"""Convert a CircuitSpec into a SPICE netlist (.cir) string."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from src.simulation.value_parser import parse_value
from src.simulation.results import AnalysisConfig

if TYPE_CHECKING:
    from src.ai.schemas import CircuitSpec, ComponentSpec, NetSpec

log = logging.getLogger(__name__)

# Net names that map to SPICE ground node "0"
_GND_NAMES = {"gnd", "0v", "vss", "gnd_net", "ground", "0"}

# Heuristic voltage detection from net names
_VOLTAGE_MAP: dict[str, float] = {
    "vcc": 5.0,
    "vdd": 3.3,
    "5v": 5.0,
    "3v3": 3.3,
    "3.3v": 3.3,
    "12v": 12.0,
    "9v": 9.0,
    "24v": 24.0,
    "1v8": 1.8,
    "1.8v": 1.8,
    "2v5": 2.5,
    "2.5v": 2.5,
}


def _net_to_node(net_name: str) -> str:
    """Convert a net name to a SPICE node name. GND variants → '0'."""
    lower = net_name.lower().strip()
    if lower in _GND_NAMES:
        return "0"
    # SPICE node names must be alphanumeric / underscored
    safe = re.sub(r"[^a-zA-Z0-9_]", "_", net_name)
    return safe if safe else "n_unknown"


def _detect_voltage(net_name: str) -> float | None:
    """Try to detect a DC voltage from a net name."""
    lower = net_name.lower().strip()
    if lower in _VOLTAGE_MAP:
        return _VOLTAGE_MAP[lower]
    # Try patterns like "15V", "3.3V"
    m = re.match(r"^(\d+(?:\.\d+)?)v$", lower)
    if m:
        return float(m.group(1))
    return None


class SpiceNetlistWriter:
    """Generates a SPICE netlist from a CircuitSpec."""

    def __init__(self, spec: CircuitSpec):
        self._spec = spec
        # Build pin→net mapping: (ref, pin_number) → net_name
        self._pin_net: dict[tuple[str, str], str] = {}
        for net in spec.nets:
            for conn in net.connections:
                self._pin_net[(conn.ref, conn.pin)] = net.name

        # Track which nets have voltage sources assigned
        self._sourced_nets: set[str] = set()
        # Voltage source counter for auto-generated sources
        self._vsrc_count = 0

    def generate(self, config: AnalysisConfig) -> str:
        """Generate a complete SPICE netlist string."""
        lines: list[str] = []
        lines.append(f"* {self._spec.name}")
        lines.append(f"* {self._spec.description}")
        lines.append("")

        # Component cards
        models: list[str] = []
        subcircuits: list[str] = []

        for comp in self._spec.components:
            card, mdl, sub = self._component_card(comp)
            if card:
                lines.append(card)
            if mdl:
                models.append(mdl)
            if sub:
                subcircuits.append(sub)

        # Auto-generate voltage sources for power nets without explicit sources
        auto_vs = self._auto_voltage_sources()
        if auto_vs:
            lines.append("")
            lines.append("* Auto-generated power supplies")
            lines.extend(auto_vs)

        # Models
        if models:
            lines.append("")
            lines.append("* Device models")
            for m in dict.fromkeys(models):  # deduplicate preserving order
                lines.append(m)

        # Subcircuits
        if subcircuits:
            lines.append("")
            for s in dict.fromkeys(subcircuits):
                lines.append(s)

        # Analysis card
        lines.append("")
        lines.append("* Analysis")
        lines.append(self._analysis_card(config))

        # Output requests
        lines.append("")
        lines.append("* Output")
        lines.extend(self._output_cards(config))

        lines.append("")
        lines.append(".end")
        return "\n".join(lines)

    def _get_node(self, ref: str, pin: str) -> str:
        """Get the SPICE node name for a component pin."""
        net_name = self._pin_net.get((ref, pin))
        if net_name:
            return _net_to_node(net_name)
        # Try matching by pin name in component spec
        comp = self._spec.get_component(ref)
        if comp:
            for p in comp.pins:
                if p.name.lower() == pin.lower() or p.number == pin:
                    alt_key = (ref, p.number)
                    net_name = self._pin_net.get(alt_key)
                    if net_name:
                        return _net_to_node(net_name)
        # Unconnected — create a floating node
        return f"nc_{ref}_{pin}"

    def _component_card(
        self, comp: ComponentSpec
    ) -> tuple[str, str, str]:
        """Return (card, model_line, subcircuit) for a component."""
        cat = comp.category.value if hasattr(comp.category, "value") else str(comp.category)
        ref = comp.ref
        val = parse_value(comp.value)

        if cat == "resistor":
            n1 = self._get_node(ref, "1")
            n2 = self._get_node(ref, "2")
            r_val = val if val > 0 else 1e3
            return f"R{ref} {n1} {n2} {r_val:.6g}", "", ""

        if cat == "capacitor":
            n1 = self._get_node(ref, "1")
            n2 = self._get_node(ref, "2")
            c_val = val if val > 0 else 100e-9
            return f"C{ref} {n1} {n2} {c_val:.6g}", "", ""

        if cat == "inductor":
            n1 = self._get_node(ref, "1")
            n2 = self._get_node(ref, "2")
            l_val = val if val > 0 else 1e-3
            return f"L{ref} {n1} {n2} {l_val:.6g}", "", ""

        if cat in ("diode", "led"):
            n1 = self._get_node(ref, "1")  # anode
            n2 = self._get_node(ref, "2")  # cathode
            model = "DLED" if cat == "led" else "D1N4148"
            card = f"D{ref} {n1} {n2} {model}"
            if cat == "led":
                mdl = ".model DLED D(IS=1e-20 N=1.8 RS=5 BV=5)"
            else:
                mdl = ".model D1N4148 D(IS=2.52e-9 RS=0.568 N=1.752 BV=100 IBV=100u)"
            return card, mdl, ""

        if cat == "transistor":
            # NPN BJT: pin1=C, pin2=B, pin3=E (or use names)
            nc = self._get_node(ref, "1")
            nb = self._get_node(ref, "2")
            ne = self._get_node(ref, "3")
            card = f"Q{ref} {nc} {nb} {ne} Q2N2222"
            mdl = ".model Q2N2222 NPN(IS=14.34f BF=255.9 VAF=74.03 RB=10 RC=1 RE=0)"
            return card, mdl, ""

        if cat == "mosfet":
            # NMOS: pin1=D, pin2=G, pin3=S
            nd = self._get_node(ref, "1")
            ng = self._get_node(ref, "2")
            ns = self._get_node(ref, "3")
            card = f"M{ref} {nd} {ng} {ns} {ns} NMOS_DEFAULT W=10u L=1u"
            mdl = ".model NMOS_DEFAULT NMOS(VTO=1.5 KP=2e-3 LAMBDA=0.01)"
            return card, mdl, ""

        if cat == "opamp":
            # Ideal opamp subcircuit: pin1=+in, pin2=-in, pin3=out
            np_node = self._get_node(ref, "1")
            nn_node = self._get_node(ref, "2")
            no_node = self._get_node(ref, "3")
            card = f"X{ref} {np_node} {nn_node} no_conn no_conn {no_node} IDEAL_OPAMP"
            sub = (
                ".subckt IDEAL_OPAMP inp inn vp vn out\n"
                "E1 out 0 inp inn 100000\n"
                "Rout out 0 1e12\n"
                ".ends IDEAL_OPAMP"
            )
            return card, "", sub

        if cat in ("regulator", "ic", "microcontroller", "sensor"):
            # Generic multi-pin: treat as a subcircuit placeholder
            # Just create resistive connections for simulation purposes
            pins = comp.pins or []
            if len(pins) >= 3:
                # Input → Output via resistor, GND connected
                n_in = self._get_node(ref, pins[0].number)
                n_out = self._get_node(ref, pins[1].number if len(pins) > 1 else "2")
                card = f"R{ref}_int {n_in} {n_out} 0.1"
                return card, "", ""
            elif len(pins) == 2:
                n1 = self._get_node(ref, pins[0].number)
                n2 = self._get_node(ref, pins[1].number)
                card = f"R{ref}_int {n1} {n2} 1e6"
                return card, "", ""
            return f"* {ref}: {comp.value} (unmodeled)", "", ""

        if cat == "connector":
            # Connectors with power pins become voltage sources
            card_parts = []
            for pin in comp.pins:
                net_name = self._pin_net.get((ref, pin.number), "")
                v = _detect_voltage(net_name)
                if v is not None and net_name.lower() not in _GND_NAMES:
                    node = _net_to_node(net_name)
                    self._vsrc_count += 1
                    vs_name = f"V{ref}_{pin.number}"
                    card_parts.append(f"{vs_name} {node} 0 DC {v}")
                    self._sourced_nets.add(net_name.lower())
            return "\n".join(card_parts) if card_parts else f"* {ref}: connector (no power)", "", ""

        if cat == "crystal":
            # Model as parallel LC
            n1 = self._get_node(ref, "1")
            n2 = self._get_node(ref, "2")
            freq = val if val > 0 else 16e6
            # f = 1/(2π√(LC)), choose C=10pF → L = 1/(4π²f²C)
            import math
            c_val = 10e-12
            l_val = 1.0 / (4.0 * math.pi**2 * freq**2 * c_val)
            card = f"L{ref}_x {n1} {n2} {l_val:.6g}\nC{ref}_x {n1} {n2} {c_val:.6g}"
            return card, "", ""

        if cat == "relay":
            # Coil as inductor + switch as resistor
            n1 = self._get_node(ref, "1")
            n2 = self._get_node(ref, "2")
            card = f"L{ref}_coil {n1} {n2} 0.05"
            return card, "", ""

        if cat == "fuse":
            n1 = self._get_node(ref, "1")
            n2 = self._get_node(ref, "2")
            card = f"R{ref}_fuse {n1} {n2} 0.01"
            return card, "", ""

        if cat == "switch":
            n1 = self._get_node(ref, "1")
            n2 = self._get_node(ref, "2")
            # Closed switch = low resistance
            card = f"R{ref}_sw {n1} {n2} 0.01"
            return card, "", ""

        if cat == "transformer":
            n1 = self._get_node(ref, "1")
            n2 = self._get_node(ref, "2")
            n3 = self._get_node(ref, "3") if len(comp.pins) > 2 else "nc_sec1"
            n4 = self._get_node(ref, "4") if len(comp.pins) > 3 else "nc_sec2"
            card = (
                f"L{ref}_pri {n1} {n2} 10m\n"
                f"L{ref}_sec {n3} {n4} 10m\n"
                f"K{ref} L{ref}_pri L{ref}_sec 0.99"
            )
            return card, "", ""

        # Fallback: treat as comment
        return f"* {ref}: {comp.value} ({cat} — not modeled)", "", ""

    def _auto_voltage_sources(self) -> list[str]:
        """Generate voltage sources for power nets that have no explicit source."""
        sources: list[str] = []
        seen: set[str] = set()
        for net in self._spec.nets:
            lower = net.name.lower()
            if lower in self._sourced_nets or lower in _GND_NAMES:
                continue
            v = _detect_voltage(net.name)
            if v is not None and lower not in seen:
                seen.add(lower)
                node = _net_to_node(net.name)
                self._vsrc_count += 1
                sources.append(f"Vauto_{self._vsrc_count} {node} 0 DC {v}")
                self._sourced_nets.add(lower)
        return sources

    def _analysis_card(self, config: AnalysisConfig) -> str:
        """Generate the SPICE analysis card."""
        t = config.analysis_type
        if t == "op":
            return ".op"
        if t == "tran":
            return f".tran {config.tran_step:.6g} {config.tran_stop:.6g} {config.tran_start:.6g}"
        if t == "ac":
            return f".ac {config.ac_sweep_type} {config.ac_n_points} {config.ac_f_start:.6g} {config.ac_f_stop:.6g}"
        if t == "dc":
            return f".dc {config.dc_source} {config.dc_start:.6g} {config.dc_stop:.6g} {config.dc_step:.6g}"
        return ".op"

    def _output_cards(self, config: AnalysisConfig) -> list[str]:
        """Generate output request cards."""
        cards: list[str] = []
        # Collect all non-ground nodes
        nodes: set[str] = set()
        for net in self._spec.nets:
            node = _net_to_node(net.name)
            if node != "0":
                nodes.add(node)

        if not nodes:
            return [".print dc v(all)"]

        if config.analysis_type == "op":
            for node in sorted(nodes):
                cards.append(f".print dc v({node})")
        elif config.analysis_type == "tran":
            node_list = " ".join(f"v({n})" for n in sorted(nodes))
            cards.append(f".print tran {node_list}")
        elif config.analysis_type == "ac":
            node_list = " ".join(f"v({n})" for n in sorted(nodes))
            cards.append(f".print ac {node_list}")
        elif config.analysis_type == "dc":
            node_list = " ".join(f"v({n})" for n in sorted(nodes))
            cards.append(f".print dc {node_list}")

        return cards

    def get_voltage_sources(self) -> list[str]:
        """Return a list of all voltage source names in the netlist."""
        sources: list[str] = []
        for comp in self._spec.components:
            cat = comp.category.value if hasattr(comp.category, "value") else str(comp.category)
            if cat == "connector":
                for pin in comp.pins:
                    net_name = self._pin_net.get((comp.ref, pin.number), "")
                    v = _detect_voltage(net_name)
                    if v is not None and net_name.lower() not in _GND_NAMES:
                        sources.append(f"V{comp.ref}_{pin.number}")
        # Auto sources
        for i in range(1, self._vsrc_count + 1):
            sources.append(f"Vauto_{i}")
        return sources

    def get_all_nodes(self) -> list[str]:
        """Return all non-ground SPICE node names."""
        nodes: set[str] = set()
        for net in self._spec.nets:
            node = _net_to_node(net.name)
            if node != "0":
                nodes.add(node)
        return sorted(nodes)
