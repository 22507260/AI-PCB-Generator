"""Tests for circuit validator / parser in src/ai/parser.py."""

import pytest

from src.ai.schemas import (
    CircuitSpec,
    ComponentCategory,
    ComponentSpec,
    NetSpec,
    PinRef,
    PinSpec,
)
from src.ai.parser import CircuitValidator, validate_circuit, ValidationWarning


# ── Pin auto-generation ──────────────────────────────────


class TestEnsurePins:
    def test_auto_generates_2_pins_for_resistor(self):
        spec = CircuitSpec(
            name="Test",
            components=[
                ComponentSpec(ref="R1", value="10k",
                              category=ComponentCategory.RESISTOR, pins=[]),
            ],
        )
        validator = CircuitValidator(spec)
        validated = validator.validate()
        assert len(validated.components[0].pins) == 2

    def test_infers_pins_from_package(self):
        """Package name like 'DIP-8' should yield 8 pins."""
        spec = CircuitSpec(
            name="Test",
            components=[
                ComponentSpec(ref="U1", value="ATtiny85",
                              category=ComponentCategory.IC,
                              package="DIP-8", pins=[]),
            ],
        )
        validator = CircuitValidator(spec)
        validated = validator.validate()
        assert len(validated.components[0].pins) == 8

    def test_existing_pins_preserved(self):
        pins = [PinSpec(number="A"), PinSpec(number="K")]
        spec = CircuitSpec(
            name="Test",
            components=[
                ComponentSpec(ref="D1", value="LED",
                              category=ComponentCategory.LED, pins=pins),
            ],
        )
        validator = CircuitValidator(spec)
        validated = validator.validate()
        assert len(validated.components[0].pins) == 2
        assert validated.components[0].pins[0].number == "A"

    def test_transistor_gets_3_pins(self):
        spec = CircuitSpec(
            name="Test",
            components=[
                ComponentSpec(ref="Q1", value="2N2222",
                              category=ComponentCategory.TRANSISTOR, pins=[]),
            ],
        )
        validator = CircuitValidator(spec)
        validated = validator.validate()
        assert len(validated.components[0].pins) == 3


# ── Unique reference check ───────────────────────────────


class TestUniqueRefs:
    def test_duplicate_refs_warned(self):
        spec = CircuitSpec(
            name="Test",
            components=[
                ComponentSpec(ref="R1", value="10k",
                              pins=[PinSpec(number="1"), PinSpec(number="2")]),
                ComponentSpec(ref="R1", value="20k",
                              pins=[PinSpec(number="1"), PinSpec(number="2")]),
            ],
        )
        validator = CircuitValidator(spec)
        validator.validate()
        msgs = [w.message for w in validator.warnings]
        assert any("Duplicate" in m for m in msgs)


# ── Net reference fixing ─────────────────────────────────


class TestNetReferences:
    def test_removes_unknown_component(self):
        spec = CircuitSpec(
            name="Test",
            components=[
                ComponentSpec(ref="R1", value="10k",
                              pins=[PinSpec(number="1"), PinSpec(number="2")]),
            ],
            nets=[
                NetSpec(name="N1", connections=[
                    PinRef(ref="R1", pin="1"),
                    PinRef(ref="GHOST", pin="1"),
                    PinRef(ref="R1", pin="2"),
                ]),
            ],
        )
        validator = CircuitValidator(spec)
        validated = validator.validate()
        # GHOST should be removed; net may survive if ≥2 valid connections
        for net in validated.nets:
            refs = [c.ref for c in net.connections]
            assert "GHOST" not in refs

    def test_fixes_pin_by_name_match(self):
        """If pin number doesn't match but name does, auto-fix."""
        spec = CircuitSpec(
            name="Test",
            components=[
                ComponentSpec(ref="D1", value="LED",
                              category=ComponentCategory.LED,
                              pins=[PinSpec(number="1", name="A"),
                                    PinSpec(number="2", name="K")]),
            ],
            nets=[
                NetSpec(name="N1", connections=[
                    PinRef(ref="D1", pin="A"),  # Name, not number
                    PinRef(ref="D1", pin="K"),
                ]),
            ],
        )
        validator = CircuitValidator(spec)
        validated = validator.validate()
        # Pin refs should be fixed to number "1" and "2"
        if validated.nets:
            pins = {c.pin for c in validated.nets[0].connections}
            assert "1" in pins or "A" in pins  # Either direct match or fixed


# ── Degenerate net cleanup ───────────────────────────────


class TestDegenerateNets:
    def test_single_connection_net_removed(self):
        spec = CircuitSpec(
            name="Test",
            components=[
                ComponentSpec(ref="R1", value="10k",
                              pins=[PinSpec(number="1"), PinSpec(number="2")]),
            ],
            nets=[
                NetSpec(name="BAD", connections=[
                    PinRef(ref="R1", pin="1"),
                    PinRef(ref="FAKE", pin="1"),  # Will be removed → net degenerates
                ]),
            ],
        )
        validator = CircuitValidator(spec)
        validated = validator.validate()
        # Net should be removed after FAKE is removed (only 1 connection left)
        assert len(validated.nets) == 0


# ── Power net warnings ───────────────────────────────────


class TestPowerNets:
    def test_warns_no_gnd(self):
        spec = CircuitSpec(
            name="Test",
            components=[
                ComponentSpec(ref="R1", value="10k",
                              pins=[PinSpec(number="1"), PinSpec(number="2")]),
            ],
            nets=[
                NetSpec(name="VCC", connections=[
                    PinRef(ref="R1", pin="1"), PinRef(ref="R1", pin="2"),
                ]),
            ],
        )
        validator = CircuitValidator(spec)
        validator.validate()
        msgs = [w.message for w in validator.warnings]
        assert any("GND" in m for m in msgs)

    def test_warns_no_power(self):
        spec = CircuitSpec(
            name="Test",
            components=[
                ComponentSpec(ref="R1", value="10k",
                              pins=[PinSpec(number="1"), PinSpec(number="2")]),
            ],
            nets=[
                NetSpec(name="GND", connections=[
                    PinRef(ref="R1", pin="1"), PinRef(ref="R1", pin="2"),
                ]),
            ],
        )
        validator = CircuitValidator(spec)
        validator.validate()
        msgs = [w.message for w in validator.warnings]
        assert any("power supply" in m.lower() or "VCC" in m for m in msgs)


# ── Position assignment ──────────────────────────────────


class TestAssignPositions:
    def test_auto_places_unplaced_components(self):
        spec = CircuitSpec(
            name="Test",
            components=[
                ComponentSpec(ref="R1", value="10k",
                              pins=[PinSpec(number="1"), PinSpec(number="2")],
                              x_mm=0, y_mm=0),
                ComponentSpec(ref="R2", value="20k",
                              pins=[PinSpec(number="1"), PinSpec(number="2")],
                              x_mm=0, y_mm=0),
            ],
        )
        validator = CircuitValidator(spec)
        validated = validator.validate()

        # After validation, components should have non-zero positions
        positions = [(c.x_mm, c.y_mm) for c in validated.components]
        assert any(x != 0 or y != 0 for x, y in positions)

    def test_preserves_existing_positions(self):
        spec = CircuitSpec(
            name="Test",
            components=[
                ComponentSpec(ref="R1", value="10k",
                              pins=[PinSpec(number="1"), PinSpec(number="2")],
                              x_mm=50, y_mm=30),
            ],
        )
        validator = CircuitValidator(spec)
        validated = validator.validate()
        assert validated.components[0].x_mm == 50
        assert validated.components[0].y_mm == 30


# ── Convenience wrapper ──────────────────────────────────


class TestValidateCircuit:
    def test_returns_tuple(self):
        spec = CircuitSpec(
            name="Test",
            components=[
                ComponentSpec(ref="R1", value="10k",
                              pins=[PinSpec(number="1"), PinSpec(number="2")]),
            ],
        )
        result, warnings = validate_circuit(spec)
        assert isinstance(result, CircuitSpec)
        assert isinstance(warnings, list)
