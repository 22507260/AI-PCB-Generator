"""Tests for PCB generation engine in src/pcb/generator.py."""

import pytest

from src.ai.schemas import (
    CircuitSpec,
    ComponentCategory,
    ComponentSpec,
    FootprintSpec,
    NetSpec,
    PinRef,
    PinSpec,
)
from src.pcb.generator import (
    Board,
    BoardOutline,
    Pad,
    PCBGenerator,
    PlacedComponent,
    TraceSegment,
)


# ── Board dataclass tests ────────────────────────────────


class TestBoard:
    def test_empty_board(self, empty_board):
        assert len(empty_board.components) == 0
        assert len(empty_board.traces) == 0
        assert empty_board.get_all_pads() == []

    def test_get_all_pads(self, board_with_components):
        pads = board_with_components.get_all_pads()
        assert len(pads) == 4  # 2 components × 2 pads

    def test_get_pads_for_net(self, board_with_components):
        vout_pads = board_with_components.get_pads_for_net("VOUT")
        assert len(vout_pads) == 2
        assert all(p.net_name == "VOUT" for p in vout_pads)

    def test_get_pads_for_nonexistent_net(self, board_with_components):
        assert board_with_components.get_pads_for_net("NOPE") == []

    def test_get_net_names(self, board_with_components):
        names = board_with_components.get_net_names()
        assert sorted(names) == ["GND", "VCC", "VOUT"]


# ── PCBGenerator tests ───────────────────────────────────


class TestPCBGenerator:
    def test_generate_simple(self, simple_spec):
        gen = PCBGenerator(simple_spec)
        board = gen.generate()

        assert len(board.components) == 3  # J1 + R1 + R2
        assert len(board.get_all_pads()) == 6  # J1(2) + R1(2) + R2(2)

    def test_generate_creates_traces(self, simple_spec):
        gen = PCBGenerator(simple_spec)
        board = gen.generate()

        # Should have traces for VOUT net (connects R1:2 to R2:1)
        assert len(board.traces) > 0

    def test_board_outline_fitted(self, simple_spec):
        """Board outline should encompass all pads with margin."""
        gen = PCBGenerator(simple_spec)
        board = gen.generate()
        o = board.outline

        for pad in board.get_all_pads():
            assert pad.x_mm >= o.x_mm, f"Pad {pad.component_ref}:{pad.number} outside left edge"
            assert pad.x_mm <= o.x_mm + o.width_mm, f"Pad outside right edge"
            assert pad.y_mm >= o.y_mm, f"Pad outside top edge"
            assert pad.y_mm <= o.y_mm + o.height_mm, f"Pad outside bottom edge"

    def test_net_assignment(self, simple_spec):
        """Pads should be assigned to correct nets."""
        gen = PCBGenerator(simple_spec)
        board = gen.generate()

        net_names = board.get_net_names()
        # At least VOUT should be assigned (connects two resistors)
        assert "VOUT" in net_names

    def test_auto_generates_pins(self):
        """Components with no pins should get 2 default pins."""
        spec = CircuitSpec(
            name="No Pins",
            components=[ComponentSpec(ref="R1", value="10k", pins=[])],
            nets=[],
        )
        gen = PCBGenerator(spec)
        board = gen.generate()

        # Generator should auto-add 2 pins
        assert len(board.components[0].pads) == 2

    def test_dual_row_placement(self):
        """Components with 4+ pins should get dual-row (DIP) layout."""
        spec = CircuitSpec(
            name="IC Test",
            components=[
                ComponentSpec(
                    ref="U1", value="ATtiny85",
                    category=ComponentCategory.IC,
                    package="DIP-8",
                    pins=[PinSpec(number=str(i)) for i in range(1, 9)],
                ),
            ],
            nets=[],
        )
        gen = PCBGenerator(spec)
        board = gen.generate()

        pads = board.components[0].pads
        assert len(pads) == 8

        # First half should be on left side, second half on right
        left_xs = [p.x_mm for p in pads[:4]]
        right_xs = [p.x_mm for p in pads[4:]]
        assert all(lx < rx for lx, rx in zip(left_xs, right_xs))

    def test_power_traces_wider(self, led_circuit_spec):
        """Power net traces should be wider (0.5mm) than signal traces."""
        gen = PCBGenerator(led_circuit_spec)
        board = gen.generate()

        for trace in board.traces:
            if trace.net_name.upper() in {"VCC", "GND"}:
                assert trace.width_mm >= 0.5, f"Power trace {trace.net_name} too narrow"

    def test_generate_led_circuit(self, led_circuit_spec):
        """Full LED circuit should generate properly."""
        gen = PCBGenerator(led_circuit_spec)
        board = gen.generate()

        assert len(board.components) == 3
        assert board.outline.width_mm > 0
        assert board.outline.height_mm > 0

    def test_joins_explicit_footprint_library_and_name(self):
        spec = CircuitSpec(
            name="Footprint Join",
            components=[
                ComponentSpec(
                    ref="R1",
                    value="10k",
                    category=ComponentCategory.RESISTOR,
                    package="0805",
                    footprint=FootprintSpec(
                        library="Resistor_SMD",
                        name="R_0805_2012Metric",
                    ),
                    pins=[PinSpec(number="1"), PinSpec(number="2")],
                ),
            ],
            nets=[],
        )

        board = PCBGenerator(spec).generate()
        assert board.components[0].footprint == "Resistor_SMD:R_0805_2012Metric"

    def test_resolves_db_footprint_from_package(self):
        spec = CircuitSpec(
            name="Footprint Lookup",
            components=[
                ComponentSpec(
                    ref="R1",
                    value="10k",
                    category=ComponentCategory.RESISTOR,
                    package="0805",
                    pins=[PinSpec(number="1"), PinSpec(number="2")],
                ),
            ],
            nets=[],
        )

        board = PCBGenerator(spec).generate()
        assert board.components[0].footprint == "Resistor_SMD:R_0805_2012Metric"
