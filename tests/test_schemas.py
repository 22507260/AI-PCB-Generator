"""Tests for Pydantic schema models in src/ai/schemas.py."""

import pytest
from pydantic import ValidationError

from src.ai.schemas import (
    BoardSpec,
    CircuitSpec,
    ComponentCategory,
    ComponentSpec,
    DesignConstraints,
    FootprintSpec,
    LayerName,
    NetSpec,
    PadShape,
    PadSpec,
    PinRef,
    PinSpec,
)


# ── Enum tests ────────────────────────────────────────────


class TestComponentCategory:
    def test_all_values(self):
        assert len(ComponentCategory) == 19

    def test_from_string(self):
        assert ComponentCategory("resistor") == ComponentCategory.RESISTOR
        assert ComponentCategory("microcontroller") == ComponentCategory.MICROCONTROLLER

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            ComponentCategory("nonexistent_category")


class TestPadShape:
    def test_valid_shapes(self):
        for shape in ("circle", "rect", "oval", "roundrect"):
            assert PadShape(shape) is not None

    def test_invalid_shape(self):
        with pytest.raises(ValueError):
            PadShape("hexagon")


class TestLayerName:
    def test_front_copper(self):
        assert LayerName.F_CU.value == "F.Cu"

    def test_edge_cuts(self):
        assert LayerName.EDGE_CUTS.value == "Edge.Cuts"


# ── PinSpec tests ─────────────────────────────────────────


class TestPinSpec:
    def test_required_fields(self):
        pin = PinSpec(number="1")
        assert pin.number == "1"
        assert pin.name == ""
        assert pin.electrical_type == "passive"

    def test_full_pin(self):
        pin = PinSpec(number="VIN", name="Voltage Input", electrical_type="power_in")
        assert pin.number == "VIN"
        assert pin.electrical_type == "power_in"

    def test_missing_number_raises(self):
        with pytest.raises(ValidationError):
            PinSpec()


# ── PadSpec tests ─────────────────────────────────────────


class TestPadSpec:
    def test_defaults(self):
        pad = PadSpec(number="1")
        assert pad.x_mm == 0.0
        assert pad.width_mm == 1.0
        assert pad.shape == PadShape.CIRCLE
        assert pad.drill_mm == 0.0  # SMD by default

    def test_smd_vs_tht(self):
        smd = PadSpec(number="1", drill_mm=0.0)
        tht = PadSpec(number="1", drill_mm=0.8)
        assert smd.drill_mm == 0.0
        assert tht.drill_mm == 0.8


# ── ComponentSpec tests ───────────────────────────────────


class TestComponentSpec:
    def test_minimal(self):
        comp = ComponentSpec(ref="R1", value="10k")
        assert comp.ref == "R1"
        assert comp.category == ComponentCategory.OTHER
        assert comp.pins == []
        assert comp.footprint is None

    def test_full_component(self):
        comp = ComponentSpec(
            ref="U1", value="ATmega328P",
            category=ComponentCategory.MICROCONTROLLER,
            package="DIP-28",
            pins=[PinSpec(number=str(i)) for i in range(1, 29)],
            footprint=FootprintSpec(name="DIP-28_W7.62mm"),
        )
        assert len(comp.pins) == 28
        assert comp.footprint.name == "DIP-28_W7.62mm"

    def test_placement_defaults(self):
        comp = ComponentSpec(ref="C1", value="100n")
        assert comp.x_mm == 0.0
        assert comp.y_mm == 0.0
        assert comp.rotation_deg == 0.0
        assert comp.layer == LayerName.F_CU

    def test_missing_ref_raises(self):
        with pytest.raises(ValidationError):
            ComponentSpec(value="10k")


# ── NetSpec tests ─────────────────────────────────────────


class TestNetSpec:
    def test_valid_net(self):
        net = NetSpec(
            name="VCC",
            connections=[PinRef(ref="R1", pin="1"), PinRef(ref="C1", pin="1")],
        )
        assert len(net.connections) == 2

    def test_min_connections_enforced(self):
        """NetSpec requires at least 2 connections."""
        with pytest.raises(ValidationError):
            NetSpec(name="bad", connections=[PinRef(ref="R1", pin="1")])

    def test_empty_connections_raises(self):
        with pytest.raises(ValidationError):
            NetSpec(name="empty", connections=[])

    def test_missing_name_raises(self):
        with pytest.raises(ValidationError):
            NetSpec(connections=[PinRef(ref="R1", pin="1"), PinRef(ref="R2", pin="1")])


# ── CircuitSpec tests ─────────────────────────────────────


class TestCircuitSpec:
    def test_minimal(self):
        spec = CircuitSpec(name="Test")
        assert spec.component_count == 0
        assert spec.net_count == 0
        assert spec.board.width_mm == 100.0
        assert spec.constraints.trace_width_mm == 0.25

    def test_component_count(self, simple_spec):
        assert simple_spec.component_count == 3

    def test_net_count(self, simple_spec):
        assert simple_spec.net_count == 3

    def test_get_component(self, simple_spec):
        r1 = simple_spec.get_component("R1")
        assert r1 is not None
        assert r1.ref == "R1"

    def test_get_component_not_found(self, simple_spec):
        assert simple_spec.get_component("Z99") is None

    def test_get_nets_for_component(self, simple_spec):
        nets = simple_spec.get_nets_for_component("R1")
        net_names = {n.name for n in nets}
        assert "VCC" in net_names
        assert "VOUT" in net_names

    def test_missing_name_raises(self):
        with pytest.raises(ValidationError):
            CircuitSpec()

    def test_serialization_roundtrip(self, simple_spec):
        """Verify JSON round-trip preserves data."""
        json_str = simple_spec.model_dump_json()
        restored = CircuitSpec.model_validate_json(json_str)
        assert restored.name == simple_spec.name
        assert restored.component_count == simple_spec.component_count
        assert restored.net_count == simple_spec.net_count


# ── DesignConstraints / BoardSpec tests ───────────────────


class TestDesignConstraints:
    def test_defaults(self):
        dc = DesignConstraints()
        assert dc.trace_width_mm == 0.25
        assert dc.clearance_mm == 0.2
        assert dc.via_diameter_mm == 0.8
        assert dc.via_drill_mm == 0.4
        assert dc.copper_weight_oz == 1.0
        assert dc.impedance_controlled is False


class TestBoardSpec:
    def test_defaults(self):
        bs = BoardSpec()
        assert bs.width_mm == 100.0
        assert bs.height_mm == 100.0
        assert bs.layers == 2
        assert bs.thickness_mm == 1.6
        assert bs.shape == "rectangular"
