"""PCB generation engine.

Converts a CircuitSpec into internal board representation
with placed components, pads, and nets ready for routing.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from src.ai.schemas import (
    BoardSpec,
    CircuitSpec,
    ComponentSpec,
    DesignConstraints,
    NetSpec,
    PinRef,
)
from src.pcb.components import ComponentDB
from src.utils.logger import get_logger

log = get_logger("pcb.generator")


# ---------------------------------------------------------------------------
# Internal board model (lightweight, framework-agnostic)
# ---------------------------------------------------------------------------

@dataclass
class Pad:
    net_name: str = ""
    x_mm: float = 0.0
    y_mm: float = 0.0
    width_mm: float = 1.0
    height_mm: float = 1.0
    drill_mm: float = 0.0  # 0 = SMD
    shape: str = "circle"   # circle, rect, oval
    number: str = ""
    component_ref: str = ""


@dataclass
class PlacedComponent:
    ref: str = ""
    value: str = ""
    footprint: str = ""
    x_mm: float = 0.0
    y_mm: float = 0.0
    rotation_deg: float = 0.0
    layer: str = "F.Cu"
    pads: list[Pad] = field(default_factory=list)


@dataclass
class TraceSegment:
    net_name: str = ""
    start_x: float = 0.0
    start_y: float = 0.0
    end_x: float = 0.0
    end_y: float = 0.0
    width_mm: float = 0.25
    layer: str = "F.Cu"
    is_ratsnest: bool = False  # True for unrouted guide lines


@dataclass
class Via:
    net_name: str = ""
    x_mm: float = 0.0
    y_mm: float = 0.0
    diameter_mm: float = 0.8
    drill_mm: float = 0.4


@dataclass
class BoardOutline:
    x_mm: float = 0.0
    y_mm: float = 0.0
    width_mm: float = 100.0
    height_mm: float = 100.0


@dataclass
class Board:
    """Internal board representation holding all physical PCB data."""
    outline: BoardOutline = field(default_factory=BoardOutline)
    layers: int = 2
    thickness_mm: float = 1.6
    components: list[PlacedComponent] = field(default_factory=list)
    traces: list[TraceSegment] = field(default_factory=list)
    vias: list[Via] = field(default_factory=list)
    constraints: DesignConstraints = field(default_factory=DesignConstraints)

    def get_all_pads(self) -> list[Pad]:
        pads = []
        for comp in self.components:
            pads.extend(comp.pads)
        return pads

    def get_pads_for_net(self, net_name: str) -> list[Pad]:
        return [p for p in self.get_all_pads() if p.net_name == net_name]

    def get_net_names(self) -> list[str]:
        names: set[str] = set()
        for pad in self.get_all_pads():
            if pad.net_name:
                names.add(pad.net_name)
        return sorted(names)


# ---------------------------------------------------------------------------
# PCB Generator
# ---------------------------------------------------------------------------

class PCBGenerator:
    """Converts CircuitSpec → Board with placed components and pad-net assignments."""

    def __init__(self, spec: CircuitSpec):
        self.spec = spec
        self._footprint_cache: dict[tuple[str, str], str] = {}

    def generate(self) -> Board:
        """Build a Board from the circuit specification."""
        board = Board(
            layers=self.spec.board.layers,
            thickness_mm=self.spec.board.thickness_mm,
            constraints=self.spec.constraints,
        )

        # 1. Place components
        for comp_spec in self.spec.components:
            placed = self._place_component(comp_spec)
            board.components.append(placed)

        # 2. Auto-fit board outline to component positions
        self._fit_board_outline(board)

        # 3. Assign nets to pads
        self._assign_nets(board)

        # 4. Generate L-shaped routed traces
        self._generate_traces(board)

        log.info(
            "Board generated: %d components, %d pads, %d traces",
            len(board.components),
            len(board.get_all_pads()),
            len(board.traces),
        )
        return board

    def _fit_board_outline(self, board: Board) -> None:
        """Set board outline to encompass all pads with margin."""
        pads = board.get_all_pads()
        if not pads:
            board.outline = BoardOutline(
                width_mm=self.spec.board.width_mm,
                height_mm=self.spec.board.height_mm,
            )
            return

        margin = 5.0  # mm from outermost pad to board edge
        min_x = min(p.x_mm - p.width_mm / 2 for p in pads)
        max_x = max(p.x_mm + p.width_mm / 2 for p in pads)
        min_y = min(p.y_mm - p.height_mm / 2 for p in pads)
        max_y = max(p.y_mm + p.height_mm / 2 for p in pads)

        board.outline = BoardOutline(
            x_mm=min_x - margin,
            y_mm=min_y - margin,
            width_mm=(max_x - min_x) + 2 * margin,
            height_mm=(max_y - min_y) + 2 * margin,
        )

    # ------------------------------------------------------------------

    def _place_component(self, comp: ComponentSpec) -> PlacedComponent:
        """Create a PlacedComponent with pads from a ComponentSpec."""
        placed = PlacedComponent(
            ref=comp.ref,
            value=comp.value,
            footprint=self._resolve_footprint(comp),
            x_mm=comp.x_mm,
            y_mm=comp.y_mm,
            rotation_deg=comp.rotation_deg,
            layer=comp.layer.value,
        )

        # Generate pads from pins — auto-generate defaults if pins list is empty
        if not comp.pins:
            from src.ai.schemas import PinSpec
            comp.pins = [PinSpec(number="1", name="1"), PinSpec(number="2", name="2")]
            log.warning("Component '%s' has no pins — generated 2 default pins", comp.ref)

        pin_count = len(comp.pins)
        pad_spacing = 5.08  # mm (standard 200mil pitch for THT)

        if pin_count <= 3:
            # Inline pads for small components (resistors, caps, LEDs, etc.)
            for i, pin in enumerate(comp.pins):
                placed.pads.append(Pad(
                    number=pin.number,
                    component_ref=comp.ref,
                    x_mm=comp.x_mm + (i - (pin_count - 1) / 2) * pad_spacing,
                    y_mm=comp.y_mm,
                    width_mm=1.6,
                    height_mm=1.6,
                    shape="circle",
                    drill_mm=0.8,
                ))
        else:
            # Dual-row (DIP/SOIC style) or quad (QFP style)
            half = pin_count // 2
            pin_pitch = 2.54   # mm between pins in same row
            row_spacing = 3.81  # mm from center to each row (7.62mm DIP width)
            for i, pin in enumerate(comp.pins):
                if i < half:
                    # Left side
                    px = comp.x_mm - row_spacing
                    py = comp.y_mm + (i - (half - 1) / 2) * pin_pitch
                else:
                    # Right side
                    j = i - half
                    px = comp.x_mm + row_spacing
                    py = comp.y_mm + ((half - 1) / 2 - j) * pin_pitch

                placed.pads.append(Pad(
                    number=pin.number,
                    component_ref=comp.ref,
                    x_mm=px,
                    y_mm=py,
                    width_mm=1.6,
                    height_mm=1.6,
                    shape="circle",
                    drill_mm=0.8,
                ))

        return placed

    def _resolve_footprint(self, comp: ComponentSpec) -> str:
        """Resolve the most useful KiCad footprint identifier for export."""
        if comp.footprint:
            name = comp.footprint.name.strip()
            library = comp.footprint.library.strip()
            if library and ":" not in name:
                return f"{library}:{name}"
            if name:
                return name

        package = (comp.package or "").strip()
        if ":" in package:
            return package
        if not package:
            return comp.ref

        category = comp.category.value
        cache_key = (category, package)
        if cache_key in self._footprint_cache:
            return self._footprint_cache[cache_key]

        resolved = package
        try:
            with ComponentDB() as db:
                db_footprint = db.get_footprint(category, package).strip()
                if db_footprint:
                    resolved = db_footprint
        except Exception:
            log.debug(
                "Footprint lookup failed for %s (%s / %s)",
                comp.ref,
                category,
                package,
                exc_info=True,
            )

        self._footprint_cache[cache_key] = resolved
        return resolved

    def _assign_nets(self, board: Board) -> None:
        """Assign net names to pads based on the netlist."""
        # Build lookup: (ref, pin_number) -> Pad
        pad_map: dict[tuple[str, str], Pad] = {}
        for comp in board.components:
            for pad in comp.pads:
                pad_map[(comp.ref, pad.number)] = pad

        # Secondary lookup: (ref, name_lower) -> pin_number from spec
        pin_name_map: dict[tuple[str, str], str] = {}
        for comp_spec in self.spec.components:
            for pin in comp_spec.pins:
                if pin.name:
                    pin_name_map[(comp_spec.ref, pin.name.lower())] = pin.number
                pin_name_map[(comp_spec.ref, pin.number.lower())] = pin.number

        matched = 0
        failed = 0
        for net in self.spec.nets:
            for pin_ref in net.connections:
                key = (pin_ref.ref, pin_ref.pin)
                pad = pad_map.get(key)
                if not pad:
                    # Fallback: resolve pin name → number
                    resolved = pin_name_map.get((pin_ref.ref, pin_ref.pin.lower()))
                    if resolved:
                        pad = pad_map.get((pin_ref.ref, resolved))
                if not pad:
                    # Last resort: first unassigned pad on this component
                    for p in board.get_all_pads():
                        if p.component_ref == pin_ref.ref and not p.net_name:
                            pad = p
                            break
                if pad:
                    pad.net_name = net.name
                    matched += 1
                else:
                    failed += 1
                    avail = [k[1] for k in pad_map if k[0] == pin_ref.ref]
                    log.warning(
                        "Net '%s': no pad for %s pin %s (available: %s)",
                        net.name, pin_ref.ref, pin_ref.pin, avail,
                    )
        log.info("Net assignment: %d matched, %d failed", matched, failed)

    def _generate_traces(self, board: Board) -> None:
        """Create L-shaped routed traces between pads of the same net."""
        _POWER_NETS = {"VCC", "VDD", "GND", "VSS", "5V", "3V3", "3.3V", "12V",
                       "+5V", "+3.3V", "+12V", "VIN", "V+", "V-", "VOUT"}

        for net_name in board.get_net_names():
            pads = board.get_pads_for_net(net_name)
            if len(pads) < 2:
                continue

            is_power = net_name.upper() in _POWER_NETS
            tw = 0.5 if is_power else board.constraints.trace_width_mm

            # Chain: connect each pad to the next with L-shaped trace
            for i in range(len(pads) - 1):
                ax, ay = pads[i].x_mm, pads[i].y_mm
                bx, by = pads[i + 1].x_mm, pads[i + 1].y_mm

                # L-shaped: horizontal from A, then vertical to B
                # Use the midpoint X or corner at (bx, ay)
                if abs(bx - ax) < 0.01 or abs(by - ay) < 0.01:
                    # Pads are aligned — single straight ratsnest line
                    board.traces.append(TraceSegment(
                        net_name=net_name, start_x=ax, start_y=ay,
                        end_x=bx, end_y=by, width_mm=tw,
                        layer="F.Cu", is_ratsnest=True,
                    ))
                else:
                    # Two-segment L-shape ratsnest: A→corner→B
                    corner_x, corner_y = bx, ay
                    board.traces.append(TraceSegment(
                        net_name=net_name, start_x=ax, start_y=ay,
                        end_x=corner_x, end_y=corner_y, width_mm=tw,
                        layer="F.Cu", is_ratsnest=True,
                    ))
                    board.traces.append(TraceSegment(
                        net_name=net_name, start_x=corner_x, start_y=corner_y,
                        end_x=bx, end_y=by, width_mm=tw,
                        layer="F.Cu", is_ratsnest=True,
                    ))
