"""Component palette — drag-and-drop tree + search bar for adding components."""

from __future__ import annotations

import json

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLineEdit, QTreeWidget, QTreeWidgetItem,
    QLabel, QFrame,
)
from PySide6.QtCore import Qt, QMimeData, QByteArray
from PySide6.QtGui import QDrag, QColor, QFont, QPalette

from src.pcb.components import ComponentDB
from src.gui.i18n import tr


# ── Default pin templates per category ──
_PIN_TEMPLATES: dict[str, list[dict]] = {
    "resistor":     [{"number": "1", "name": "1", "electrical_type": "passive"},
                     {"number": "2", "name": "2", "electrical_type": "passive"}],
    "capacitor":    [{"number": "1", "name": "+", "electrical_type": "passive"},
                     {"number": "2", "name": "-", "electrical_type": "passive"}],
    "inductor":     [{"number": "1", "name": "1", "electrical_type": "passive"},
                     {"number": "2", "name": "2", "electrical_type": "passive"}],
    "diode":        [{"number": "1", "name": "A", "electrical_type": "passive"},
                     {"number": "2", "name": "K", "electrical_type": "passive"}],
    "led":          [{"number": "1", "name": "A", "electrical_type": "passive"},
                     {"number": "2", "name": "K", "electrical_type": "passive"}],
    "transistor":   [{"number": "1", "name": "B", "electrical_type": "input"},
                     {"number": "2", "name": "C", "electrical_type": "output"},
                     {"number": "3", "name": "E", "electrical_type": "passive"}],
    "mosfet":       [{"number": "1", "name": "G", "electrical_type": "input"},
                     {"number": "2", "name": "D", "electrical_type": "output"},
                     {"number": "3", "name": "S", "electrical_type": "passive"}],
    "regulator":    [{"number": "1", "name": "VIN", "electrical_type": "power_in"},
                     {"number": "2", "name": "GND", "electrical_type": "power_in"},
                     {"number": "3", "name": "VOUT", "electrical_type": "power_out"}],
    "opamp":        [{"number": "1", "name": "OUT", "electrical_type": "output"},
                     {"number": "2", "name": "IN-", "electrical_type": "input"},
                     {"number": "3", "name": "IN+", "electrical_type": "input"},
                     {"number": "4", "name": "V-", "electrical_type": "power_in"},
                     {"number": "5", "name": "V+", "electrical_type": "power_in"}],
    "connector":    [{"number": "1", "name": "1", "electrical_type": "passive"},
                     {"number": "2", "name": "2", "electrical_type": "passive"}],
    "switch":       [{"number": "1", "name": "1", "electrical_type": "passive"},
                     {"number": "2", "name": "2", "electrical_type": "passive"}],
    "fuse":         [{"number": "1", "name": "1", "electrical_type": "passive"},
                     {"number": "2", "name": "2", "electrical_type": "passive"}],
    "crystal":      [{"number": "1", "name": "1", "electrical_type": "passive"},
                     {"number": "2", "name": "2", "electrical_type": "passive"}],
    "sensor":       [{"number": "1", "name": "VCC", "electrical_type": "power_in"},
                     {"number": "2", "name": "GND", "electrical_type": "power_in"},
                     {"number": "3", "name": "OUT", "electrical_type": "output"}],
}

# Category display names / emojis
_CAT_DISPLAY: dict[str, str] = {
    "resistor": "🔧 Resistor",
    "capacitor": "⚡ Capacitor",
    "inductor": "🔄 Inductor",
    "diode": "◀ Diode",
    "led": "💡 LED",
    "transistor": "🔀 Transistor",
    "mosfet": "🔀 MOSFET",
    "regulator": "🔋 Regulator",
    "opamp": "📐 Op-Amp",
    "microcontroller": "🖥 MCU",
    "ic": "📦 IC",
    "connector": "🔌 Connector",
    "crystal": "💎 Crystal",
    "relay": "⚙ Relay",
    "transformer": "🔁 Transformer",
    "fuse": "🛡 Fuse",
    "switch": "🔘 Switch",
    "sensor": "📡 Sensor",
    "other": "📎 Other",
}

MIME_TYPE = "application/x-pcb-component"


class _DragTreeWidget(QTreeWidget):
    """Tree that supports starting a drag from component items."""

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if not item or not item.data(0, Qt.ItemDataRole.UserRole):
            return
        data = item.data(0, Qt.ItemDataRole.UserRole)
        mime = QMimeData()
        mime.setData(MIME_TYPE, QByteArray(json.dumps(data).encode("utf-8")))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)


class ComponentPalette(QWidget):
    """Tree view + search bar for browsing and dragging components."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self._load_components()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # Title
        title = QLabel(tr("palette_title"))
        title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        title.setStyleSheet("color: #e6edf3;")
        layout.addWidget(title)

        # Search bar
        self._search = QLineEdit()
        self._search.setPlaceholderText(tr("palette_search"))
        self._search.setClearButtonEnabled(True)
        self._search.setStyleSheet(
            "QLineEdit { background: #161b22; border: 1px solid #30363d; "
            "border-radius: 4px; padding: 4px 8px; color: #e6edf3; }"
        )
        self._search.textChanged.connect(self._filter)
        layout.addWidget(self._search)

        # Tree
        self._tree = _DragTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setDragEnabled(True)
        self._tree.setDragDropMode(_DragTreeWidget.DragDropMode.DragOnly)
        self._tree.setRootIsDecorated(True)
        self._tree.setAnimated(True)
        self._tree.setStyleSheet(
            "QTreeWidget { background: #0d1117; border: 1px solid #30363d; "
            "border-radius: 4px; color: #e6edf3; }"
            "QTreeWidget::item { padding: 3px 4px; }"
            "QTreeWidget::item:hover { background: #1c2333; }"
            "QTreeWidget::item:selected { background: #1f6feb; }"
            "QTreeWidget::branch { background: #0d1117; }"
        )
        layout.addWidget(self._tree)

    def _load_components(self):
        """Load components from DB into tree, grouped by category."""
        self._tree.clear()
        cat_nodes: dict[str, QTreeWidgetItem] = {}

        try:
            with ComponentDB() as db:
                for cat in sorted(db.all_categories()):
                    display = _CAT_DISPLAY.get(cat, cat.title())
                    node = QTreeWidgetItem([display])
                    node.setFont(0, QFont("Segoe UI", 9, QFont.Weight.Bold))
                    node.setFlags(node.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)
                    cat_nodes[cat] = node
                    self._tree.addTopLevelItem(node)

                    comps = db.search(category=cat, limit=100)
                    for c in comps:
                        child = QTreeWidgetItem([f"  {c['value']}  ({c['package']})"])
                        child.setToolTip(0, c.get("description", ""))
                        pins = _PIN_TEMPLATES.get(cat, [
                            {"number": str(i + 1), "name": str(i + 1),
                             "electrical_type": "passive"}
                            for i in range(c.get("pin_count", 2))
                        ])
                        child.setData(0, Qt.ItemDataRole.UserRole, {
                            "category": cat,
                            "value": c["value"],
                            "package": c.get("package", ""),
                            "ref_prefix": c.get("ref_prefix", "X"),
                            "description": c.get("description", ""),
                            "pin_count": c.get("pin_count", 2),
                            "pins": pins,
                        })
                        node.addChild(child)

                    node.setExpanded(False)
        except Exception:
            pass  # DB may not exist yet

    def _filter(self, text: str):
        """Filter tree items by search text."""
        text = text.lower().strip()
        for i in range(self._tree.topLevelItemCount()):
            cat_item = self._tree.topLevelItem(i)
            any_visible = False
            for j in range(cat_item.childCount()):
                child = cat_item.child(j)
                matches = not text or text in child.text(0).lower()
                child.setHidden(not matches)
                if matches:
                    any_visible = True
            cat_item.setHidden(not any_visible)
            if any_visible and text:
                cat_item.setExpanded(True)

    def retranslate(self):
        """Update text for language changes."""
        # Reload to pick up new translations
        self._load_components()
