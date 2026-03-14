"""Design for Manufacturing (DFM) analysis engine.

Validates a Board against real-world manufacturing constraints
and provides actionable recommendations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

from src.pcb.generator import Board, Pad, PlacedComponent, TraceSegment, Via
from src.utils.logger import get_logger

log = get_logger("pcb.dfm")


# ======================================================================
# DFM Issue Model
# ======================================================================

class DFMCategory(str, Enum):
    MANUFACTURING = "manufacturing"
    THERMAL = "thermal"
    ELECTRICAL = "electrical"
    ASSEMBLY = "assembly"
    SIGNAL_INTEGRITY = "signal_integrity"


class DFMSeverity(str, Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


@dataclass
class DFMIssue:
    category: DFMCategory
    severity: DFMSeverity
    code: str
    title: str
    description: str
    recommendation: str = ""
    refs: list[str] = field(default_factory=list)
    x_mm: float = 0.0
    y_mm: float = 0.0


# ======================================================================
# Current Capacity Tables (IPC-2221)
# ======================================================================

# Approximate max current (A) for 1oz copper at 10°C rise, external layer
# Key = trace width in mm, Value = max current in amps
_TRACE_CURRENT_CAPACITY: list[tuple[float, float]] = [
    (0.10, 0.3),
    (0.15, 0.4),
    (0.20, 0.5),
    (0.25, 0.7),
    (0.30, 0.8),
    (0.40, 1.0),
    (0.50, 1.2),
    (0.75, 1.6),
    (1.00, 2.0),
    (1.50, 2.8),
    (2.00, 3.5),
    (3.00, 4.8),
    (5.00, 7.0),
]


def _max_current_for_width(width_mm: float) -> float:
    """Interpolate max current for a given trace width."""
    if width_mm <= _TRACE_CURRENT_CAPACITY[0][0]:
        return _TRACE_CURRENT_CAPACITY[0][1]
    if width_mm >= _TRACE_CURRENT_CAPACITY[-1][0]:
        return _TRACE_CURRENT_CAPACITY[-1][1]
    for i in range(len(_TRACE_CURRENT_CAPACITY) - 1):
        w0, c0 = _TRACE_CURRENT_CAPACITY[i]
        w1, c1 = _TRACE_CURRENT_CAPACITY[i + 1]
        if w0 <= width_mm <= w1:
            t = (width_mm - w0) / (w1 - w0)
            return c0 + t * (c1 - c0)
    return _TRACE_CURRENT_CAPACITY[-1][1]


# Power net names that carry significant current
_POWER_NETS = {"VCC", "VDD", "GND", "VSS", "5V", "3V3", "3.3V", "12V",
               "+5V", "+3.3V", "+12V", "VIN", "V+", "V-", "VOUT", "VBAT"}


# ======================================================================
# DFM Engine
# ======================================================================

class DFMEngine:
    """Run Design-for-Manufacturing analysis on a Board."""

    def __init__(self, board: Board):
        self.board = board

    def run_all(self) -> list[DFMIssue]:
        """Execute all DFM checks and return issues."""
        issues: list[DFMIssue] = []

        issues.extend(self._check_trace_current_capacity())
        issues.extend(self._check_annular_ring())
        issues.extend(self._check_acid_traps())
        issues.extend(self._check_thermal_relief())
        issues.extend(self._check_silkscreen_over_pads())
        issues.extend(self._check_component_spacing())
        issues.extend(self._check_board_size())
        issues.extend(self._check_via_aspect_ratio())
        issues.extend(self._check_copper_balance())
        issues.extend(self._check_solder_bridge_risk())
        issues.extend(self._check_minimum_drill())
        issues.extend(self._check_trace_length_mismatch())

        if issues:
            log.info("DFM analysis found %d issue(s).", len(issues))
        else:
            log.info("DFM analysis passed — no issues.")

        return issues

    # ------------------------------------------------------------------
    # DFM-001: Power trace current capacity
    # ------------------------------------------------------------------

    def _check_trace_current_capacity(self) -> list[DFMIssue]:
        """Check if power traces can handle expected current."""
        issues: list[DFMIssue] = []
        for trace in self.board.traces:
            if trace.is_ratsnest:
                continue
            if not trace.net_name or trace.net_name.upper() not in _POWER_NETS:
                continue
            max_a = _max_current_for_width(trace.width_mm)
            if trace.width_mm < 0.4:
                issues.append(DFMIssue(
                    category=DFMCategory.ELECTRICAL,
                    severity=DFMSeverity.WARNING,
                    code="DFM-001",
                    title="Narrow power trace",
                    description=(
                        f"Power trace on net '{trace.net_name}' is "
                        f"{trace.width_mm:.2f}mm wide (max ~{max_a:.1f}A). "
                        f"Recommend ≥0.5mm for power lines."
                    ),
                    recommendation=f"Increase trace width to ≥0.5mm for reliable current capacity.",
                    x_mm=trace.start_x,
                    y_mm=trace.start_y,
                ))
        return issues

    # ------------------------------------------------------------------
    # DFM-002: Annular ring
    # ------------------------------------------------------------------

    def _check_annular_ring(self) -> list[DFMIssue]:
        """Verify annular ring is sufficient for manufacturing."""
        issues: list[DFMIssue] = []
        min_ring = 0.15  # mm — typical fab minimum

        for via in self.board.vias:
            ring = (via.diameter_mm - via.drill_mm) / 2
            if ring < min_ring:
                issues.append(DFMIssue(
                    category=DFMCategory.MANUFACTURING,
                    severity=DFMSeverity.CRITICAL,
                    code="DFM-002",
                    title="Insufficient annular ring (via)",
                    description=(
                        f"Via at ({via.x_mm:.1f}, {via.y_mm:.1f}) has "
                        f"{ring:.3f}mm annular ring (min {min_ring}mm)."
                    ),
                    recommendation=f"Increase via diameter or decrease drill size.",
                    x_mm=via.x_mm,
                    y_mm=via.y_mm,
                ))

        for pad in self.board.get_all_pads():
            if pad.drill_mm <= 0:
                continue
            ring = (min(pad.width_mm, pad.height_mm) - pad.drill_mm) / 2
            if ring < min_ring:
                issues.append(DFMIssue(
                    category=DFMCategory.MANUFACTURING,
                    severity=DFMSeverity.WARNING,
                    code="DFM-002",
                    title="Insufficient annular ring (pad)",
                    description=(
                        f"Pad {pad.component_ref}:{pad.number} has "
                        f"{ring:.3f}mm annular ring (min {min_ring}mm)."
                    ),
                    recommendation="Increase pad size or decrease drill.",
                    refs=[pad.component_ref],
                    x_mm=pad.x_mm,
                    y_mm=pad.y_mm,
                ))
        return issues

    # ------------------------------------------------------------------
    # DFM-003: Acid traps (acute-angle trace junctions)
    # ------------------------------------------------------------------

    def _check_acid_traps(self) -> list[DFMIssue]:
        """Detect acute-angle trace junctions that trap etchant."""
        issues: list[DFMIssue] = []
        traces = [t for t in self.board.traces if not t.is_ratsnest]
        if len(traces) < 2:
            return issues

        # Group traces by layer
        layer_traces: dict[str, list[TraceSegment]] = {}
        for t in traces:
            layer_traces.setdefault(t.layer, []).append(t)

        for layer, lt in layer_traces.items():
            for i in range(len(lt)):
                for j in range(i + 1, len(lt)):
                    a, b = lt[i], lt[j]
                    # Check if traces share an endpoint
                    shared = None
                    if abs(a.end_x - b.start_x) < 0.01 and abs(a.end_y - b.start_y) < 0.01:
                        shared = (a.end_x, a.end_y)
                        va = (a.end_x - a.start_x, a.end_y - a.start_y)
                        vb = (b.end_x - b.start_x, b.end_y - b.start_y)
                    elif abs(a.end_x - b.end_x) < 0.01 and abs(a.end_y - b.end_y) < 0.01:
                        shared = (a.end_x, a.end_y)
                        va = (a.end_x - a.start_x, a.end_y - a.start_y)
                        vb = (b.start_x - b.end_x, b.start_y - b.end_y)
                    else:
                        continue

                    la = math.hypot(*va)
                    lb = math.hypot(*vb)
                    if la < 0.01 or lb < 0.01:
                        continue
                    cos_angle = (va[0] * vb[0] + va[1] * vb[1]) / (la * lb)
                    cos_angle = max(-1.0, min(1.0, cos_angle))
                    angle_deg = math.degrees(math.acos(cos_angle))

                    if angle_deg < 45:
                        issues.append(DFMIssue(
                            category=DFMCategory.MANUFACTURING,
                            severity=DFMSeverity.WARNING,
                            code="DFM-003",
                            title="Acid trap detected",
                            description=(
                                f"Trace junction at ({shared[0]:.1f}, {shared[1]:.1f}) "
                                f"has {angle_deg:.0f}° angle — etchant may pool."
                            ),
                            recommendation="Use 45° or 90° trace junctions.",
                            x_mm=shared[0],
                            y_mm=shared[1],
                        ))
        return issues

    # ------------------------------------------------------------------
    # DFM-004: Thermal relief on power pads
    # ------------------------------------------------------------------

    def _check_thermal_relief(self) -> list[DFMIssue]:
        """Check large power pads that may need thermal relief for soldering."""
        issues: list[DFMIssue] = []
        for pad in self.board.get_all_pads():
            if not pad.net_name:
                continue
            if pad.net_name.upper() not in _POWER_NETS:
                continue
            # Large THT pads on power nets should have thermal relief
            if pad.drill_mm > 0 and pad.width_mm >= 2.0:
                issues.append(DFMIssue(
                    category=DFMCategory.THERMAL,
                    severity=DFMSeverity.INFO,
                    code="DFM-004",
                    title="Thermal relief recommended",
                    description=(
                        f"Pad {pad.component_ref}:{pad.number} on power net "
                        f"'{pad.net_name}' is large ({pad.width_mm:.1f}mm). "
                        f"Thermal relief improves solderability."
                    ),
                    recommendation="Add thermal relief pattern to power plane connection.",
                    refs=[pad.component_ref],
                    x_mm=pad.x_mm,
                    y_mm=pad.y_mm,
                ))
        return issues

    # ------------------------------------------------------------------
    # DFM-005: Silkscreen over pads
    # ------------------------------------------------------------------

    def _check_silkscreen_over_pads(self) -> list[DFMIssue]:
        """Detect potential silkscreen encroachment on pads.

        Approximation: checks if component reference position overlaps
        any pad of same component.
        """
        issues: list[DFMIssue] = []
        for comp in self.board.components:
            # Silkscreen ref is typically at component center
            ref_x, ref_y = comp.x_mm, comp.y_mm - 2.0  # typical offset
            for pad in comp.pads:
                dist = math.hypot(ref_x - pad.x_mm, ref_y - pad.y_mm)
                if dist < pad.width_mm * 0.8:
                    issues.append(DFMIssue(
                        category=DFMCategory.MANUFACTURING,
                        severity=DFMSeverity.WARNING,
                        code="DFM-005",
                        title="Silkscreen over pad",
                        description=(
                            f"Reference label for {comp.ref} may overlap "
                            f"pad {pad.number}."
                        ),
                        recommendation="Move silkscreen text away from exposed copper.",
                        refs=[comp.ref],
                        x_mm=comp.x_mm,
                        y_mm=comp.y_mm,
                    ))
                    break  # One warning per component
        return issues

    # ------------------------------------------------------------------
    # DFM-006: Component spacing for assembly
    # ------------------------------------------------------------------

    def _check_component_spacing(self) -> list[DFMIssue]:
        """Check minimum spacing between components for pick-and-place."""
        issues: list[DFMIssue] = []
        min_spacing = 1.0  # mm edge-to-edge minimum for assembly
        comps = self.board.components

        for i in range(len(comps)):
            for j in range(i + 1, len(comps)):
                a, b = comps[i], comps[j]
                dist = math.hypot(a.x_mm - b.x_mm, a.y_mm - b.y_mm)
                # Rough estimate: subtract component body sizes
                body_a = self._component_body_radius(a)
                body_b = self._component_body_radius(b)
                edge_dist = dist - body_a - body_b

                if edge_dist < min_spacing and edge_dist >= 0:
                    issues.append(DFMIssue(
                        category=DFMCategory.ASSEMBLY,
                        severity=DFMSeverity.WARNING,
                        code="DFM-006",
                        title="Tight component spacing",
                        description=(
                            f"{a.ref} ↔ {b.ref} edge distance ~{edge_dist:.2f}mm "
                            f"(min {min_spacing}mm for assembly)."
                        ),
                        recommendation="Increase spacing for pick-and-place machines.",
                        refs=[a.ref, b.ref],
                        x_mm=(a.x_mm + b.x_mm) / 2,
                        y_mm=(a.y_mm + b.y_mm) / 2,
                    ))
        return issues

    # ------------------------------------------------------------------
    # DFM-007: Board dimensions
    # ------------------------------------------------------------------

    def _check_board_size(self) -> list[DFMIssue]:
        """Validate board size is within common fab limits."""
        issues: list[DFMIssue] = []
        o = self.board.outline

        if o.width_mm < 5 or o.height_mm < 5:
            issues.append(DFMIssue(
                category=DFMCategory.MANUFACTURING,
                severity=DFMSeverity.WARNING,
                code="DFM-007",
                title="Very small board",
                description=(
                    f"Board is {o.width_mm:.1f}×{o.height_mm:.1f}mm. "
                    f"Many fabs require minimum 10×10mm."
                ),
                recommendation="Consider panelization for very small boards.",
            ))
        elif o.width_mm > 500 or o.height_mm > 500:
            issues.append(DFMIssue(
                category=DFMCategory.MANUFACTURING,
                severity=DFMSeverity.WARNING,
                code="DFM-007",
                title="Large board",
                description=(
                    f"Board is {o.width_mm:.1f}×{o.height_mm:.1f}mm — "
                    f"exceeds standard panel (450×600mm)."
                ),
                recommendation="Check manufacturer's maximum board size.",
            ))
        return issues

    # ------------------------------------------------------------------
    # DFM-008: Via aspect ratio
    # ------------------------------------------------------------------

    def _check_via_aspect_ratio(self) -> list[DFMIssue]:
        """Check via aspect ratio (depth/diameter) for plating reliability."""
        issues: list[DFMIssue] = []
        board_thickness = self.board.thickness_mm or 1.6
        max_aspect = 8.0  # typical fab limit

        for via in self.board.vias:
            if via.drill_mm <= 0:
                continue
            aspect = board_thickness / via.drill_mm
            if aspect > max_aspect:
                issues.append(DFMIssue(
                    category=DFMCategory.MANUFACTURING,
                    severity=DFMSeverity.CRITICAL,
                    code="DFM-008",
                    title="High via aspect ratio",
                    description=(
                        f"Via at ({via.x_mm:.1f}, {via.y_mm:.1f}) has "
                        f"aspect ratio {aspect:.1f}:1 (max {max_aspect:.0f}:1). "
                        f"Plating may be unreliable."
                    ),
                    recommendation="Increase drill size or reduce board thickness.",
                    x_mm=via.x_mm,
                    y_mm=via.y_mm,
                ))
        return issues

    # ------------------------------------------------------------------
    # DFM-009: Copper balance
    # ------------------------------------------------------------------

    def _check_copper_balance(self) -> list[DFMIssue]:
        """Check copper distribution balance between layers."""
        issues: list[DFMIssue] = []
        if self.board.layers < 2:
            return issues

        layer_count: dict[str, int] = {}
        for trace in self.board.traces:
            if trace.is_ratsnest:
                continue
            layer_count[trace.layer] = layer_count.get(trace.layer, 0) + 1

        for comp in self.board.components:
            for pad in comp.pads:
                layer_count[comp.layer] = layer_count.get(comp.layer, 0) + 1

        if not layer_count:
            return issues

        values = list(layer_count.values())
        total = sum(values)
        if total == 0:
            return issues

        max_layer = max(layer_count, key=layer_count.get)
        max_pct = layer_count[max_layer] / total * 100

        if max_pct > 85 and total > 10:
            issues.append(DFMIssue(
                category=DFMCategory.MANUFACTURING,
                severity=DFMSeverity.INFO,
                code="DFM-009",
                title="Unbalanced copper distribution",
                description=(
                    f"{max_pct:.0f}% of copper elements on {max_layer}. "
                    f"Unbalanced copper can cause board warping."
                ),
                recommendation="Distribute traces/copper pours more evenly across layers.",
            ))
        return issues

    # ------------------------------------------------------------------
    # DFM-010: Solder bridge risk
    # ------------------------------------------------------------------

    def _check_solder_bridge_risk(self) -> list[DFMIssue]:
        """Detect SMD pads too close together risking solder bridges."""
        issues: list[DFMIssue] = []
        min_gap = 0.2  # mm between SMD pads

        pads = [p for p in self.board.get_all_pads() if p.drill_mm == 0]
        checked: set[tuple[str, str]] = set()

        for i in range(len(pads)):
            for j in range(i + 1, len(pads)):
                a, b = pads[i], pads[j]
                if a.component_ref == b.component_ref:
                    continue
                if a.net_name == b.net_name and a.net_name:
                    continue

                pair_key = tuple(sorted([
                    f"{a.component_ref}:{a.number}",
                    f"{b.component_ref}:{b.number}",
                ]))
                if pair_key in checked:
                    continue
                checked.add(pair_key)

                dist = math.hypot(a.x_mm - b.x_mm, a.y_mm - b.y_mm)
                edge_dist = dist - (a.width_mm + b.width_mm) / 2
                if edge_dist < min_gap and edge_dist >= 0:
                    issues.append(DFMIssue(
                        category=DFMCategory.ASSEMBLY,
                        severity=DFMSeverity.WARNING,
                        code="DFM-010",
                        title="Solder bridge risk",
                        description=(
                            f"SMD pads {a.component_ref}:{a.number} ↔ "
                            f"{b.component_ref}:{b.number} gap is "
                            f"{edge_dist:.3f}mm (min {min_gap}mm)."
                        ),
                        recommendation="Increase pad spacing or use solder mask dam.",
                        refs=[a.component_ref, b.component_ref],
                        x_mm=(a.x_mm + b.x_mm) / 2,
                        y_mm=(a.y_mm + b.y_mm) / 2,
                    ))
        return issues

    # ------------------------------------------------------------------
    # DFM-011: Minimum drill size
    # ------------------------------------------------------------------

    def _check_minimum_drill(self) -> list[DFMIssue]:
        """Verify drill sizes meet fab capabilities."""
        issues: list[DFMIssue] = []
        min_drill = 0.2  # mm — typical CNC minimum

        for pad in self.board.get_all_pads():
            if pad.drill_mm > 0 and pad.drill_mm < min_drill:
                issues.append(DFMIssue(
                    category=DFMCategory.MANUFACTURING,
                    severity=DFMSeverity.CRITICAL,
                    code="DFM-011",
                    title="Drill too small",
                    description=(
                        f"Pad {pad.component_ref}:{pad.number} has "
                        f"{pad.drill_mm:.3f}mm drill (min {min_drill}mm)."
                    ),
                    recommendation=f"Increase drill to ≥{min_drill}mm.",
                    refs=[pad.component_ref],
                    x_mm=pad.x_mm,
                    y_mm=pad.y_mm,
                ))
        return issues

    # ------------------------------------------------------------------
    # DFM-012: Trace length mismatch on differential pairs
    # ------------------------------------------------------------------

    def _check_trace_length_mismatch(self) -> list[DFMIssue]:
        """Detect significant length mismatches in signal groups."""
        issues: list[DFMIssue] = []
        traces = [t for t in self.board.traces if not t.is_ratsnest]

        # Group trace lengths by net
        net_lengths: dict[str, float] = {}
        for t in traces:
            length = math.hypot(t.end_x - t.start_x, t.end_y - t.start_y)
            net_lengths[t.net_name] = net_lengths.get(t.net_name, 0) + length

        if len(net_lengths) < 2:
            return issues

        # Check for differential pair naming patterns (D+/D-, TX+/TX-)
        pairs: list[tuple[str, str]] = []
        names = list(net_lengths.keys())
        for name in names:
            if name.endswith("+"):
                partner = name[:-1] + "-"
                if partner in net_lengths:
                    pairs.append((name, partner))
            elif name.upper().endswith("_P"):
                partner = name[:-2] + ("_N" if name[-1] == "P" else "_n")
                if partner in net_lengths:
                    pairs.append((name, partner))

        for p, n in pairs:
            lp, ln = net_lengths[p], net_lengths[n]
            mismatch = abs(lp - ln)
            if mismatch > 2.0:  # mm
                issues.append(DFMIssue(
                    category=DFMCategory.SIGNAL_INTEGRITY,
                    severity=DFMSeverity.WARNING,
                    code="DFM-012",
                    title="Differential pair length mismatch",
                    description=(
                        f"Net pair {p}/{n} length difference is "
                        f"{mismatch:.1f}mm. Match within ±0.5mm for high-speed."
                    ),
                    recommendation="Add serpentine tuning to shorter net.",
                ))
        return issues

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _component_body_radius(comp: PlacedComponent) -> float:
        """Estimate component body radius from pad positions."""
        if not comp.pads:
            return 2.0  # default estimate
        max_dist = 0.0
        for pad in comp.pads:
            dist = math.hypot(pad.x_mm - comp.x_mm, pad.y_mm - comp.y_mm)
            max_dist = max(max_dist, dist)
        return max_dist + 0.5  # add body margin


# ======================================================================
# Summary Score
# ======================================================================

def compute_dfm_score(issues: list[DFMIssue]) -> int:
    """Compute a DFM score 0-100 (100 = perfect)."""
    if not issues:
        return 100
    score = 100
    for issue in issues:
        if issue.severity == DFMSeverity.CRITICAL:
            score -= 15
        elif issue.severity == DFMSeverity.WARNING:
            score -= 5
        else:
            score -= 1
    return max(0, score)
