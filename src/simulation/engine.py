"""NgSpice subprocess engine — runs SPICE simulations via ngspice CLI."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile

from src.simulation.results import AnalysisConfig, SimulationResult
from src.vendor import find_ngspice as _vendor_find_ngspice

log = logging.getLogger(__name__)


class NgSpiceEngine:
    """Wrapper around the NgSpice command-line simulator."""

    def __init__(self):
        self._exe: str | None = None

    def find_ngspice(self) -> str | None:
        """Locate the ngspice executable (vendor first, then system)."""
        if self._exe:
            return self._exe

        found = _vendor_find_ngspice()
        if found:
            self._exe = found
            return self._exe

        return None

    @property
    def available(self) -> bool:
        return self.find_ngspice() is not None

    def run(self, netlist: str, config: AnalysisConfig, timeout: int = 30) -> SimulationResult:
        """Run a SPICE simulation and return results.

        Args:
            netlist: Complete SPICE netlist string.
            config: Analysis configuration.
            timeout: Maximum execution time in seconds.

        Returns:
            SimulationResult with parsed waveform data.
        """
        exe = self.find_ngspice()
        if not exe:
            return SimulationResult(
                analysis_type=config.analysis_type,
                success=False,
                error_message="NgSpice not found",
                engine_used="ngspice",
            )

        tmpdir = tempfile.mkdtemp(prefix="apcb_sim_")
        try:
            cir_path = os.path.join(tmpdir, "circuit.cir")
            raw_path = os.path.join(tmpdir, "output.raw")

            with open(cir_path, "w", encoding="utf-8") as f:
                f.write(netlist)

            cmd = [exe, "-b", "-r", raw_path, cir_path]
            log.info("Running: %s", " ".join(cmd))

            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=tmpdir,
            )

            raw_output = proc.stdout + "\n" + proc.stderr

            if proc.returncode != 0 and not os.path.isfile(raw_path):
                return SimulationResult(
                    analysis_type=config.analysis_type,
                    success=False,
                    error_message=f"NgSpice exited with code {proc.returncode}:\n{proc.stderr[:500]}",
                    engine_used="ngspice",
                    raw_output=raw_output,
                )

            # Parse results
            from src.simulation.result_parser import parse_raw_file, parse_stdout

            if os.path.isfile(raw_path) and os.path.getsize(raw_path) > 0:
                result = parse_raw_file(raw_path, config)
            else:
                result = parse_stdout(raw_output, config)

            result.engine_used = "ngspice"
            result.raw_output = raw_output
            return result

        except subprocess.TimeoutExpired:
            return SimulationResult(
                analysis_type=config.analysis_type,
                success=False,
                error_message=f"Simulation timed out after {timeout}s",
                engine_used="ngspice",
            )
        except Exception as e:
            log.exception("NgSpice execution error")
            return SimulationResult(
                analysis_type=config.analysis_type,
                success=False,
                error_message=str(e),
                engine_used="ngspice",
            )
        finally:
            # Cleanup temp files
            try:
                shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception:
                pass
