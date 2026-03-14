"""AI Co-Pilot — ERC, design rule validation & auto-fix suggestions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem,
    QPushButton, QFrame,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor, QIcon

from src.ai.schemas import CircuitSpec, ComponentSpec, NetSpec, PinRef
from src.gui.i18n import tr


# =====================================================================
# ERC violation model
# =====================================================================

class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ERCViolation:
    severity: Severity
    code: str
    message: str
    refs: list[str] = field(default_factory=list)
    auto_fix: str = ""  # description of auto-fix, empty if none
    fix_data: dict = field(default_factory=dict)  # data for auto-fix


# =====================================================================
# ERC Engine
# =====================================================================

_GND_NAMES = {"GND", "VSS", "V-", "0V", "AGND", "DGND"}
_PWR_NAMES = {"VCC", "VDD", "V+", "5V", "3V3", "3.3V", "12V", "VIN", "VOUT",
              "VBAT", "VSYS"} | _GND_NAMES


def run_erc(spec: CircuitSpec | None) -> list[ERCViolation]:
    """Run Electrical Rules Check on the circuit spec."""
    if not spec or not spec.components:
        return []

    violations: list[ERCViolation] = []

    # Build connectivity maps
    pin_to_nets: dict[str, list[str]] = {}  # "R1:1" → [net_names]
    net_pins: dict[str, list[PinRef]] = {}
    # Track all net-connected pin identifiers per component
    comp_connected_pins: dict[str, set[str]] = {}  # ref → {pin_ids (lowered)}
    for net in spec.nets:
        net_pins[net.name] = list(net.connections)
        for conn in net.connections:
            key = f"{conn.ref}:{conn.pin}"
            pin_to_nets.setdefault(key, []).append(net.name)
            comp_connected_pins.setdefault(conn.ref, set()).add(conn.pin.upper())

    comp_map = {c.ref: c for c in spec.components}

    # Common pin name aliases (both directions)
    _PIN_ALIASES: dict[str, set[str]] = {
        "VIN": {"IN", "INPUT", "VIN", "V+", "VS", "VS+", "VCC", "VDD"},
        "VOUT": {"OUT", "OUTPUT", "VOUT", "VO"},
        "GND": {"GND", "VSS", "V-", "VS-", "GROUND", "0V", "AGND", "DGND"},
        "IN": {"VIN", "INPUT", "IN", "V+"},
        "OUT": {"VOUT", "OUTPUT", "OUT"},
    }

    def _pin_connected(ref: str, pin) -> bool:
        """Check if a pin is connected via number, name, or common alias."""
        # Direct key match (number or name)
        if f"{ref}:{pin.number}" in pin_to_nets:
            return True
        if pin.name and f"{ref}:{pin.name}" in pin_to_nets:
            return True

        # Fuzzy match: check if any net-connected pin id for this component
        # matches this pin by alias or containment
        connected = comp_connected_pins.get(ref, set())
        if not connected:
            return False

        pin_ids = {pin.number.upper()}
        if pin.name:
            pin_ids.add(pin.name.upper())

        # Check if any connected id matches or is an alias
        for pid in pin_ids:
            if pid in connected:
                return True
            aliases = _PIN_ALIASES.get(pid, set())
            if aliases & connected:
                return True

        return False

    # ── Check 1: Unconnected pins ──
    for comp in spec.components:
        for pin in comp.pins:
            if _pin_connected(comp.ref, pin):
                continue
            # Power pins MUST be connected
            if pin.electrical_type in ("power_in", "power_out"):
                violations.append(ERCViolation(
                    severity=Severity.ERROR,
                    code="ERC001",
                    message=tr("erc_unconnected_power",
                               ref=comp.ref, pin=pin.name or pin.number),
                    refs=[comp.ref],
                ))
            elif pin.electrical_type in ("input", "output"):
                violations.append(ERCViolation(
                    severity=Severity.WARNING,
                    code="ERC002",
                    message=tr("erc_unconnected_pin",
                               ref=comp.ref, pin=pin.name or pin.number),
                        refs=[comp.ref],
                    ))

    # ── Check 2: LED without current-limiting resistor ──
    for comp in spec.components:
        if comp.category.value != "led":
            continue
        # Check if any net connected to this LED also connects to a resistor
        has_resistor = False
        for pin in comp.pins:
            key = f"{comp.ref}:{pin.number}"
            for net_name in pin_to_nets.get(key, []):
                for conn in net_pins.get(net_name, []):
                    other = comp_map.get(conn.ref)
                    if other and other.category.value == "resistor":
                        has_resistor = True
                        break
                if has_resistor:
                    break
            if has_resistor:
                break
        if not has_resistor:
            violations.append(ERCViolation(
                severity=Severity.WARNING,
                code="ERC003",
                message=tr("erc_led_no_resistor", ref=comp.ref),
                refs=[comp.ref],
                auto_fix=tr("erc_fix_add_resistor"),
            ))

    # ── Check 3: No ground connection ──
    has_gnd = any(n.name.upper() in _GND_NAMES for n in spec.nets)
    if not has_gnd and spec.components:
        violations.append(ERCViolation(
            severity=Severity.ERROR,
            code="ERC004",
            message=tr("erc_no_ground"),
            auto_fix=tr("erc_fix_add_ground"),
        ))

    # ── Check 4: No power source ──
    has_pwr = any(
        n.name.upper() in (_PWR_NAMES - _GND_NAMES) for n in spec.nets
    )
    pwr_components = [c for c in spec.components
                      if c.category.value in ("regulator", "connector")]
    if not has_pwr and not pwr_components:
        violations.append(ERCViolation(
            severity=Severity.WARNING,
            code="ERC005",
            message=tr("erc_no_power"),
        ))

    # ── Check 5: Multiple outputs on same net ──
    for net in spec.nets:
        outputs = []
        for conn in net.connections:
            comp = comp_map.get(conn.ref)
            if not comp:
                continue
            # Connectors are pass-through — they don't drive signals
            if comp.category.value in ("connector", "switch", "fuse"):
                continue
            for pin in comp.pins:
                if pin.number == conn.pin and pin.electrical_type == "output":
                    outputs.append(f"{comp.ref}:{pin.name or pin.number}")
        if len(outputs) > 1:
            violations.append(ERCViolation(
                severity=Severity.ERROR,
                code="ERC006",
                message=tr("erc_multiple_outputs", net=net.name,
                           outputs=", ".join(outputs)),
                refs=[o.split(":")[0] for o in outputs],
            ))

    # ── Check 6: IC/MCU without decoupling capacitor ──
    for comp in spec.components:
        if comp.category.value not in ("ic", "microcontroller", "opamp"):
            continue
        # Check for capacitor on same power net
        power_nets = set()
        for pin in comp.pins:
            if pin.electrical_type in ("power_in", "power_out"):
                key = f"{comp.ref}:{pin.number}"
                for nn in pin_to_nets.get(key, []):
                    power_nets.add(nn)
        has_cap = False
        for nn in power_nets:
            for conn in net_pins.get(nn, []):
                other = comp_map.get(conn.ref)
                if other and other.category.value == "capacitor":
                    has_cap = True
                    break
            if has_cap:
                break
        if not has_cap:
            violations.append(ERCViolation(
                severity=Severity.WARNING,
                code="ERC007",
                message=tr("erc_no_decoupling", ref=comp.ref),
                refs=[comp.ref],
                auto_fix=tr("erc_fix_add_cap"),
            ))

    # ── Check 7: Nets with only one connection ──
    for net in spec.nets:
        if len(net.connections) < 2:
            violations.append(ERCViolation(
                severity=Severity.WARNING,
                code="ERC008",
                message=tr("erc_single_pin_net", net=net.name),
            ))

    return violations


# =====================================================================
# AI Co-Pilot Panel
# =====================================================================

_SEV_ICONS = {
    Severity.ERROR: "❌",
    Severity.WARNING: "⚠️",
    Severity.INFO: "ℹ️",
}

_SEV_COLORS = {
    Severity.ERROR: QColor("#f85149"),
    Severity.WARNING: QColor("#d29922"),
    Severity.INFO: QColor("#58a6ff"),
}


class AICoPilotPanel(QWidget):
    """Panel showing ERC violations and design suggestions."""

    fix_requested = Signal(object)  # emits ERCViolation
    component_highlight = Signal(str)  # emits component ref to highlight

    def __init__(self, parent=None):
        super().__init__(parent)
        self._violations: list[ERCViolation] = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        # Header
        header = QHBoxLayout()
        self._title = QLabel(tr("copilot_title"))
        self._title.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self._title.setStyleSheet("color: #e6edf3;")
        header.addWidget(self._title)

        header.addStretch()

        self._btn_run = QPushButton(tr("copilot_run_erc"))
        self._btn_run.setStyleSheet(
            "QPushButton { background: #238636; color: white; border: none; "
            "border-radius: 4px; padding: 3px 10px; font-size: 11px; }"
            "QPushButton:hover { background: #2ea043; }"
        )
        self._btn_run.clicked.connect(self._on_run_clicked)
        header.addWidget(self._btn_run)

        layout.addLayout(header)

        # Status bar
        self._status = QLabel("")
        self._status.setStyleSheet("color: #8b949e; font-size: 11px;")
        layout.addWidget(self._status)

        # Violations tree
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(False)
        self._tree.setStyleSheet(
            "QTreeWidget { background: #0d1117; border: 1px solid #30363d; "
            "border-radius: 4px; color: #e6edf3; font-size: 11px; }"
            "QTreeWidget::item { padding: 3px 4px; }"
            "QTreeWidget::item:hover { background: #1c2333; }"
            "QTreeWidget::item:selected { background: #1f6feb; }"
        )
        self._tree.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._tree)

    def _on_run_clicked(self):
        """Re-run ERC from button click."""
        if hasattr(self, "_spec"):
            self.run_erc(self._spec)

    def _on_item_clicked(self, item: QTreeWidgetItem, col: int):
        """Highlight the component referenced in the violation."""
        idx = item.data(0, Qt.ItemDataRole.UserRole)
        if idx is not None and 0 <= idx < len(self._violations):
            v = self._violations[idx]
            if v.refs:
                self.component_highlight.emit(v.refs[0])

    def run_erc(self, spec: CircuitSpec | None):
        """Run ERC and update the violations display."""
        self._spec = spec
        self._violations = run_erc(spec)
        self._update_display()

    def _update_display(self):
        self._tree.clear()
        errors = sum(1 for v in self._violations if v.severity == Severity.ERROR)
        warnings = sum(1 for v in self._violations if v.severity == Severity.WARNING)

        if not self._violations:
            self._status.setText(tr("copilot_no_issues"))
            self._status.setStyleSheet("color: #3fb950; font-size: 11px;")
            return

        self._status.setText(
            tr("copilot_issues_found", errors=errors, warnings=warnings)
        )
        self._status.setStyleSheet("color: #d29922; font-size: 11px;")

        for i, v in enumerate(self._violations):
            icon = _SEV_ICONS.get(v.severity, "")
            text = f"{icon} [{v.code}] {v.message}"
            if v.auto_fix:
                text += f"  💡 {v.auto_fix}"
            item = QTreeWidgetItem([text])
            item.setForeground(0, _SEV_COLORS.get(v.severity, QColor("#e6edf3")))
            item.setData(0, Qt.ItemDataRole.UserRole, i)
            self._tree.addTopLevelItem(item)

    def retranslate(self):
        self._title.setText(tr("copilot_title"))
        self._btn_run.setText(tr("copilot_run_erc"))
        if hasattr(self, "_spec"):
            self.run_erc(self._spec)
