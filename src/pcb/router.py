"""Freerouting integration for automatic PCB trace routing.

Exports board data to Specctra DSN format, invokes Freerouting CLI,
and imports the routed SES result back into the Board model.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from src.pcb.generator import Board, TraceSegment, Via
from src.config import get_settings
from src.utils.logger import get_logger

log = get_logger("pcb.router")


class RoutingError(Exception):
    """Raised when auto-routing fails."""


class FreeroutingRouter:
    """Manages the Freerouting auto-router lifecycle."""

    def __init__(self, board: Board, jar_path: str | None = None):
        self.board = board
        settings = get_settings()
        self._jar = jar_path or settings.freerouting_jar

    def route(self, timeout_seconds: int = 300) -> Board:
        """Run Freerouting and return the board with routed traces.

        Falls back to ratsnest if Freerouting is not available.
        """
        if not self._jar or not Path(self._jar).exists():
            log.warning(
                "Freerouting JAR not found at '%s'. Using ratsnest (unrouted) traces.",
                self._jar,
            )
            return self.board

        # Check Java availability
        if not self._java_available():
            log.warning("Java runtime not found. Cannot run Freerouting.")
            return self.board

        with tempfile.TemporaryDirectory(prefix="aipcb_") as tmpdir:
            dsn_path = Path(tmpdir) / "board.dsn"
            ses_path = Path(tmpdir) / "board.ses"

            self._export_dsn(dsn_path)
            self._run_freerouting(dsn_path, ses_path, timeout_seconds)

            if ses_path.exists():
                self._import_ses(ses_path)
                log.info("Auto-routing completed successfully.")
            else:
                log.warning("Freerouting did not produce output. Keeping ratsnest.")

        return self.board

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
