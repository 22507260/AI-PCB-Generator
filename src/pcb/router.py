"""Freerouting integration and internal A* maze router for PCB trace routing.

Exports board data to Specctra DSN format, invokes Freerouting CLI,
and imports the routed SES result back into the Board model.
When Freerouting is not available, falls back to an internal grid-based
A* maze router.
"""

from __future__ import annotations

import heapq
import math
import subprocess
import tempfile
from pathlib import Path

from src.pcb.generator import Board, TraceSegment, Via
from src.config import get_settings
from src.vendor import find_freerouting_jar
from src.utils.logger import get_logger

log = get_logger("pcb.router")


class RoutingError(Exception):
    """Raised when auto-routing fails."""


class FreeroutingRouter:
    """Manages the Freerouting auto-router lifecycle."""

    def __init__(self, board: Board, jar_path: str | None = None):
        self.board = board
        self._jar = jar_path or find_freerouting_jar() or ""

    def route(self, timeout_seconds: int = 300) -> Board:
        """Run Freerouting and return the board with routed traces.

        Falls back to internal A* maze router if Freerouting is unavailable
        or if the Freerouting run/import fails.
        """
        if not self._jar or not Path(self._jar).exists():
            log.warning(
                "Freerouting JAR not found at '%s'. Using internal A* router.",
                self._jar,
            )
            return _maze_route(self.board)

        # Check Java availability
        if not self._java_available():
            log.warning("Java runtime not found. Using internal A* router.")
            return _maze_route(self.board)

        with tempfile.TemporaryDirectory(prefix="aipcb_") as tmpdir:
            dsn_path = Path(tmpdir) / "board.dsn"
            ses_path = Path(tmpdir) / "board.ses"

            try:
                self._export_dsn(dsn_path)
                self._run_freerouting(dsn_path, ses_path, timeout_seconds)

                if ses_path.exists():
                    self._import_ses(ses_path)
                    log.info("Auto-routing completed successfully.")
                    return self.board

                log.warning(
                    "Freerouting did not produce SES output. Falling back to internal A* router."
                )
            except Exception as exc:
                log.warning(
                    "Freerouting failed (%s). Falling back to internal A* router.",
                    exc,
                )
                log.debug("Freerouting failure details", exc_info=True)

        return _maze_route(self.board)

    # ------------------------------------------------------------------
    # DSN Export
    # ------------------------------------------------------------------

    def _export_dsn(self, path: Path) -> None:
        """Write the board in Specctra DSN format."""
        b = self.board
        o = b.outline
        lines: list[str] = []

        lines.append("(pcb board.dsn")
        lines.append("  (parser (string_quote \") (host_cad KiCad) (host_version ai-pcb))")
        lines.append(f"  (resolution mm 1000)")
        lines.append(f"  (unit mm)")

        # Structure
        lines.append("  (structure")
        for layer_idx in range(b.layers):
            name = f"F.Cu" if layer_idx == 0 else (f"B.Cu" if layer_idx == b.layers - 1 else f"In{layer_idx}.Cu")
            lines.append(f'    (layer "{name}" (type signal))')
        lines.append(f"    (boundary (rect pcb {o.x_mm} {o.y_mm} {o.x_mm + o.width_mm} {o.y_mm + o.height_mm}))")
        lines.append(f"    (rule (width {b.constraints.trace_width_mm}) (clearance {b.constraints.clearance_mm}))")
        lines.append("  )")

        # Placement
        lines.append("  (placement")
        for comp in b.components:
            lines.append(f'    (component "{comp.footprint}"')
            lines.append(f'      (place "{comp.ref}" {comp.x_mm} {comp.y_mm} {comp.layer} {comp.rotation_deg})')
            lines.append("    )")
        lines.append("  )")

        # Library (simplified)
        lines.append("  (library")
        for comp in b.components:
            lines.append(f'    (image "{comp.footprint}"')
            for pad in comp.pads:
                lines.append(
                    f'      (pin round_pad "{pad.number}" {pad.x_mm - comp.x_mm} {pad.y_mm - comp.y_mm})'
                )
            lines.append("    )")
        lines.append("  )")

        # Network
        lines.append("  (network")
        net_names = b.get_net_names()
        for net_name in net_names:
            pads = b.get_pads_for_net(net_name)
            pins_str = " ".join(f'"{p.component_ref}"-"{p.number}"' for p in pads)
            lines.append(f'    (net "{net_name}" (pins {pins_str}))')
        lines.append("  )")

        lines.append(")")

        path.write_text("\n".join(lines), encoding="utf-8")
        log.debug("Exported DSN to %s", path)

    # ------------------------------------------------------------------
    # Run Freerouting
    # ------------------------------------------------------------------

    def _run_freerouting(self, dsn: Path, ses: Path, timeout: int) -> None:
        """Invoke Freerouting CLI as a subprocess."""
        cmd = ["java", "-jar", self._jar, "-de", str(dsn), "-do", str(ses)]
        log.info("Running Freerouting: %s", " ".join(cmd))

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if result.returncode != 0:
                log.error("Freerouting stderr: %s", result.stderr)
                raise RoutingError(f"Freerouting exited with code {result.returncode}")
        except subprocess.TimeoutExpired:
            raise RoutingError(f"Freerouting timed out after {timeout}s")
        except FileNotFoundError:
            raise RoutingError("Java executable not found. Install Java 11+.")

    # ------------------------------------------------------------------
    # SES Import
    # ------------------------------------------------------------------

    def _import_ses(self, path: Path) -> None:
        """Parse Specctra SES file and update board traces.

        SES parsing is simplified — handles basic wiring structures.
        """
        content = path.read_text(encoding="utf-8")

        # Clear ratsnest traces (they'll be replaced by routed traces)
        self.board.traces.clear()

        # Basic SES wire extraction
        # Full parser would use a proper S-expression parser;
        # this handles the common `(wire (path …))` pattern.
        import re

        wire_pattern = re.compile(
            r'\(wire\s+\(path\s+"?([^")\s]+)"?\s+([\d.]+)\s+'
            r'([\d.\s-]+)\)',
            re.DOTALL,
        )
        for match in wire_pattern.finditer(content):
            layer = match.group(1)
            width = float(match.group(2))
            coords = match.group(3).strip().split()

            # Coordinates come in pairs (x y x y …)
            points = []
            for i in range(0, len(coords) - 1, 2):
                try:
                    points.append((float(coords[i]), float(coords[i + 1])))
                except (ValueError, IndexError):
                    continue

            for i in range(len(points) - 1):
                self.board.traces.append(TraceSegment(
                    start_x=points[i][0],
                    start_y=points[i][1],
                    end_x=points[i + 1][0],
                    end_y=points[i + 1][1],
                    width_mm=width,
                    layer=layer,
                ))

        # Extract vias
        via_pattern = re.compile(
            r'\(via\s+"?[^")\s]+"?\s+([\d.]+)\s+([\d.]+)',
        )
        for match in via_pattern.finditer(content):
            self.board.vias.append(Via(
                x_mm=float(match.group(1)),
                y_mm=float(match.group(2)),
                diameter_mm=self.board.constraints.via_diameter_mm,
                drill_mm=self.board.constraints.via_drill_mm,
            ))

        log.info(
            "Imported %d trace segments and %d vias from SES.",
            len(self.board.traces),
            len(self.board.vias),
        )

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _java_available() -> bool:
        try:
            result = subprocess.run(
                ["java", "-version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False


# ======================================================================
# Internal A* Maze Router (fallback when Freerouting is unavailable)
# ======================================================================

def _maze_route(board: Board) -> Board:
    """Route all nets using an A* grid-based maze router.

    Creates a uniform grid over the board area, marks pad/via obstacles,
    and routes each net point-to-point using A* search. Already-routed
    traces become obstacles for subsequent nets.
    """
    o = board.outline
    clearance = board.constraints.clearance_mm
    trace_w = board.constraints.trace_width_mm

    # Grid resolution — balance between quality and performance
    grid_step = max(trace_w, clearance, 0.25)

    # Grid dimensions
    cols = max(1, int(math.ceil(o.width_mm / grid_step)))
    rows = max(1, int(math.ceil(o.height_mm / grid_step)))

    # Clamp grid to reasonable size to prevent memory issues
    MAX_CELLS = 500_000
    if cols * rows > MAX_CELLS:
        scale = math.sqrt(MAX_CELLS / (cols * rows))
        grid_step = grid_step / scale
        cols = max(1, int(math.ceil(o.width_mm / grid_step)))
        rows = max(1, int(math.ceil(o.height_mm / grid_step)))

    log.info("A* router: grid %d×%d (step=%.3fmm)", cols, rows, grid_step)

    # Obstacle grid (False = free, True = blocked)
    blocked: set[tuple[int, int]] = set()

    def _mm_to_grid(x_mm: float, y_mm: float) -> tuple[int, int]:
        gc = int(round((x_mm - o.x_mm) / grid_step))
        gr = int(round((y_mm - o.y_mm) / grid_step))
        return (max(0, min(gc, cols - 1)), max(0, min(gr, rows - 1)))

    def _grid_to_mm(gc: int, gr: int) -> tuple[float, float]:
        return (o.x_mm + gc * grid_step, o.y_mm + gr * grid_step)

    def _mark_blocked(cx: float, cy: float, radius_mm: float) -> None:
        """Block grid cells around a coordinate."""
        r_cells = int(math.ceil(radius_mm / grid_step))
        gc, gr = _mm_to_grid(cx, cy)
        for di in range(-r_cells, r_cells + 1):
            for dj in range(-r_cells, r_cells + 1):
                ni, nj = gc + di, gr + dj
                if 0 <= ni < cols and 0 <= nj < rows:
                    blocked.add((ni, nj))

    # Mark component pad obstacles (pads that aren't being routed)
    pad_radius = max(0.4, trace_w)
    for comp in board.components:
        for pad in comp.pads:
            _mark_blocked(pad.x_mm, pad.y_mm, pad_radius)

    # Gather nets
    net_names = board.get_net_names()
    routed_traces: list[TraceSegment] = []

    for net_name in net_names:
        pads = board.get_pads_for_net(net_name)
        if len(pads) < 2:
            continue

        # Temporarily unblock pads in this net
        net_cells: list[tuple[int, int]] = []
        for pad in pads:
            gc_p, gr_p = _mm_to_grid(pad.x_mm, pad.y_mm)
            net_cells.append((gc_p, gr_p))
            blocked.discard((gc_p, gr_p))

        # Route star pattern: connect all pads to the first pad
        start_cell = net_cells[0]
        layer = pads[0].layer if hasattr(pads[0], 'layer') else "F.Cu"
        comp_layer = None
        for comp in board.components:
            if any(p.component_ref == comp.ref for p in pads):
                comp_layer = comp.layer
                break
        if comp_layer:
            layer = comp_layer

        for i in range(1, len(net_cells)):
            path = _astar(start_cell, net_cells[i], blocked, cols, rows)
            if path and len(path) >= 2:
                # Convert path to trace segments
                for j in range(len(path) - 1):
                    x1, y1 = _grid_to_mm(path[j][0], path[j][1])
                    x2, y2 = _grid_to_mm(path[j + 1][0], path[j + 1][1])
                    routed_traces.append(TraceSegment(
                        start_x=x1, start_y=y1,
                        end_x=x2, end_y=y2,
                        width_mm=trace_w,
                        layer=layer,
                        net_name=net_name,
                    ))
                # Block routed path cells (with trace clearance)
                for cell in path:
                    r = int(math.ceil((trace_w + clearance) / grid_step))
                    for di in range(-r, r + 1):
                        for dj in range(-r, r + 1):
                            ni, nj = cell[0] + di, cell[1] + dj
                            if 0 <= ni < cols and 0 <= nj < rows:
                                blocked.add((ni, nj))
            else:
                # Direct connection as fallback (ratsnest style)
                x1, y1 = _grid_to_mm(start_cell[0], start_cell[1])
                x2, y2 = _grid_to_mm(net_cells[i][0], net_cells[i][1])
                routed_traces.append(TraceSegment(
                    start_x=x1, start_y=y1,
                    end_x=x2, end_y=y2,
                    width_mm=trace_w,
                    layer=layer,
                    net_name=net_name,
                ))

        # Re-block net pad cells for other nets
        for cell in net_cells:
            blocked.add(cell)

    board.traces = routed_traces
    log.info("A* router complete: %d trace segments for %d nets.",
             len(routed_traces), len(net_names))
    return board


def _astar(
    start: tuple[int, int],
    goal: tuple[int, int],
    blocked: set[tuple[int, int]],
    cols: int,
    rows: int,
) -> list[tuple[int, int]]:
    """A* pathfinding on a 2D grid.

    Returns a list of (col, row) cells from start to goal, or empty list
    if no path exists. Uses 8-directional movement.
    """
    if start == goal:
        return [start]

    # Heuristic: Chebyshev distance (since we allow diagonal moves)
    def h(c: tuple[int, int]) -> float:
        return max(abs(c[0] - goal[0]), abs(c[1] - goal[1]))

    open_set: list[tuple[float, int, tuple[int, int]]] = []
    counter = 0
    heapq.heappush(open_set, (h(start), counter, start))
    came_from: dict[tuple[int, int], tuple[int, int]] = {}
    g_score: dict[tuple[int, int], float] = {start: 0.0}

    SQRT2 = math.sqrt(2)
    _DIRS = [
        (1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
        (1, 1, SQRT2), (-1, 1, SQRT2), (1, -1, SQRT2), (-1, -1, SQRT2),
    ]

    max_iterations = cols * rows * 2  # safety limit
    iterations = 0

    while open_set and iterations < max_iterations:
        iterations += 1
        _, _, current = heapq.heappop(open_set)

        if current == goal:
            # Reconstruct path
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            path.reverse()
            return _simplify_path(path)

        for dc, dr, cost in _DIRS:
            neighbor = (current[0] + dc, current[1] + dr)
            if not (0 <= neighbor[0] < cols and 0 <= neighbor[1] < rows):
                continue
            if neighbor in blocked:
                continue
            tentative_g = g_score[current] + cost
            if tentative_g < g_score.get(neighbor, float('inf')):
                came_from[neighbor] = current
                g_score[neighbor] = tentative_g
                f = tentative_g + h(neighbor)
                counter += 1
                heapq.heappush(open_set, (f, counter, neighbor))

    return []  # No path found


def _simplify_path(path: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Remove collinear intermediate points to reduce trace segments."""
    if len(path) <= 2:
        return path
    result = [path[0]]
    for i in range(1, len(path) - 1):
        # Check if direction changes
        dx1 = path[i][0] - path[i - 1][0]
        dy1 = path[i][1] - path[i - 1][1]
        dx2 = path[i + 1][0] - path[i][0]
        dy2 = path[i + 1][1] - path[i][1]
        if (dx1, dy1) != (dx2, dy2):
            result.append(path[i])
    result.append(path[-1])
    return result
