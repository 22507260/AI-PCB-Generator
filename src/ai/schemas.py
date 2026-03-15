"""Pydantic schemas for AI-generated circuit specifications.

These models define the structured contract between the AI engine
and the PCB generation pipeline.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ComponentCategory(str, Enum):
    RESISTOR = "resistor"
    CAPACITOR = "capacitor"
    INDUCTOR = "inductor"
    DIODE = "diode"
    LED = "led"
    TRANSISTOR = "transistor"
    MOSFET = "mosfet"
    IC = "ic"
    REGULATOR = "regulator"
    OPAMP = "opamp"
    MICROCONTROLLER = "microcontroller"
    CONNECTOR = "connector"
    CRYSTAL = "crystal"
    RELAY = "relay"
    TRANSFORMER = "transformer"
    FUSE = "fuse"
    SWITCH = "switch"
    SENSOR = "sensor"
    OTHER = "other"


class PadShape(str, Enum):
    CIRCLE = "circle"
    RECT = "rect"
    OVAL = "oval"
    ROUNDRECT = "roundrect"


class LayerName(str, Enum):
    F_CU = "F.Cu"
    B_CU = "B.Cu"
    IN1_CU = "In1.Cu"
    IN2_CU = "In2.Cu"
    IN3_CU = "In3.Cu"
    IN4_CU = "In4.Cu"
    F_SILKSCREEN = "F.SilkS"
    B_SILKSCREEN = "B.SilkS"
    F_MASK = "F.Mask"
    B_MASK = "B.Mask"
    EDGE_CUTS = "Edge.Cuts"
    F_COURTYARD = "F.CrtYd"
    B_COURTYARD = "B.CrtYd"
    F_FAB = "F.Fab"
    B_FAB = "B.Fab"


# ---------------------------------------------------------------------------
# Pin / Pad
# ---------------------------------------------------------------------------

class PinSpec(BaseModel):
    """A single pin on a component."""
    number: str = Field(..., description="Pin number/name (e.g. '1', 'VIN', 'GND')")
    name: str = Field(default="", description="Functional pin name")
    electrical_type: str = Field(
        default="passive",
        description="Pin type: input, output, power_in, power_out, passive, bidirectional",
    )


class PadSpec(BaseModel):
    """Physical pad on a footprint."""
    number: str
    x_mm: float = 0.0
    y_mm: float = 0.0
    width_mm: float = 1.0
    height_mm: float = 1.0
    shape: PadShape = PadShape.CIRCLE
    drill_mm: float = 0.0  # 0 = SMD pad


# ---------------------------------------------------------------------------
# Component
# ---------------------------------------------------------------------------

class FootprintSpec(BaseModel):
    """Footprint (physical package) description."""
    library: str = Field(default="", description="KiCad footprint library name")
    name: str = Field(..., description="Footprint name (e.g. 'R_0805_2012Metric')")
    pads: list[PadSpec] = Field(default_factory=list)


class ComponentSpec(BaseModel):
    """A single electronic component in the circuit."""
    ref: str = Field(..., description="Reference designator (e.g. 'R1', 'U1', 'C3')")
    value: str = Field(..., description="Component value (e.g. '10kΩ', '100nF', 'LM7805')")
    category: ComponentCategory = ComponentCategory.OTHER
    package: str = Field(default="", description="Package type (e.g. '0805', 'SOT-23', 'DIP-8')")
    description: str = Field(default="")
    manufacturer: str = Field(default="")
    manufacturer_pn: str = Field(default="", description="Manufacturer part number")
    pins: list[PinSpec] = Field(default_factory=list)
    footprint: Optional[FootprintSpec] = None
    datasheet_url: str = Field(default="")

    # Placement hints
    x_mm: float = Field(default=0.0, description="Suggested X position on board")
    y_mm: float = Field(default=0.0, description="Suggested Y position on board")
    rotation_deg: float = Field(default=0.0)
    layer: LayerName = Field(default=LayerName.F_CU)


# ---------------------------------------------------------------------------
# Net / Connection
# ---------------------------------------------------------------------------

class PinRef(BaseModel):
    """Reference to a specific pin on a component."""
    ref: str = Field(..., description="Component reference (e.g. 'R1')")
    pin: str = Field(..., description="Pin number/name (e.g. '1', 'VIN')")

    @field_validator("pin", mode="before")
    @classmethod
    def _coerce_pin(cls, v):
        if v is None:
            return "1"
        return str(v)


class NetSpec(BaseModel):
    """An electrical net connecting multiple pins."""
    name: str = Field(..., description="Net name (e.g. 'VCC', 'GND', 'NET1')")
    connections: list[PinRef] = Field(
        ..., min_length=2, description="At least two pins connected"
    )


# ---------------------------------------------------------------------------
# Design constraints
# ---------------------------------------------------------------------------

class DesignConstraints(BaseModel):
    """Board-level design rules and constraints."""
    trace_width_mm: float = Field(default=0.25)
    clearance_mm: float = Field(default=0.2)
    via_diameter_mm: float = Field(default=0.8)
    via_drill_mm: float = Field(default=0.4)
    min_trace_width_mm: float = Field(default=0.15)
    min_clearance_mm: float = Field(default=0.15)
    copper_weight_oz: float = Field(default=1.0, description="Copper weight in oz/ft²")
    impedance_controlled: bool = Field(default=False)


class BoardSpec(BaseModel):
    """Physical board specification."""
    width_mm: float = Field(default=100.0)
    height_mm: float = Field(default=100.0)
    layers: int = Field(default=2, description="Number of copper layers")
    thickness_mm: float = Field(default=1.6, description="Board thickness")
    shape: str = Field(default="rectangular", description="Board outline shape")


# ---------------------------------------------------------------------------
# Top-level circuit specification
# ---------------------------------------------------------------------------

class CircuitSpec(BaseModel):
    """Complete AI-generated circuit specification.

    This is the primary data contract between the AI engine and
    the PCB generation pipeline.
    """
    name: str = Field(..., description="Circuit/project name")
    description: str = Field(default="", description="Human-readable circuit description")
    components: list[ComponentSpec] = Field(default_factory=list)
    nets: list[NetSpec] = Field(default_factory=list)
    board: BoardSpec = Field(default_factory=BoardSpec)
    constraints: DesignConstraints = Field(default_factory=DesignConstraints)

    @property
    def component_count(self) -> int:
        return len(self.components)

    @property
    def net_count(self) -> int:
        return len(self.nets)

    def get_component(self, ref: str) -> ComponentSpec | None:
        """Look up a component by reference designator."""
        for c in self.components:
            if c.ref == ref:
                return c
        return None

    def get_nets_for_component(self, ref: str) -> list[NetSpec]:
        """Return all nets connected to a given component."""
        return [
            net for net in self.nets
            if any(pin.ref == ref for pin in net.connections)
        ]
