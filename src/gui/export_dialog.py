"""Export dialog — multi-format PCB export with options."""

from __future__ import annotations

import copy
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QCheckBox,
    QPushButton, QLabel, QFileDialog, QLineEdit, QMessageBox,
    QProgressBar,
)
from PySide6.QtCore import Qt, Signal, QThread

from src.ai.schemas import CircuitSpec
from src.pcb.generator import Board, PCBGenerator
from src.pcb.router import FreeroutingRouter
from src.pcb.rules import DRCEngine
from src.pcb.exporter import export_kicad_pcb, export_svg, export_json, export_gerber
from src.gui.i18n import tr, Translator
from src.utils.logger import get_logger

log = get_logger("gui.export_dialog")


class ExportWorker(QThread):
    """Background export processing."""

    progress = Signal(str)
    finished = Signal(list)  # list of exported file paths
    error = Signal(str)

    def __init__(
        self,
        spec: CircuitSpec,
        board: Board | None,
        output_dir: str,
        formats: dict[str, bool],
        auto_route: bool,
        parent=None,
    ):
        super().__init__(parent)
        self._spec = spec
        self._board = board
        self._output_dir = Path(output_dir)
        self._formats = formats
        self._auto_route = auto_route

    def run(self):
        try:
            exported: list[str] = []

            # Generate board
            self.progress.emit(tr("progress_creating_pcb"))
            if self._board is not None:
                board = copy.deepcopy(self._board)
            else:
                gen = PCBGenerator(self._spec)
                board = gen.generate()

            # Auto-route
            if self._auto_route:
                self.progress.emit(tr("progress_routing"))
                router = FreeroutingRouter(board)
                board = router.route()

            # DRC
            self.progress.emit(tr("progress_drc"))
            drc = DRCEngine(board)
            violations = drc.run_all()

            out = self._output_dir
            out.mkdir(parents=True, exist_ok=True)
            spec_dict = self._spec.model_dump(mode="json")

            if self._formats.get("kicad"):
                self.progress.emit(tr("progress_kicad"))
                p = export_kicad_pcb(board, out / f"{self._spec.name}.kicad_pcb")
                exported.append(str(p))

            if self._formats.get("svg"):
                self.progress.emit(tr("progress_svg"))
                p = export_svg(board, out / f"{self._spec.name}.svg")
                exported.append(str(p))

            if self._formats.get("json"):
                self.progress.emit(tr("progress_json"))
                p = export_json(board, spec_dict, out / f"{self._spec.name}.json")
                exported.append(str(p))

            if self._formats.get("gerber"):
                self.progress.emit(tr("progress_gerber"))
                gerber_dir = out / "gerber"
                files = export_gerber(board, gerber_dir)
                exported.extend(str(f) for f in files)

            self.finished.emit(exported)
        except Exception as e:
            self.error.emit(str(e))


class ExportDialog(QDialog):
    """Dialog for configuring and executing PCB export."""

    def __init__(self, spec: CircuitSpec, board: Board | None = None, parent=None):
        super().__init__(parent)
        self._spec = spec
        self._board = board
        self._worker: ExportWorker | None = None
        self.setMinimumSize(500, 400)
        self._setup_ui()
        self._retranslate()
        Translator.instance().language_changed.connect(self._retranslate)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # Title
        self._title_label = QLabel()
        self._title_label.setObjectName("titleLabel")
        layout.addWidget(self._title_label)

        # Output directory
        dir_layout = QHBoxLayout()
        self._dir_label = QLabel()
        dir_layout.addWidget(self._dir_label)
        self._dir_edit = QLineEdit()
        self._dir_edit.setText(str(Path.home() / "Desktop" / "pcb_output"))
        dir_layout.addWidget(self._dir_edit, 1)
        browse_btn = QPushButton("📁")
        browse_btn.setMaximumWidth(40)
        browse_btn.clicked.connect(self._browse_dir)
        dir_layout.addWidget(browse_btn)
        layout.addLayout(dir_layout)

        # Format selection
        self._fmt_group = QGroupBox()
        fmt_layout = QVBoxLayout(self._fmt_group)

        self._cb_kicad = QCheckBox()
        self._cb_kicad.setChecked(True)
        fmt_layout.addWidget(self._cb_kicad)

        self._cb_svg = QCheckBox()
        self._cb_svg.setChecked(True)
        fmt_layout.addWidget(self._cb_svg)

        self._cb_gerber = QCheckBox()
        self._cb_gerber.setChecked(True)
        fmt_layout.addWidget(self._cb_gerber)

        self._cb_json = QCheckBox()
        self._cb_json.setChecked(False)
        fmt_layout.addWidget(self._cb_json)

        layout.addWidget(self._fmt_group)

        # Options
        self._opt_group = QGroupBox()
        opt_layout = QVBoxLayout(self._opt_group)

        self._cb_autoroute = QCheckBox()
        self._cb_autoroute.setChecked(True)
        opt_layout.addWidget(self._cb_autoroute)

        layout.addWidget(self._opt_group)

        # Progress
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._cancel_btn = QPushButton()
        self._cancel_btn.setObjectName("secondaryButton")
        self._cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self._cancel_btn)

        self._export_btn = QPushButton()
        self._export_btn.setMinimumWidth(150)
        self._export_btn.clicked.connect(self._start_export)
        btn_layout.addWidget(self._export_btn)

        layout.addLayout(btn_layout)

    def _browse_dir(self):
        d = QFileDialog.getExistingDirectory(self, tr("dialog_select_output"))
        if d:
            self._dir_edit.setText(d)

    def _start_export(self):
        output_dir = self._dir_edit.text().strip()
        if not output_dir:
            QMessageBox.warning(self, tr("dialog_warning"), tr("warning_select_folder"))
            return

        formats = {
            "kicad": self._cb_kicad.isChecked(),
            "svg": self._cb_svg.isChecked(),
            "gerber": self._cb_gerber.isChecked(),
            "json": self._cb_json.isChecked(),
        }

        if not any(formats.values()):
            QMessageBox.warning(self, tr("dialog_warning"), tr("warning_select_format"))
            return

        self._export_btn.setEnabled(False)
        self._progress.setVisible(True)

        self._worker = ExportWorker(
            self._spec, self._board, output_dir, formats,
            auto_route=self._cb_autoroute.isChecked(),
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, msg: str):
        self._status.setText(msg)

    def _on_finished(self, files: list[str]):
        self._progress.setVisible(False)
        self._export_btn.setEnabled(True)
        count = len(files)
        self._status.setText(tr("success_exported", count=count))
        self._status.setStyleSheet("color: #3fb950;")

        QMessageBox.information(
            self,
            tr("dialog_success"),
            tr("message_exported", count=count) + "\n".join(files[:10]),
        )

    def _on_error(self, msg: str):
        self._progress.setVisible(False)
        self._export_btn.setEnabled(True)
        self._status.setText(tr("error_export", error=msg))
        self._status.setStyleSheet("color: #f85149;")
        QMessageBox.critical(self, tr("dialog_error"), msg)

    def _retranslate(self):
        """Update all labels to the current language."""
        self.setWindowTitle(tr("export_title"))
        self._title_label.setText(tr("export_heading", name=self._spec.name))
        self._dir_label.setText(tr("label_output_folder"))
        self._fmt_group.setTitle(tr("group_output_formats"))
        self._cb_kicad.setText(tr("checkbox_kicad"))
        self._cb_svg.setText(tr("checkbox_svg"))
        self._cb_gerber.setText(tr("checkbox_gerber"))
        self._cb_json.setText(tr("checkbox_json"))
        self._opt_group.setTitle(tr("group_options"))
        self._cb_autoroute.setText(tr("checkbox_autoroute"))
        self._cancel_btn.setText(tr("button_cancel"))
        self._export_btn.setText(tr("button_export"))
