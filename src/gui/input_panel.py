"""AI input panel — natural language circuit description entry."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
    QPushButton, QLabel, QComboBox, QProgressBar, QMessageBox,
)
from PySide6.QtCore import Qt, Signal, QThread

from src.gui.i18n import tr, Translator
from src.gui.theme import tc


class AIWorker(QThread):
    """Background thread for AI circuit generation."""

    finished = Signal(object, object)   # CircuitSpec, validation warnings
    error = Signal(str)         # Error message
    progress = Signal(str)      # Status text

    def __init__(self, description: str, parent=None):
        super().__init__(parent)
        self._description = description

    def run(self):
        try:
            self.progress.emit(tr("progress_engine_start"))
            from src.ai.client import AIClient, AIClientError
            from src.ai.parser import validate_circuit

            client = AIClient()
            self.progress.emit(tr("progress_designing"))
            spec = client.generate_circuit(self._description)

            self.progress.emit(tr("progress_validating"))
            validated, warnings = validate_circuit(spec)

            self.finished.emit(validated, warnings)
        except AIClientError as e:
            self.error.emit(str(e))
        except Exception as e:
            self.error.emit(tr("error_unexpected", error=e))


class InputPanel(QWidget):
    """Left panel with text area for circuit description and generate button."""

    circuit_generated = Signal(object)   # Emits CircuitSpec
    status_message = Signal(str)

    # Template keys map to i18n keys
    _TEMPLATE_KEYS = [
        ("tpl_empty", ""),
        ("tpl_led", "tpl_led_desc"),
        ("tpl_vreg", "tpl_vreg_desc"),
        ("tpl_arduino", "tpl_arduino_desc"),
        ("tpl_sensor", "tpl_sensor_desc"),
        ("tpl_motor", "tpl_motor_desc"),
        ("tpl_usbc", "tpl_usbc_desc"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: AIWorker | None = None
        self._setup_ui()
        self._retranslate()
        Translator.instance().language_changed.connect(self._retranslate)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Title
        self._title = QLabel()
        self._title.setObjectName("titleLabel")
        layout.addWidget(self._title)

        self._subtitle = QLabel()
        self._subtitle.setObjectName("subtitleLabel")
        self._subtitle.setWordWrap(True)
        layout.addWidget(self._subtitle)

        # Template selector
        tmpl_layout = QHBoxLayout()
        self._tmpl_label = QLabel()
        self._template_combo = QComboBox()
        self._template_combo.currentIndexChanged.connect(self._on_template_selected)
        tmpl_layout.addWidget(self._tmpl_label)
        tmpl_layout.addWidget(self._template_combo, 1)
        layout.addLayout(tmpl_layout)

        # Text input
        self._text_edit = QTextEdit()
        self._text_edit.setMinimumHeight(150)
        layout.addWidget(self._text_edit, 1)

        # Buttons
        btn_layout = QHBoxLayout()
        self._generate_btn = QPushButton()
        self._generate_btn.setMinimumHeight(40)
        self._generate_btn.clicked.connect(self._on_generate)

        self._clear_btn = QPushButton()
        self._clear_btn.setObjectName("secondaryButton")
        self._clear_btn.clicked.connect(self._text_edit.clear)

        btn_layout.addWidget(self._clear_btn)
        btn_layout.addWidget(self._generate_btn, 1)
        layout.addLayout(btn_layout)

        # Progress
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)  # Indeterminate
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)

        self._status_label = QLabel("")
        self._status_label.setObjectName("subtitleLabel")
        self._status_label.setWordWrap(True)
        layout.addWidget(self._status_label)

        self._warnings_label = QLabel("")
        self._warnings_label.setWordWrap(True)
        self._warnings_label.setVisible(False)
        layout.addWidget(self._warnings_label)

    # ------------------------------------------------------------------

    def _on_template_selected(self, index: int):
        if index <= 0 or index >= len(self._TEMPLATE_KEYS):
            return
        desc_key = self._TEMPLATE_KEYS[index][1]
        if desc_key:
            self._text_edit.setPlainText(tr(desc_key))

    def _on_generate(self):
        description = self._text_edit.toPlainText().strip()
        if not description:
            self._status_label.setText(tr("warning_enter_desc"))
            self._status_label.setObjectName("warningLabel")
            self._status_label.setStyleSheet(f"color: {tc().warning};")
            return

        self._set_busy(True)
        self._status_label.setText(tr("status_starting_ai"))
        self._status_label.setStyleSheet(f"color: {tc().text_dim};")
        self._warnings_label.setVisible(False)
        self._warnings_label.setText("")

        self._worker = AIWorker(description)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.progress.connect(self._on_progress)
        self._worker.start()

    def _on_finished(self, spec, warnings):
        self._set_busy(False)
        self._status_label.setText(
            tr("success_circuit", name=spec.name,
               components=spec.component_count, nets=spec.net_count)
        )
        if spec.net_count == 0:
            self._status_label.setStyleSheet(f"color: {tc().warning};")
            QMessageBox.warning(
                self,
                tr("dialog_warning"),
                tr("warning_zero_nets", name=spec.name, count=spec.component_count),
            )
        else:
            self._status_label.setStyleSheet(f"color: {tc().success};")

        if warnings:
            lines: list[str] = [tr("input_validation_warnings_title", count=len(warnings))]
            for w in warnings[:5]:
                sev = str(getattr(w, "severity", "warning")).upper()
                msg = str(getattr(w, "message", w))
                lines.append(f"[{sev}] {msg}")
            if len(warnings) > 5:
                lines.append(tr("input_validation_warnings_more", count=len(warnings) - 5))

            self._warnings_label.setText("\n".join(lines))
            self._warnings_label.setStyleSheet(f"color: {tc().warning}; font-size: 11px;")
            self._warnings_label.setVisible(True)
            self.status_message.emit(
                tr("status_circuit_created_with_warnings", name=spec.name, count=len(warnings))
            )
        else:
            self._warnings_label.setVisible(False)
            self.status_message.emit(tr("status_circuit_created", name=spec.name))

        self.circuit_generated.emit(spec)

    def _on_error(self, msg: str):
        self._set_busy(False)
        self._status_label.setText(tr("error_circuit", error=msg))
        self._status_label.setStyleSheet(f"color: {tc().error};")
        self._warnings_label.setVisible(False)
        self._warnings_label.setText("")
        self.status_message.emit(tr("error_circuit", error=msg))

    def _on_progress(self, msg: str):
        self._status_label.setText(msg)

    def _set_busy(self, busy: bool):
        self._generate_btn.setEnabled(not busy)
        self._text_edit.setReadOnly(busy)
        self._progress_bar.setVisible(busy)

    def _retranslate(self):
        """Update all labels to the current language."""
        self._title.setText(tr("title_circuit_desc"))
        self._subtitle.setText(tr("subtitle_circuit"))
        self._tmpl_label.setText(tr("label_template"))
        self._text_edit.setPlaceholderText(tr("placeholder_circuit"))
        self._generate_btn.setText(tr("button_design"))
        self._clear_btn.setText(tr("button_clear"))
        # Rebuild template combo
        self._template_combo.blockSignals(True)
        self._template_combo.clear()
        for name_key, _ in self._TEMPLATE_KEYS:
            self._template_combo.addItem(tr(name_key))
        self._template_combo.blockSignals(False)
