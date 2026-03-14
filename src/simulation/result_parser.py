"""Parse NgSpice output — binary .raw files and ASCII stdout."""

from __future__ import annotations

import logging
import re
import struct
from pathlib import Path

import numpy as np

from src.simulation.results import (
    AnalysisConfig,
    OperatingPoint,
    SimulationResult,
    WaveformData,
)

log = logging.getLogger(__name__)


def parse_raw_file(path: str, config: AnalysisConfig) -> SimulationResult:
    """Parse an NgSpice binary .raw output file.

    NgSpice raw format:
        Header lines (ASCII) until 'Binary:' or 'Values:' keyword,
        then binary IEEE-754 doubles or ASCII values.
    """
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as e:
        return SimulationResult(
            analysis_type=config.analysis_type,
            success=False, error_message=f"Cannot read raw file: {e}",
        )

    # Split header from data
    # The header is ASCII, terminated by "Binary:\n" or "Values:\n"
    try:
        text_part = raw.split(b"Binary:\n")
        is_binary = True
        if len(text_part) < 2:
            text_part = raw.split(b"Values:\n")
            is_binary = False
        if len(text_part) < 2:
            # Try with \r\n
            text_part = raw.split(b"Binary:\r\n")
            is_binary = True
            if len(text_part) < 2:
                text_part = raw.split(b"Values:\r\n")
                is_binary = False

        header_text = text_part[0].decode("utf-8", errors="replace")
        data_blob = text_part[1] if len(text_part) > 1 else b""
    except Exception as e:
        return SimulationResult(
            analysis_type=config.analysis_type,
            success=False, error_message=f"Cannot parse raw header: {e}",
        )

    # Parse header fields
    n_vars = 0
    n_points = 0
    var_names: list[str] = []
    var_types: list[str] = []
    is_complex = False

    for line in header_text.splitlines():
        line_s = line.strip()
        if line_s.startswith("No. Variables:"):
            n_vars = int(line_s.split(":", 1)[1].strip())
        elif line_s.startswith("No. Points:"):
            n_points = int(line_s.split(":", 1)[1].strip())
        elif line_s.startswith("Flags:") and "complex" in line_s.lower():
            is_complex = True
        elif re.match(r"^\d+\s+", line_s):
            # Variable definition line: "0  time  time"
            parts = line_s.split()
            if len(parts) >= 3:
                var_names.append(parts[1])
                var_types.append(parts[2])
            elif len(parts) == 2:
                var_names.append(parts[1])
                var_types.append("unknown")

    if n_vars == 0 or n_points == 0:
        return SimulationResult(
            analysis_type=config.analysis_type,
            success=False, error_message="No data in raw file",
        )

    # Parse binary data
    if is_binary:
        doubles_per_point = n_vars * (2 if is_complex else 1)
        expected_bytes = n_points * doubles_per_point * 8

        if len(data_blob) < expected_bytes:
            log.warning("Raw file data shorter than expected: %d < %d", len(data_blob), expected_bytes)
            n_points = len(data_blob) // (doubles_per_point * 8)
            if n_points == 0:
                return SimulationResult(
                    analysis_type=config.analysis_type,
                    success=False, error_message="Insufficient binary data",
                )

        all_values = struct.unpack(f"<{n_points * doubles_per_point}d", data_blob[:n_points * doubles_per_point * 8])
        data = np.array(all_values).reshape(n_points, doubles_per_point)

        if is_complex:
            # Complex data: real, imag pairs
            signals: dict[str, WaveformData] = {}
            for i, name in enumerate(var_names):
                real = data[:, i * 2]
                imag = data[:, i * 2 + 1]
                magnitude = np.sqrt(real**2 + imag**2)
                phase = np.degrees(np.arctan2(imag, real))
                signals[f"{name}_mag"] = WaveformData(name=f"|{name}|", unit="", values=magnitude)
                signals[f"{name}_phase"] = WaveformData(name=f"∠{name}", unit="°", values=phase)

            x_axis = WaveformData(name=var_names[0], unit=_unit_for(var_types[0]), values=data[:, 0])
            return SimulationResult(
                analysis_type=config.analysis_type, success=True,
                x_axis=x_axis, signals=signals,
            )
        else:
            signals = {}
            x_data = data[:, 0]
            x_axis = WaveformData(name=var_names[0], unit=_unit_for(var_types[0]), values=x_data)

            for i in range(1, n_vars):
                name = var_names[i] if i < len(var_names) else f"v{i}"
                unit = _unit_for(var_types[i]) if i < len(var_types) else "V"
                signals[name] = WaveformData(name=name, unit=unit, values=data[:, i])

            return SimulationResult(
                analysis_type=config.analysis_type, success=True,
                x_axis=x_axis, signals=signals,
            )
    else:
        # ASCII values format
        return _parse_ascii_values(data_blob.decode("utf-8", errors="replace"),
                                   var_names, var_types, n_vars, n_points, config)


def _parse_ascii_values(
    text: str,
    var_names: list[str],
    var_types: list[str],
    n_vars: int,
    n_points: int,
    config: AnalysisConfig,
) -> SimulationResult:
    """Parse ASCII 'Values:' section of raw file."""
    columns: dict[int, list[float]] = {i: [] for i in range(n_vars)}
    current_point = -1
    var_idx = 0

    for line in text.splitlines():
        line_s = line.strip()
        if not line_s:
            continue
        # Lines starting with a point index reset the variable counter
        m = re.match(r"^(\d+)\s+([-+\dEe.]+)", line_s)
        if m:
            current_point = int(m.group(1))
            var_idx = 0
            try:
                columns[0].append(float(m.group(2)))
            except ValueError:
                columns[0].append(0.0)
            var_idx = 1
        else:
            # Continuation line with just a value
            try:
                val = float(line_s.split()[0])
            except (ValueError, IndexError):
                val = 0.0
            if var_idx < n_vars:
                columns[var_idx].append(val)
                var_idx += 1

    # Build result
    if not columns[0]:
        return SimulationResult(
            analysis_type=config.analysis_type,
            success=False, error_message="No data parsed from ASCII values",
        )

    x_axis = WaveformData(
        name=var_names[0] if var_names else "x",
        unit=_unit_for(var_types[0]) if var_types else "",
        values=np.array(columns[0]),
    )
    signals: dict[str, WaveformData] = {}
    for i in range(1, n_vars):
        name = var_names[i] if i < len(var_names) else f"v{i}"
        unit = _unit_for(var_types[i]) if i < len(var_types) else "V"
        vals = columns.get(i, [])
        signals[name] = WaveformData(name=name, unit=unit, values=np.array(vals))

    return SimulationResult(
        analysis_type=config.analysis_type, success=True,
        x_axis=x_axis, signals=signals,
    )


def parse_stdout(text: str, config: AnalysisConfig) -> SimulationResult:
    """Parse NgSpice stdout for operating point or print data.

    Falls back on stdout when no .raw file is produced (e.g., for .op).
    """
    if config.analysis_type == "op":
        return _parse_op_stdout(text, config)
    return _parse_print_stdout(text, config)


def _parse_op_stdout(text: str, config: AnalysisConfig) -> SimulationResult:
    """Parse DC operating point from stdout."""
    op = OperatingPoint()

    # NgSpice OP output format:
    # Node                  Voltage
    # ----                  -------
    # v(vcc)                5
    # v(out)                2.5
    # --- or ---
    # V(vcc) = 5.00000e+00
    for line in text.splitlines():
        line_s = line.strip()
        # Pattern: "v(node) = value" or "V(node) = value"
        m = re.match(r"[vV]\((\w+)\)\s*=?\s*([-+\dEe.]+)", line_s)
        if m:
            node = m.group(1)
            try:
                val = float(m.group(2))
                op.node_voltages[node] = val
            except ValueError:
                pass
            continue
        # Pattern: "i(vsource) = value"
        m = re.match(r"[iI]\((\w+)\)\s*=?\s*([-+\dEe.]+)", line_s)
        if m:
            source = m.group(1)
            try:
                val = float(m.group(2))
                op.branch_currents[source] = val
            except ValueError:
                pass

    # Also try tabular format
    in_table = False
    for line in text.splitlines():
        line_s = line.strip()
        if "Node" in line_s and "Voltage" in line_s:
            in_table = True
            continue
        if in_table and line_s.startswith("---"):
            continue
        if in_table and line_s:
            parts = line_s.split()
            if len(parts) >= 2:
                node_name = parts[0]
                # Strip v() wrapper if present
                m = re.match(r"[vV]\((\w+)\)", node_name)
                if m:
                    node_name = m.group(1)
                try:
                    val = float(parts[-1])
                    if node_name not in op.node_voltages:
                        op.node_voltages[node_name] = val
                except ValueError:
                    pass

    success = bool(op.node_voltages or op.branch_currents)
    return SimulationResult(
        analysis_type="op",
        success=success,
        operating_point=op,
        error_message="" if success else "No operating point data found in output",
    )


def _parse_print_stdout(text: str, config: AnalysisConfig) -> SimulationResult:
    """Parse .print output from stdout (tabular data)."""
    # Look for tabular data starting with "Index" header or numbered rows
    columns: list[list[float]] = []
    headers: list[str] = []
    in_data = False

    for line in text.splitlines():
        line_s = line.strip()
        if not line_s or line_s.startswith("*"):
            continue

        # Detect header line
        if "Index" in line_s or re.match(r"^(Index|No\.)\s+", line_s):
            headers = line_s.split()
            columns = [[] for _ in headers]
            in_data = True
            continue
        if line_s.startswith("---"):
            continue

        if in_data:
            parts = line_s.split()
            if parts and re.match(r"^\d+$", parts[0]):
                for i, p in enumerate(parts):
                    if i < len(columns):
                        try:
                            columns[i].append(float(p))
                        except ValueError:
                            columns[i].append(0.0)

    if not columns or len(columns) < 2:
        return SimulationResult(
            analysis_type=config.analysis_type,
            success=False,
            error_message="No tabular data found in output",
        )

    # First column after index is usually the sweep variable
    x_idx = 1
    x_name = headers[x_idx] if x_idx < len(headers) else "x"
    x_axis = WaveformData(name=x_name, unit=_unit_for_name(x_name), values=np.array(columns[x_idx]))

    signals: dict[str, WaveformData] = {}
    for i in range(x_idx + 1, len(columns)):
        name = headers[i] if i < len(headers) else f"v{i}"
        signals[name] = WaveformData(
            name=name, unit=_unit_for_name(name), values=np.array(columns[i]),
        )

    return SimulationResult(
        analysis_type=config.analysis_type, success=True,
        x_axis=x_axis, signals=signals,
    )


def _unit_for(var_type: str) -> str:
    """Map NgSpice variable type to unit string."""
    t = var_type.lower()
    if t in ("time",):
        return "s"
    if t in ("frequency",):
        return "Hz"
    if t in ("voltage",):
        return "V"
    if t in ("current",):
        return "A"
    return ""


def _unit_for_name(name: str) -> str:
    """Guess unit from signal name."""
    lower = name.lower()
    if "time" in lower:
        return "s"
    if lower.startswith("v(") or lower.startswith("v_"):
        return "V"
    if lower.startswith("i(") or lower.startswith("i_"):
        return "A"
    if "freq" in lower:
        return "Hz"
    return ""
