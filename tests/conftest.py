"""Shared pytest fixtures for the AI PCB Generator test suite."""

from __future__ import annotations

import pytest

from src.ai.schemas import (
    BoardSpec,
    CircuitSpec,
    ComponentCategory,
    ComponentSpec,
    DesignConstraints,
    FootprintSpec,
    NetSpec,
    PadSpec,
    PinRef,
    PinSpec,
)
from src.pcb.generator import (
    Board,
    BoardOutline,
    Pad,
    PlacedComponent,
    TraceSegment,
    Via,
)
from src.simulation.results import AnalysisConfig


# ── Minimal CircuitSpec fixtures ─────────────────────────────────────


@pytest.fixture
def simple_spec() -> CircuitSpec:
    """A simple voltage divider: R1 + R2 with VCC/GND/VOUT nets."""
    return CircuitSpec(
        name="Voltage Divider",
        description="Simple resistor divider",
        components=[
            ComponentSpec(
                ref="J1",
                value="Connector",
                category=ComponentCategory.CONNECTOR,
                pins=[PinSpec(number="1", name="VCC"), PinSpec(number="2", name="GND")],
            ),
            ComponentSpec(
                ref="R1",
                value="10kΩ",
                category=ComponentCategory.RESISTOR,
                package="0805",
                pins=[PinSpec(number="1", name="1"), PinSpec(number="2", name="2")],
            ),
            ComponentSpec(
                ref="R2",
                value="10kΩ",
                category=ComponentCategory.RESISTOR,
                package="0805",
                pins=[PinSpec(number="1", name="1"), PinSpec(number="2", name="2")],
            ),
        ],
        nets=[
            NetSpec(name="VCC", connections=[PinRef(ref="J1", pin="1"), PinRef(ref="R1", pin="1")]),
            NetSpec(name="VOUT", connections=[PinRef(ref="R1", pin="2"), PinRef(ref="R2", pin="1")]),
            NetSpec(name="GND", connections=[PinRef(ref="J1", pin="2"), PinRef(ref="R2", pin="2")]),
        ],
        board=BoardSpec(width_mm=50, height_mm=30),
        constraints=DesignConstraints(),
    )


@pytest.fixture
def led_circuit_spec() -> CircuitSpec:
    """LED + resistor + power connector."""
    return CircuitSpec(
        name="LED Blinker",
        components=[
            ComponentSpec(
                ref="J1", value="Connector", category=ComponentCategory.CONNECTOR,
                pins=[PinSpec(number="1", name="VCC"), PinSpec(number="2", name="GND")],
            ),
            ComponentSpec(
                ref="R1", value="330Ω", category=ComponentCategory.RESISTOR,
                pins=[PinSpec(number="1", name="1"), PinSpec(number="2", name="2")],
            ),
            ComponentSpec(
                ref="D1", value="Red LED", category=ComponentCategory.LED,
                pins=[PinSpec(number="1", name="A"), PinSpec(number="2", name="K")],
            ),
        ],
        nets=[
            NetSpec(name="VCC", connections=[PinRef(ref="J1", pin="1"), PinRef(ref="R1", pin="1")]),
            NetSpec(name="NET1", connections=[PinRef(ref="R1", pin="2"), PinRef(ref="D1", pin="1")]),
            NetSpec(name="GND", connections=[PinRef(ref="D1", pin="2"), PinRef(ref="J1", pin="2")]),
        ],
    )


# ── Board fixtures ───────────────────────────────────────────────────


@pytest.fixture
def empty_board() -> Board:
    """Empty board with default dimensions."""
    return Board(
        outline=BoardOutline(x_mm=0, y_mm=0, width_mm=50, height_mm=30),
    )


@pytest.fixture
def board_with_components() -> Board:
    """Board with two placed components and pads, no traces."""
    return Board(
        outline=BoardOutline(x_mm=0, y_mm=0, width_mm=60, height_mm=40),
        components=[
            PlacedComponent(
                ref="R1", value="10k", footprint="R_0805",
                x_mm=15, y_mm=20,
                pads=[
                    Pad(number="1", component_ref="R1", x_mm=12.46, y_mm=20,
                        width_mm=1.6, height_mm=1.6, drill_mm=0.8, net_name="VCC"),
                    Pad(number="2", component_ref="R1", x_mm=17.54, y_mm=20,
                        width_mm=1.6, height_mm=1.6, drill_mm=0.8, net_name="VOUT"),
                ],
            ),
            PlacedComponent(
                ref="R2", value="10k", footprint="R_0805",
                x_mm=35, y_mm=20,
                pads=[
                    Pad(number="1", component_ref="R2", x_mm=32.46, y_mm=20,
                        width_mm=1.6, height_mm=1.6, drill_mm=0.8, net_name="VOUT"),
                    Pad(number="2", component_ref="R2", x_mm=37.54, y_mm=20,
                        width_mm=1.6, height_mm=1.6, drill_mm=0.8, net_name="GND"),
                ],
            ),
        ],
    )


@pytest.fixture
def board_with_traces(board_with_components: Board) -> Board:
    """Board with components and a routed trace."""
    board_with_components.traces = [
        TraceSegment(
            net_name="VOUT", start_x=17.54, start_y=20,
            end_x=32.46, end_y=20, width_mm=0.25, layer="F.Cu",
        ),
    ]
    return board_with_components


@pytest.fixture
def board_with_vias() -> Board:
    """Board with vias for DFM testing."""
    return Board(
        outline=BoardOutline(x_mm=0, y_mm=0, width_mm=50, height_mm=50),
        vias=[
            Via(net_name="VCC", x_mm=10, y_mm=10, diameter_mm=0.8, drill_mm=0.4),
            Via(net_name="GND", x_mm=20, y_mm=20, diameter_mm=0.8, drill_mm=0.4),
        ],
    )


# ── Simulation fixtures ──────────────────────────────────────────────


@pytest.fixture
def dc_op_config() -> AnalysisConfig:
    """DC operating point analysis config."""
    return AnalysisConfig(analysis_type="op")


@pytest.fixture
def tran_config() -> AnalysisConfig:
    """Transient analysis config."""
    return AnalysisConfig(
        analysis_type="tran",
        tran_step=1e-6,
        tran_stop=1e-3,
    )


@pytest.fixture
def ac_config() -> AnalysisConfig:
    """AC sweep analysis config."""
    return AnalysisConfig(
        analysis_type="ac",
        ac_sweep_type="dec",
        ac_n_points=10,
        ac_f_start=1.0,
        ac_f_stop=1e6,
    )


@pytest.fixture
def rc_netlist() -> str:
    """Simple RC circuit SPICE netlist for solver testing."""
    return (
        "* Simple RC Low-Pass Filter\n"
        "V1 in 0 DC 5\n"
        "R1 in out 1k\n"
        "C1 out 0 100n\n"
        ".end\n"
    )


@pytest.fixture
def voltage_divider_netlist() -> str:
    """Voltage divider SPICE netlist."""
    return (
        "* Voltage Divider\n"
        "V1 vin 0 DC 10\n"
        "R1 vin vout 10k\n"
        "R2 vout 0 10k\n"
        ".end\n"
    )
