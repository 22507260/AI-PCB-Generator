"""Tests for SPICE netlist writer in src/simulation/netlist_writer.py."""

import pytest

from src.ai.schemas import (
    CircuitSpec,
    ComponentCategory,
    ComponentSpec,
    NetSpec,
    PinRef,
    PinSpec,
)
from src.simulation.netlist_writer import (
    SpiceNetlistWriter,
    _detect_voltage,
    _net_to_node,
)
from src.simulation.results import AnalysisConfig


# ── Node name mapping ────────────────────────────────────


class TestNetToNode:
    def test_gnd_maps_to_zero(self):
        assert _net_to_node("GND") == "0"
        assert _net_to_node("gnd") == "0"
        assert _net_to_node("VSS") == "0"
        assert _net_to_node("0") == "0"

    def test_normal_net(self):
        assert _net_to_node("VCC") == "VCC"

    def test_special_chars_sanitized(self):
        result = _net_to_node("NET-1.2")
        assert "-" not in result
        assert "." not in result


# ── Voltage detection from net names ─────────────────────


class TestDetectVoltage:
    def test_vcc(self):
        assert _detect_voltage("VCC") == 5.0

    def test_vdd(self):
        assert _detect_voltage("VDD") == 3.3

    def test_numeric_pattern(self):
        assert _detect_voltage("12V") == 12.0
        assert _detect_voltage("3.3V") == 3.3

    def test_unrecognized_returns_none(self):
        assert _detect_voltage("NET1") is None
        assert _detect_voltage("SIGNAL_A") is None


# ── Netlist generation ───────────────────────────────────


class TestNetlistGeneration:
    @pytest.fixture
    def divider_spec(self):
        return CircuitSpec(
            name="Voltage Divider",
            components=[
                ComponentSpec(
                    ref="R1", value="10k",
                    category=ComponentCategory.RESISTOR,
                    pins=[PinSpec(number="1"), PinSpec(number="2")],
                ),
                ComponentSpec(
                    ref="R2", value="10k",
                    category=ComponentCategory.RESISTOR,
                    pins=[PinSpec(number="1"), PinSpec(number="2")],
                ),
            ],
            nets=[
                NetSpec(name="VCC", connections=[
                    PinRef(ref="R1", pin="1"), PinRef(ref="R2", pin="1"),
                ]),
                NetSpec(name="VOUT", connections=[
                    PinRef(ref="R1", pin="2"), PinRef(ref="R2", pin="2"),
                ]),
            ],
        )

    def test_generate_contains_components(self, divider_spec):
        writer = SpiceNetlistWriter(divider_spec)
        netlist = writer.generate(AnalysisConfig(analysis_type="op"))

        assert "RR1" in netlist
        assert "RR2" in netlist

    def test_generate_contains_analysis(self, divider_spec):
        writer = SpiceNetlistWriter(divider_spec)
        netlist = writer.generate(AnalysisConfig(analysis_type="op"))
        assert ".op" in netlist

    def test_tran_analysis_card(self, divider_spec):
        writer = SpiceNetlistWriter(divider_spec)
        config = AnalysisConfig(
            analysis_type="tran", tran_step=1e-6, tran_stop=1e-3,
        )
        netlist = writer.generate(config)
        assert ".tran" in netlist

    def test_ac_analysis_card(self, divider_spec):
        writer = SpiceNetlistWriter(divider_spec)
        config = AnalysisConfig(
            analysis_type="ac", ac_sweep_type="dec",
            ac_n_points=10, ac_f_start=1.0, ac_f_stop=1e6,
        )
        netlist = writer.generate(config)
        assert ".ac dec" in netlist

    def test_dc_analysis_card(self, divider_spec):
        writer = SpiceNetlistWriter(divider_spec)
        config = AnalysisConfig(
            analysis_type="dc", dc_source="V1",
            dc_start=0, dc_stop=5, dc_step=0.1,
        )
        netlist = writer.generate(config)
        assert ".dc V1" in netlist

    def test_ends_with_dot_end(self, divider_spec):
        writer = SpiceNetlistWriter(divider_spec)
        netlist = writer.generate(AnalysisConfig(analysis_type="op"))
        assert netlist.strip().endswith(".end")

    def test_auto_voltage_source_for_vcc(self, divider_spec):
        writer = SpiceNetlistWriter(divider_spec)
        netlist = writer.generate(AnalysisConfig(analysis_type="op"))
        # VCC should get an auto-generated voltage source
        assert "Vauto_" in netlist or "DC 5" in netlist

    def test_get_all_nodes(self, divider_spec):
        writer = SpiceNetlistWriter(divider_spec)
        writer.generate(AnalysisConfig(analysis_type="op"))
        nodes = writer.get_all_nodes()
        assert "VCC" in nodes
        assert "VOUT" in nodes


class TestComponentCards:
    """Test SPICE card generation for different component categories."""

    def _make_spec(self, comp, nets=None):
        if nets is None:
            nets = [
                NetSpec(name="N1", connections=[
                    PinRef(ref=comp.ref, pin="1"),
                    PinRef(ref=comp.ref, pin="2"),
                ]),
            ]
        return CircuitSpec(name="Test", components=[comp], nets=nets)

    def test_capacitor_card(self):
        spec = self._make_spec(
            ComponentSpec(ref="C1", value="100n", category=ComponentCategory.CAPACITOR,
                          pins=[PinSpec(number="1"), PinSpec(number="2")]),
        )
        writer = SpiceNetlistWriter(spec)
        netlist = writer.generate(AnalysisConfig(analysis_type="op"))
        assert "CC1" in netlist

    def test_inductor_card(self):
        spec = self._make_spec(
            ComponentSpec(ref="L1", value="10m", category=ComponentCategory.INDUCTOR,
                          pins=[PinSpec(number="1"), PinSpec(number="2")]),
        )
        writer = SpiceNetlistWriter(spec)
        netlist = writer.generate(AnalysisConfig(analysis_type="op"))
        assert "LL1" in netlist

    def test_diode_card(self):
        spec = self._make_spec(
            ComponentSpec(ref="D1", value="1N4148", category=ComponentCategory.DIODE,
                          pins=[PinSpec(number="1"), PinSpec(number="2")]),
        )
        writer = SpiceNetlistWriter(spec)
        netlist = writer.generate(AnalysisConfig(analysis_type="op"))
        assert "DD1" in netlist
        assert ".model D1N4148" in netlist

    def test_led_card(self):
        spec = self._make_spec(
            ComponentSpec(ref="D1", value="Red", category=ComponentCategory.LED,
                          pins=[PinSpec(number="1"), PinSpec(number="2")]),
        )
        writer = SpiceNetlistWriter(spec)
        netlist = writer.generate(AnalysisConfig(analysis_type="op"))
        assert "DD1" in netlist
        assert "DLED" in netlist
