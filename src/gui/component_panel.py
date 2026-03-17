"""Component list panel and BOM (Bill of Materials) view."""

from __future__ import annotations

import csv
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
    QTableWidgetItem, QPushButton, QLabel, QHeaderView,
    QFileDialog, QAbstractItemView,
)
from PySide6.QtCore import Qt

from src.ai.schemas import CircuitSpec, ComponentSpec
from src.gui.i18n import tr, Translator
from src.utils.logger import get_logger

log = get_logger("gui.component_panel")


class ComponentPanel(QWidget):
    """Displays components as a table with BOM export capability."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._spec: CircuitSpec | None = None
        self._setup_ui()
        self._retranslate()
        Translator.instance().language_changed.connect(self._retranslate)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Header
        header = QHBoxLayout()
        self._title = QLabel()
        self._title.setObjectName("titleLabel")
        self._title.setStyleSheet("font-size: 14px;")
        header.addWidget(self._title)
        header.addStretch()

        self._count_label = QLabel("")
        self._count_label.setObjectName("subtitleLabel")
        header.addWidget(self._count_label)
        layout.addLayout(header)

        # Table
        self._table = QTableWidget()
        self._table.setColumnCount(7)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)

        h = self._table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)

        layout.addWidget(self._table, 1)

        # Export button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self._export_btn = QPushButton()
        self._export_btn.setObjectName("secondaryButton")
        self._export_btn.setEnabled(False)
        self._export_btn.clicked.connect(self._export_bom)
        btn_layout.addWidget(self._export_btn)
        layout.addLayout(btn_layout)

    def load_circuit(self, spec: CircuitSpec):
        """Populate the table with components from a CircuitSpec."""
        self._spec = spec
        self._table.setRowCount(0)

        for comp in spec.components:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, 0, QTableWidgetItem(comp.ref))
            self._table.setItem(row, 1, QTableWidgetItem(comp.value))
            self._table.setItem(row, 2, QTableWidgetItem(comp.category.value))
            self._table.setItem(row, 3, QTableWidgetItem(comp.package))
            self._table.setItem(row, 4, QTableWidgetItem(str(len(comp.pins))))
            self._table.setItem(row, 5, QTableWidgetItem(comp.description))
            self._table.setItem(row, 6, QTableWidgetItem(comp.manufacturer_pn))

        self._count_label.setText(tr("label_component_count", count=spec.component_count))
        self._export_btn.setEnabled(spec.component_count > 0)

    def _export_bom(self):
        if not self._spec:
            return

        path, _ = QFileDialog.getSaveFileName(
            self, tr("dialog_save_bom"), "bom.csv", tr("file_filter_csv")
        )
        if not path:
            return

        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["Ref", "Value", "Category", "Package", "Pins", "Description", "MPN"])
            for comp in self._spec.components:
                writer.writerow([
                    comp.ref, comp.value, comp.category.value,
                    comp.package, len(comp.pins), comp.description,
                    comp.manufacturer_pn,
                ])

        log.info("BOM exported to %s", path)

    def _retranslate(self):
        """Update all labels to the current language."""
        self._title.setText(tr("title_bom"))
        self._table.setHorizontalHeaderLabels([
            tr("header_ref"), tr("header_value"), tr("header_category"),
            tr("header_package"), tr("header_pins"), tr("header_description"),
            tr("header_mpn"),
        ])
        self._export_btn.setText(tr("button_export_bom"))
        if self._spec:
            self._count_label.setText(
                tr("label_component_count", count=self._spec.component_count)
            )
