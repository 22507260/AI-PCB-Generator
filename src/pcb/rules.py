"""Design Rule Check (DRC) engine.

Validates a generated Board against configurable design constraints.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from src.pcb.generator import Board, Pad, TraceSegment, Via
from src.utils.logger import get_logger

log = get_logger("pcb.rules")


@dataclass
class DRCViolation:
    """A single design rule violation."""
    rule: str
    message: str
    severity: str = "error"      # error, warning
    x_mm: float = 0.0
    y_mm: float = 0.0

    def __repr__(self) -> str:
        return f"[DRC {self.severity.upper()}] {self.rule}: {self.message} @ ({self.x_mm:.2f}, {self.y_mm:.2f})"


class DRCEngine:
    """Run design rule checks on a Board."""

    def __init__(self, board: Board):
        self.board = board
        self.violations: list[DRCViolation] = []

    def run_all(self) -> list[DRCViolation]:
        """Execute all DRC checks and return violations."""
        self.violations.clear()

        self._check_trace_width()
        self._check_clearance_pad_to_pad()
        self._check_clearance_trace_to_pad()
        self._check_via_drill()
        self._check_board_boundary()
        self._check_unconnected_pads()

        if self.violations:
            log.warning("DRC found %d violation(s).", len(self.violations))
            for v in self.violations:
                log.warning("  %s", v)
        else:
            log.info("DRC passed — no violations.")

        return self.violations

    @property
    def has_errors(self) -> bool:
        return any(v.severity == "error" for v in self.violations)

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_trace_width(self) -> None:
        """Verify all traces meet the minimum width."""
        min_w = self.board.constraints.min_trace_width_mm
        for t in self.board.traces:
            if t.width_mm < min_w - 1e-6:
                self.violations.append(DRCViolation(
                    rule="min_trace_width",
                    message=f"Trace width {t.width_mm:.3f}mm < minimum {min_w:.3f}mm",
                    x_mm=t.start_x,
                    y_mm=t.start_y,
                ))

    def _check_clearance_pad_to_pad(self) -> None:
        """Check minimum clearance between pads of different nets."""
        min_clr = self.board.constraints.min_clearance_mm
        pads = self.board.get_all_pads()

        for i in range(len(pads)):
            for j in range(i + 1, len(pads)):
                a, b = pads[i], pads[j]
                if a.net_name == b.net_name:
                    continue  # Same net — skip
                if a.component_ref == b.component_ref:
                    continue  # Same component — handled by footprint

                dist = math.hypot(a.x_mm - b.x_mm, a.y_mm - b.y_mm)
                # Approximate edge-to-edge distance
                edge_dist = dist - (a.width_mm + b.width_mm) / 2
                if edge_dist < min_clr - 1e-6:
                    self.violations.append(DRCViolation(
                        rule="pad_clearance",
                        message=(
                            f"Pad {a.component_ref}:{a.number} ↔ {b.component_ref}:{b.number} "
                            f"clearance {edge_dist:.3f}mm < {min_clr:.3f}mm"
                        ),
                        severity="error",
                        x_mm=(a.x_mm + b.x_mm) / 2,
                        y_mm=(a.y_mm + b.y_mm) / 2,
                    ))

    def _check_clearance_trace_to_pad(self) -> None:
        """Check clearance between routed traces and pads of different nets."""
        min_clr = self.board.constraints.min_clearance_mm
        pads = self.board.get_all_pads()

        for trace in self.board.traces:
            if trace.is_ratsnest:
                continue  # Skip unrouted guide lines
            for pad in pads:
                if pad.net_name == trace.net_name:
                    continue
                # Distance from pad center to trace line segment
                dist = self._point_to_segment_distance(
                    pad.x_mm, pad.y_mm,
                    trace.start_x, trace.start_y,
                    trace.end_x, trace.end_y,
                )
                edge_dist = dist - pad.width_mm / 2 - trace.width_mm / 2
                if edge_dist < min_clr - 1e-6:
                    self.violations.append(DRCViolation(
                        rule="trace_pad_clearance",
                        message=(
                            f"Trace (net={trace.net_name}) ↔ Pad {pad.component_ref}:{pad.number} "
                            f"clearance {edge_dist:.3f}mm < {min_clr:.3f}mm"
                        ),
                        severity="error",
                        x_mm=pad.x_mm,
                        y_mm=pad.y_mm,
                    ))

    def _check_via_drill(self) -> None:
        """Ensure via drills are within tolerance."""
        for via in self.board.vias:
            if via.drill_mm < 0.2:
                self.violations.append(DRCViolation(
                    rule="via_drill",
                    message=f"Via drill {via.drill_mm:.3f}mm is below 0.2mm manufacturing limit.",
                    x_mm=via.x_mm,
                    y_mm=via.y_mm,
                ))
            if via.drill_mm >= via.diameter_mm:
                self.violations.append(DRCViolation(
                    rule="via_annular_ring",
                    message=f"Via drill ({via.drill_mm}mm) ≥ diameter ({via.diameter_mm}mm) — no annular ring.",
                    x_mm=via.x_mm,
                    y_mm=via.y_mm,
                ))

    def _check_board_boundary(self) -> None:
        """Ensure all pads are within the board outline."""
        o = self.board.outline
        for pad in self.board.get_all_pads():
            margin = 0.5  # mm from edge
            if (
                pad.x_mm < o.x_mm + margin
                or pad.x_mm > o.x_mm + o.width_mm - margin
                or pad.y_mm < o.y_mm + margin
                or pad.y_mm > o.y_mm + o.height_mm - margin
            ):
                self.violations.append(DRCViolation(
                    rule="board_boundary",
                    message=f"Pad {pad.component_ref}:{pad.number} is outside or too close to board edge.",
                    severity="warning",
                    x_mm=pad.x_mm,
                    y_mm=pad.y_mm,
                ))

    def _check_unconnected_pads(self) -> None:
        """Warn about pads with no net assigned."""
        for pad in self.board.get_all_pads():
            if not pad.net_name:
                self.violations.append(DRCViolation(
                    rule="unconnected",
                    message=f"Pad {pad.component_ref}:{pad.number} has no net assignment.",
                    severity="warning",
                    x_mm=pad.x_mm,
                    y_mm=pad.y_mm,
                ))

    # ------------------------------------------------------------------
    # Geometry helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _point_to_segment_distance(
        px: float, py: float,
        ax: float, ay: float,
        bx: float, by: float,
    ) -> float:
        """Calculate the shortest distance from point (px,py) to segment (ax,ay)-(bx,by)."""
        dx, dy = bx - ax, by - ay
        seg_len_sq = dx * dx + dy * dy
        if seg_len_sq < 1e-12:
            return math.hypot(px - ax, py - ay)

        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg_len_sq))
        proj_x = ax + t * dx
        proj_y = ay + t * dy
        return math.hypot(px - proj_x, py - proj_y)
