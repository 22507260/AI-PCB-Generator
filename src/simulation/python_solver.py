"""Pure-Python MNA (Modified Nodal Analysis) SPICE solver.

Fallback when NgSpice is not installed. Supports:
  - DC Operating Point
  - Transient Analysis (Backward Euler for C/L)
  - DC Sweep
  - AC Sweep (complex MNA)
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass, field

import numpy as np

from src.simulation.results import (
    AnalysisConfig,
    OperatingPoint,
    SimulationResult,
    WaveformData,
)

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Netlist element dataclasses
# ---------------------------------------------------------------------------

@dataclass
class _Resistor:
    name: str
    n1: str
    n2: str
    value: float  # Ohms


@dataclass
class _Capacitor:
    name: str
    n1: str
    n2: str
    value: float  # Farads


@dataclass
class _Inductor:
    name: str
    n1: str
    n2: str
    value: float  # Henrys


@dataclass
class _VSource:
    name: str
    n_pos: str
    n_neg: str
    dc_value: float = 0.0
    ac_mag: float = 0.0
    ac_phase: float = 0.0


@dataclass
class _Diode:
    name: str
    n_anode: str
    n_cathode: str
    is_val: float = 1e-14
    n_factor: float = 1.0
    rs: float = 0.0


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _parse_netlist(netlist: str):
    """Parse a SPICE netlist string into element lists."""
    resistors: list[_Resistor] = []
    capacitors: list[_Capacitor] = []
    inductors: list[_Inductor] = []
    vsources: list[_VSource] = []
    diodes: list[_Diode] = []
    models: dict[str, dict] = {}

    for line in netlist.splitlines():
        line = line.strip()
        if not line or line.startswith("*") or line.startswith("."):
            # Parse .model lines for diode parameters
            if line.lower().startswith(".model"):
                _parse_model(line, models)
            continue

        parts = line.split()
        if len(parts) < 3:
            continue

        first = parts[0].upper()

        if first.startswith("R"):
            val = _parse_num(parts[3]) if len(parts) > 3 else 1e3
            resistors.append(_Resistor(parts[0], parts[1], parts[2], max(val, 1e-9)))

        elif first.startswith("C"):
            val = _parse_num(parts[3]) if len(parts) > 3 else 100e-9
            capacitors.append(_Capacitor(parts[0], parts[1], parts[2], max(val, 1e-15)))

        elif first.startswith("L"):
            val = _parse_num(parts[3]) if len(parts) > 3 else 1e-3
            inductors.append(_Inductor(parts[0], parts[1], parts[2], max(val, 1e-12)))

        elif first.startswith("V"):
            dc_val = 0.0
            ac_mag = 0.0
            for i, p in enumerate(parts[3:], 3):
                if p.upper() == "DC" and i + 1 < len(parts):
                    dc_val = _parse_num(parts[i + 1])
                elif p.upper() == "AC" and i + 1 < len(parts):
                    ac_mag = _parse_num(parts[i + 1])
                elif i == 3 and re.match(r"^[+-]?\d", p):
                    dc_val = _parse_num(p)
            vsources.append(_VSource(parts[0], parts[1], parts[2], dc_val, ac_mag))

        elif first.startswith("D"):
            diodes.append(_Diode(parts[0], parts[1], parts[2]))

    return resistors, capacitors, inductors, vsources, diodes


def _parse_model(line: str, models: dict):
    """Parse a .model line (simplified)."""
    # .model NAME TYPE(params...)
    m = re.match(r"\.model\s+(\S+)\s+(\S+)\s*\(([^)]*)\)", line, re.IGNORECASE)
    if m:
        name, mtype, params_str = m.groups()
        params = {}
        for pair in re.findall(r"(\w+)\s*=\s*([\d.eE+-]+)", params_str):
            params[pair[0].upper()] = float(pair[1])
        models[name.upper()] = {"type": mtype.upper(), **params}


def _parse_num(s: str) -> float:
    """Parse a numeric string with optional SI suffix."""
    s = s.strip().rstrip(")")
    # Remove unit suffixes
    s = re.sub(r"[ΩFHVAWHz]+$", "", s, flags=re.IGNORECASE)

    suffixes = {
        "f": 1e-15, "p": 1e-12, "n": 1e-9, "u": 1e-6,
        "m": 1e-3, "k": 1e3, "meg": 1e6, "g": 1e9, "t": 1e12,
    }
    lower = s.lower()
    for sfx, mult in sorted(suffixes.items(), key=lambda x: -len(x[0])):
        if lower.endswith(sfx):
            try:
                return float(s[:len(s) - len(sfx)]) * mult
            except ValueError:
                return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


# ---------------------------------------------------------------------------
# MNA solver
# ---------------------------------------------------------------------------

class PythonSolver:
    """Pure-Python MNA circuit solver."""

    def solve(self, netlist: str, config: AnalysisConfig) -> SimulationResult:
        """Run simulation on a SPICE netlist string."""
        try:
            resistors, capacitors, inductors, vsources, diodes = _parse_netlist(netlist)

            if config.analysis_type == "op":
                return self._solve_dc_op(resistors, capacitors, inductors, vsources, diodes)
            elif config.analysis_type == "tran":
                return self._solve_tran(resistors, capacitors, inductors, vsources, diodes, config)
            elif config.analysis_type == "dc":
                return self._solve_dc_sweep(resistors, capacitors, inductors, vsources, diodes, config)
            elif config.analysis_type == "ac":
                return self._solve_ac(resistors, capacitors, inductors, vsources, diodes, config)
            else:
                return SimulationResult(
                    analysis_type=config.analysis_type,
                    success=False,
                    error_message=f"Unknown analysis type: {config.analysis_type}",
                    engine_used="built-in",
                )
        except Exception as e:
            log.exception("Python solver error")
            return SimulationResult(
                analysis_type=config.analysis_type,
                success=False,
                error_message=str(e),
                engine_used="built-in",
            )

    # ----- node mapping -----

    def _build_node_map(self, *element_lists) -> tuple[dict[str, int], int]:
        """Collect all unique node names, assign indices (ground = excluded)."""
        nodes: set[str] = set()
        for elist in element_lists:
            for elem in elist:
                for attr in ("n1", "n2", "n_pos", "n_neg", "n_anode", "n_cathode"):
                    n = getattr(elem, attr, None)
                    if n and n != "0":
                        nodes.add(n)
        node_map = {n: i for i, n in enumerate(sorted(nodes))}
        return node_map, len(node_map)

    def _idx(self, node_map: dict[str, int], name: str) -> int | None:
        """Return matrix index for a node, or None for ground."""
        if name == "0":
            return None
        return node_map.get(name)

    # ----- DC Operating Point -----

    def _solve_dc_op(self, R, C, L, V, D) -> SimulationResult:
        node_map, n = self._build_node_map(R, C, L, V, D)
        if n == 0:
            return SimulationResult(
                analysis_type="op", success=False,
                error_message="No nodes found in circuit",
                engine_used="built-in",
            )

        nv = len(V)  # number of voltage sources
        size = n + nv

        G = np.zeros((size, size), dtype=float)
        s = np.zeros(size, dtype=float)

        # Stamp resistors
        for r in R:
            g = 1.0 / r.value
            i1 = self._idx(node_map, r.n1)
            i2 = self._idx(node_map, r.n2)
            if i1 is not None:
                G[i1, i1] += g
            if i2 is not None:
                G[i2, i2] += g
            if i1 is not None and i2 is not None:
                G[i1, i2] -= g
                G[i2, i1] -= g

        # Stamp voltage sources (extra MNA rows)
        for k, vs in enumerate(V):
            row = n + k
            ip = self._idx(node_map, vs.n_pos)
            im = self._idx(node_map, vs.n_neg)
            if ip is not None:
                G[ip, row] += 1.0
                G[row, ip] += 1.0
            if im is not None:
                G[im, row] -= 1.0
                G[row, im] -= 1.0
            s[row] = vs.dc_value

        # Stamp diodes as linearized (initial guess: Vd=0.65V, gd=Is/Vt)
        vt = 0.026  # thermal voltage at 300K
        for d in D:
            ia = self._idx(node_map, d.n_anode)
            ic = self._idx(node_map, d.n_cathode)
            vd_guess = 0.65
            id_guess = d.is_val * (math.exp(vd_guess / (d.n_factor * vt)) - 1)
            gd = id_guess / (d.n_factor * vt)
            ieq = id_guess - gd * vd_guess
            if ia is not None:
                G[ia, ia] += gd
                s[ia] -= ieq
            if ic is not None:
                G[ic, ic] += gd
                s[ic] += ieq
            if ia is not None and ic is not None:
                G[ia, ic] -= gd
                G[ic, ia] -= gd

        # Solve
        try:
            x = np.linalg.solve(G, s)
        except np.linalg.LinAlgError:
            # Singular matrix — add small conductance to ground
            for i in range(n):
                G[i, i] += 1e-12
            try:
                x = np.linalg.solve(G, s)
            except np.linalg.LinAlgError:
                return SimulationResult(
                    analysis_type="op", success=False,
                    error_message="Singular matrix — circuit may be disconnected",
                    engine_used="built-in",
                )

        # Extract results
        op = OperatingPoint()
        for name, idx in node_map.items():
            op.node_voltages[name] = float(x[idx])
        for k, vs in enumerate(V):
            op.branch_currents[vs.name] = float(x[n + k])

        return SimulationResult(
            analysis_type="op", success=True,
            operating_point=op, engine_used="built-in",
        )

    # ----- Transient Analysis -----

    def _solve_tran(self, R, C, L, V, D, config: AnalysisConfig) -> SimulationResult:
        node_map, n = self._build_node_map(R, C, L, V, D)
        if n == 0:
            return SimulationResult(
                analysis_type="tran", success=False,
                error_message="No nodes found", engine_used="built-in",
            )

        nv = len(V)
        nl = len(L)
        size = n + nv + nl

        dt = config.tran_step
        t_stop = config.tran_stop
        t_start = config.tran_start
        n_steps = int((t_stop - t_start) / dt) + 1
        # Limit to reasonable number of points
        if n_steps > 50000:
            dt = (t_stop - t_start) / 50000
            n_steps = 50001

        # Time array
        times = np.linspace(t_start, t_stop, n_steps)

        # Storage for all node voltages over time
        history: dict[str, list[float]] = {name: [] for name in node_map}

        # Previous voltage state (for capacitor companion model)
        v_prev = np.zeros(size, dtype=float)

        for step_i in range(n_steps):
            t = times[step_i]

            G = np.zeros((size, size), dtype=float)
            s = np.zeros(size, dtype=float)

            # Stamp resistors
            for r in R:
                g = 1.0 / r.value
                i1 = self._idx(node_map, r.n1)
                i2 = self._idx(node_map, r.n2)
                if i1 is not None:
                    G[i1, i1] += g
                if i2 is not None:
                    G[i2, i2] += g
                if i1 is not None and i2 is not None:
                    G[i1, i2] -= g
                    G[i2, i1] -= g

            # Stamp capacitors (Backward Euler: Geq = C/dt, Ieq = C/dt * v_prev)
            for c in C:
                geq = c.value / dt
                i1 = self._idx(node_map, c.n1)
                i2 = self._idx(node_map, c.n2)
                v1_prev = v_prev[i1] if i1 is not None else 0.0
                v2_prev = v_prev[i2] if i2 is not None else 0.0
                ieq = geq * (v1_prev - v2_prev)
                if i1 is not None:
                    G[i1, i1] += geq
                    s[i1] += ieq
                if i2 is not None:
                    G[i2, i2] += geq
                    s[i2] -= ieq
                if i1 is not None and i2 is not None:
                    G[i1, i2] -= geq
                    G[i2, i1] -= geq

            # Stamp voltage sources
            for k, vs in enumerate(V):
                row = n + k
                ip = self._idx(node_map, vs.n_pos)
                im = self._idx(node_map, vs.n_neg)
                if ip is not None:
                    G[ip, row] += 1.0
                    G[row, ip] += 1.0
                if im is not None:
                    G[im, row] -= 1.0
                    G[row, im] -= 1.0
                s[row] = vs.dc_value

            # Stamp inductors (Backward Euler: treat as voltage source)
            for k, l_elem in enumerate(L):
                row = n + nv + k
                i1 = self._idx(node_map, l_elem.n1)
                i2 = self._idx(node_map, l_elem.n2)
                req = l_elem.value / dt
                # Companion: V_L = L/dt * I_prev, stamp as voltage source with series R
                # Simplified: stamp as resistor with R = L/dt
                if i1 is not None:
                    G[i1, i1] += 1.0 / req
                if i2 is not None:
                    G[i2, i2] += 1.0 / req
                if i1 is not None and i2 is not None:
                    G[i1, i2] -= 1.0 / req
                    G[i2, i1] -= 1.0 / req

            # Solve
            try:
                x = np.linalg.solve(G, s)
            except np.linalg.LinAlgError:
                for i in range(n):
                    G[i, i] += 1e-12
                x = np.linalg.solve(G, s)

            # Record
            for name, idx in node_map.items():
                history[name].append(float(x[idx]))

            v_prev = x.copy()

        # Build result
        x_axis = WaveformData(name="time", unit="s", values=times)
        signals: dict[str, WaveformData] = {}
        for name, vals in history.items():
            signals[f"v({name})"] = WaveformData(
                name=f"v({name})", unit="V", values=np.array(vals),
            )

        return SimulationResult(
            analysis_type="tran", success=True,
            x_axis=x_axis, signals=signals, engine_used="built-in",
        )

    # ----- DC Sweep -----

    def _solve_dc_sweep(self, R, C, L, V, D, config: AnalysisConfig) -> SimulationResult:
        src_name = config.dc_source.upper()
        src_idx = None
        for i, vs in enumerate(V):
            if vs.name.upper() == src_name:
                src_idx = i
                break

        if src_idx is None:
            return SimulationResult(
                analysis_type="dc", success=False,
                error_message=f"Source '{config.dc_source}' not found",
                engine_used="built-in",
            )

        node_map, n = self._build_node_map(R, C, L, V, D)
        sweep_vals = np.arange(config.dc_start, config.dc_stop + config.dc_step / 2, config.dc_step)

        history: dict[str, list[float]] = {name: [] for name in node_map}

        for sv in sweep_vals:
            V[src_idx].dc_value = sv
            result = self._solve_dc_op(R, C, L, V, D)
            if result.success and result.operating_point:
                for name in node_map:
                    history[name].append(result.operating_point.node_voltages.get(name, 0.0))
            else:
                for name in node_map:
                    history[name].append(0.0)

        x_axis = WaveformData(name=config.dc_source, unit="V", values=sweep_vals)
        signals: dict[str, WaveformData] = {}
        for name, vals in history.items():
            signals[f"v({name})"] = WaveformData(
                name=f"v({name})", unit="V", values=np.array(vals),
            )

        return SimulationResult(
            analysis_type="dc", success=True,
            x_axis=x_axis, signals=signals, engine_used="built-in",
        )

    # ----- AC Analysis -----

    def _solve_ac(self, R, C, L, V, D, config: AnalysisConfig) -> SimulationResult:
        """AC small-signal analysis using complex MNA."""
        node_map, n = self._build_node_map(R, C, L, V, D)
        if n == 0:
            return SimulationResult(
                analysis_type="ac", success=False,
                error_message="No nodes found", engine_used="built-in",
            )

        nv = len(V)
        size = n + nv

        # Build frequency array
        if config.ac_sweep_type == "lin":
            freqs = np.linspace(config.ac_f_start, config.ac_f_stop, config.ac_n_points)
        elif config.ac_sweep_type == "oct":
            n_oct = math.log2(config.ac_f_stop / config.ac_f_start)
            freqs = np.geomspace(config.ac_f_start, config.ac_f_stop, int(n_oct * config.ac_n_points) + 1)
        else:  # dec
            freqs = np.geomspace(config.ac_f_start, config.ac_f_stop, config.ac_n_points)

        history_mag: dict[str, list[float]] = {name: [] for name in node_map}
        history_phase: dict[str, list[float]] = {name: [] for name in node_map}

        for freq in freqs:
            omega = 2.0 * math.pi * freq
            G = np.zeros((size, size), dtype=complex)
            s = np.zeros(size, dtype=complex)

            # Resistors
            for r in R:
                g = 1.0 / r.value
                i1 = self._idx(node_map, r.n1)
                i2 = self._idx(node_map, r.n2)
                if i1 is not None:
                    G[i1, i1] += g
                if i2 is not None:
                    G[i2, i2] += g
                if i1 is not None and i2 is not None:
                    G[i1, i2] -= g
                    G[i2, i1] -= g

            # Capacitors: Y = jωC
            for c in C:
                yc = 1j * omega * c.value
                i1 = self._idx(node_map, c.n1)
                i2 = self._idx(node_map, c.n2)
                if i1 is not None:
                    G[i1, i1] += yc
                if i2 is not None:
                    G[i2, i2] += yc
                if i1 is not None and i2 is not None:
                    G[i1, i2] -= yc
                    G[i2, i1] -= yc

            # Inductors: Y = 1/(jωL)
            for l_elem in L:
                yl = 1.0 / (1j * omega * l_elem.value) if omega > 0 else 1e12
                i1 = self._idx(node_map, l_elem.n1)
                i2 = self._idx(node_map, l_elem.n2)
                if i1 is not None:
                    G[i1, i1] += yl
                if i2 is not None:
                    G[i2, i2] += yl
                if i1 is not None and i2 is not None:
                    G[i1, i2] -= yl
                    G[i2, i1] -= yl

            # Voltage sources
            for k, vs in enumerate(V):
                row = n + k
                ip = self._idx(node_map, vs.n_pos)
                im = self._idx(node_map, vs.n_neg)
                if ip is not None:
                    G[ip, row] += 1.0
                    G[row, ip] += 1.0
                if im is not None:
                    G[im, row] -= 1.0
                    G[row, im] -= 1.0
                # AC source magnitude
                if vs.ac_mag > 0:
                    phase_rad = math.radians(vs.ac_phase)
                    s[row] = vs.ac_mag * (math.cos(phase_rad) + 1j * math.sin(phase_rad))

            try:
                x = np.linalg.solve(G, s)
            except np.linalg.LinAlgError:
                for i in range(n):
                    G[i, i] += 1e-12
                x = np.linalg.solve(G, s)

            for name, idx in node_map.items():
                v_complex = x[idx]
                mag_db = 20 * math.log10(abs(v_complex)) if abs(v_complex) > 1e-30 else -300
                phase_deg = math.degrees(math.atan2(v_complex.imag, v_complex.real))
                history_mag[name].append(mag_db)
                history_phase[name].append(phase_deg)

        x_axis = WaveformData(name="frequency", unit="Hz", values=freqs)
        signals: dict[str, WaveformData] = {}
        for name in node_map:
            signals[f"|v({name})|"] = WaveformData(
                name=f"|v({name})|", unit="dB", values=np.array(history_mag[name]),
            )
            signals[f"∠v({name})"] = WaveformData(
                name=f"∠v({name})", unit="°", values=np.array(history_phase[name]),
            )

        return SimulationResult(
            analysis_type="ac", success=True,
            x_axis=x_axis, signals=signals, engine_used="built-in",
        )
