"""Tests for SPICE Python solver in src/simulation/python_solver.py."""

import math

import numpy as np
import pytest

from src.simulation.python_solver import PythonSolver, _parse_num
from src.simulation.results import AnalysisConfig


# ── SI suffix parser ─────────────────────────────────────


class TestParseNum:
    def test_plain_integer(self):
        assert _parse_num("100") == 100.0

    def test_plain_float(self):
        assert abs(_parse_num("3.14") - 3.14) < 1e-10

    def test_kilo(self):
        assert _parse_num("10k") == 10_000.0

    def test_meg(self):
        assert _parse_num("1meg") == 1e6

    def test_micro(self):
        assert abs(_parse_num("100u") - 100e-6) < 1e-15

    def test_nano(self):
        assert abs(_parse_num("100n") - 100e-9) < 1e-18

    def test_pico(self):
        assert abs(_parse_num("10p") - 10e-12) < 1e-21

    def test_milli(self):
        assert abs(_parse_num("4.7m") - 4.7e-3) < 1e-12

    def test_giga(self):
        assert _parse_num("1g") == 1e9

    def test_invalid_returns_zero(self):
        assert _parse_num("abc") == 0.0

    def test_empty_returns_zero(self):
        assert _parse_num("") == 0.0


# ── DC Operating Point ───────────────────────────────────


class TestDCOp:
    def test_voltage_divider(self, voltage_divider_netlist, dc_op_config):
        solver = PythonSolver()
        result = solver.solve(voltage_divider_netlist, dc_op_config)

        assert result.success, f"Solver failed: {result.error_message}"
        assert result.analysis_type == "op"
        assert result.engine_used == "built-in"
        assert result.operating_point is not None

        # V(vin) should be 10V, V(vout) should be 5V (equal resistor divider)
        op = result.operating_point
        assert abs(op.node_voltages.get("vin", 0) - 10.0) < 0.1
        assert abs(op.node_voltages.get("vout", 0) - 5.0) < 0.1

    def test_rc_circuit_op(self, rc_netlist, dc_op_config):
        solver = PythonSolver()
        result = solver.solve(rc_netlist, dc_op_config)

        assert result.success
        op = result.operating_point
        # At DC, capacitor is open → V(out) = V(in) = 5V through R
        assert abs(op.node_voltages.get("out", 0) - 5.0) < 0.5


# ── Transient Analysis ───────────────────────────────────


class TestTransient:
    def test_rc_transient_produces_waveforms(self, rc_netlist, tran_config):
        solver = PythonSolver()
        result = solver.solve(rc_netlist, tran_config)

        assert result.success, f"Solver failed: {result.error_message}"
        assert result.analysis_type == "tran"
        assert result.x_axis is not None
        assert result.x_axis.values.size > 0
        assert len(result.signals) > 0

    def test_rc_transient_settles(self, rc_netlist):
        """RC circuit should settle near supply voltage after 5*RC."""
        config = AnalysisConfig(analysis_type="tran", tran_step=1e-5, tran_stop=1e-2)
        solver = PythonSolver()
        result = solver.solve(rc_netlist, config)

        assert result.success
        # After 10ms (10× RC=0.1ms), V(out) should be close to 5V
        for name, sig in result.signals.items():
            if "out" in name.lower():
                assert sig.values[-1] > 4.5, f"Signal {name} did not settle: {sig.values[-1]}"


# ── DC Sweep ─────────────────────────────────────────────


class TestDCSweep:
    def test_dc_sweep_produces_data(self, voltage_divider_netlist):
        config = AnalysisConfig(
            analysis_type="dc",
            dc_source="V1",
            dc_start=0, dc_stop=10, dc_step=1,
        )
        solver = PythonSolver()
        result = solver.solve(voltage_divider_netlist, config)

        assert result.success, f"Solver failed: {result.error_message}"
        assert result.x_axis is not None
        assert result.x_axis.values.size >= 10


# ── AC Sweep ─────────────────────────────────────────────


class TestACSweep:
    def test_ac_sweep_produces_data(self):
        netlist = (
            "* RC LPF for AC\n"
            "V1 in 0 DC 5 AC 1\n"
            "R1 in out 1k\n"
            "C1 out 0 100n\n"
            ".end\n"
        )
        config = AnalysisConfig(
            analysis_type="ac",
            ac_sweep_type="dec",
            ac_n_points=5,
            ac_f_start=10,
            ac_f_stop=1e6,
        )
        solver = PythonSolver()
        result = solver.solve(netlist, config)

        assert result.success, f"Solver failed: {result.error_message}"
        assert result.x_axis is not None
        assert len(result.signals) > 0


# ── Error handling ───────────────────────────────────────


class TestSolverErrors:
    def test_unknown_analysis_type(self, rc_netlist):
        config = AnalysisConfig(analysis_type="weird")
        solver = PythonSolver()
        result = solver.solve(rc_netlist, config)

        assert not result.success
        assert "Unknown analysis type" in result.error_message

    def test_empty_netlist(self, dc_op_config):
        solver = PythonSolver()
        result = solver.solve("* Empty\n.end", dc_op_config)
        # Should handle gracefully (may still succeed with no nodes)
        assert result.engine_used == "built-in"
