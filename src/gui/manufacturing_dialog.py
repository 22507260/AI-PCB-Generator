"""One-Click PCB Manufacturing dialog.

Allows users to select a manufacturer, configure options, generate
production files, and get cost estimates — all in one step.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QSpinBox, QGroupBox, QFrame, QFileDialog, QMessageBox,
    QProgressBar, QLineEdit, QGridLayout, QWidget,
)
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QColor, QDesktopServices
from PySide6.QtCore import QUrl

from src.ai.schemas import CircuitSpec
from src.pcb.generator import Board, PCBGenerator
from src.pcb.router import FreeroutingRouter
from src.pcb.manufacturing import (
    MANUFACTURERS,
    ManufacturerProfile,
    estimate_cost,
    generate_production_package,
    CostEstimate,
)
from src.gui.i18n import tr, Translator
from src.utils.logger import get_logger

log = get_logger("gui.manufacturing")


# ======================================================================
# Background Worker
# ======================================================================

class ManufacturingWorker(QThread):
    """Background production file generation."""

    progress = Signal(str)
    finished = Signal(dict)   # {str: Path}
    error = Signal(str)

    def __init__(
        self,
        spec: CircuitSpec,
        output_dir: str,
        manufacturer_key: str,
        auto_route: bool,
        parent=None,
    ):
        super().__init__(parent)
        self._spec = spec
        self._output_dir = output_dir
        self._manufacturer_key = manufacturer_key
        self._auto_route = auto_route

    def run(self):
        try:
            self.progress.emit(tr("mfg_progress_pcb"))
            gen = PCBGenerator(self._spec)
            board = gen.generate()

            if self._auto_route:
                self.progress.emit(tr("mfg_progress_routing"))
                router = FreeroutingRouter(board)
                board = router.route()

            self.progress.emit(tr("mfg_progress_generating"))
            result = generate_production_package(
                board, self._spec,
                self._output_dir,
                self._manufacturer_key,
            )
            self.finished.emit({k: str(v) for k, v in result.items()})
        except Exception as e:
            self.error.emit(str(e))


# ======================================================================
# Manufacturing Dialog
# ======================================================================

class ManufacturingDialog(QDialog):
    """One-Click PCB Manufacturing dialog."""

    def __init__(self, spec: CircuitSpec, board: Board | None = None, parent=None):
        super().__init__(parent)
        self._spec = spec
        self._board = board
        self._worker: ManufacturingWorker | None = None
        self._cost: CostEstimate | None = None

        self.setMinimumSize(600, 560)
        self._setup_ui()
        self._retranslate()
        self._update_cost()
        Translator.instance().language_changed.connect(self._retranslate)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # ── Title ──
        self._title = QLabel()
        self._title.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
        self._title.setStyleSheet("color: #e6edf3;")
        layout.addWidget(self._title)

        self._subtitle = QLabel()
        self._subtitle.setStyleSheet("color: #8b949e; font-size: 11px;")
        self._subtitle.setWordWrap(True)
        layout.addWidget(self._subtitle)

        # ── Manufacturer Selection ──
        self._mfg_group = QGroupBox()
        mfg_layout = QGridLayout(self._mfg_group)
        mfg_layout.setColumnStretch(1, 1)

        self._lbl_manufacturer = QLabel()
        mfg_layout.addWidget(self._lbl_manufacturer, 0, 0)

        self._cmb_manufacturer = QComboBox()
        for key, profile in MANUFACTURERS.items():
            self._cmb_manufacturer.addItem(
                f"{profile.name} — {profile.website}", key
            )
        self._cmb_manufacturer.currentIndexChanged.connect(self._update_cost)
        mfg_layout.addWidget(self._cmb_manufacturer, 0, 1)

        self._lbl_quantity = QLabel()
        mfg_layout.addWidget(self._lbl_quantity, 1, 0)

        self._spn_quantity = QSpinBox()
        self._spn_quantity.setRange(1, 10000)
        self._spn_quantity.setValue(5)
        self._spn_quantity.setSuffix(" pcs")
        self._spn_quantity.valueChanged.connect(self._update_cost)
        mfg_layout.addWidget(self._spn_quantity, 1, 1)

        layout.addWidget(self._mfg_group)

        # ── Cost Estimation Card ──
        self._cost_frame = QFrame()
        self._cost_frame.setStyleSheet(
            "QFrame { background: #161b22; border: 1px solid #30363d; "
            "border-radius: 6px; }"
        )
        cost_layout = QGridLayout(self._cost_frame)
        cost_layout.setContentsMargins(16, 12, 16, 12)
        cost_layout.setSpacing(8)

        self._cost_title = QLabel()
        self._cost_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self._cost_title.setStyleSheet("color: #e6edf3;")
        cost_layout.addWidget(self._cost_title, 0, 0, 1, 2)

        self._lbl_board_area = QLabel()
        self._lbl_board_area.setStyleSheet("color: #8b949e; font-size: 11px;")
        cost_layout.addWidget(self._lbl_board_area, 1, 0)
        self._val_board_area = QLabel()
        self._val_board_area.setStyleSheet("color: #e6edf3; font-size: 11px;")
        cost_layout.addWidget(self._val_board_area, 1, 1)

        self._lbl_pcb_cost = QLabel()
        self._lbl_pcb_cost.setStyleSheet("color: #8b949e; font-size: 11px;")
        cost_layout.addWidget(self._lbl_pcb_cost, 2, 0)
        self._val_pcb_cost = QLabel()
        self._val_pcb_cost.setStyleSheet("color: #e6edf3; font-size: 11px;")
        cost_layout.addWidget(self._val_pcb_cost, 2, 1)

        self._lbl_smt_cost = QLabel()
        self._lbl_smt_cost.setStyleSheet("color: #8b949e; font-size: 11px;")
        cost_layout.addWidget(self._lbl_smt_cost, 3, 0)
        self._val_smt_cost = QLabel()
        self._val_smt_cost.setStyleSheet("color: #e6edf3; font-size: 11px;")
        cost_layout.addWidget(self._val_smt_cost, 3, 1)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #30363d;")
        cost_layout.addWidget(sep, 4, 0, 1, 2)

        self._lbl_total = QLabel()
        self._lbl_total.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self._lbl_total.setStyleSheet("color: #3fb950;")
        cost_layout.addWidget(self._lbl_total, 5, 0)
        self._val_total = QLabel()
        self._val_total.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self._val_total.setStyleSheet("color: #3fb950;")
        cost_layout.addWidget(self._val_total, 5, 1)

        self._lbl_lead_time = QLabel()
        self._lbl_lead_time.setStyleSheet("color: #8b949e; font-size: 11px;")
        cost_layout.addWidget(self._lbl_lead_time, 6, 0)
        self._val_lead_time = QLabel()
        self._val_lead_time.setStyleSheet("color: #e6edf3; font-size: 11px;")
        cost_layout.addWidget(self._val_lead_time, 6, 1)

        self._cost_notes = QLabel()
        self._cost_notes.setStyleSheet("color: #d29922; font-size: 10px;")
        self._cost_notes.setWordWrap(True)
        cost_layout.addWidget(self._cost_notes, 7, 0, 1, 2)

        layout.addWidget(self._cost_frame)

        # ── Output Directory ──
        dir_layout = QHBoxLayout()
        self._lbl_output = QLabel()
        dir_layout.addWidget(self._lbl_output)
        self._dir_edit = QLineEdit()
        self._dir_edit.setText(
            str(Path.home() / "Desktop" / "pcb_production")
        )
        dir_layout.addWidget(self._dir_edit, 1)
        browse_btn = QPushButton("📁")
        browse_btn.setMaximumWidth(40)
        browse_btn.clicked.connect(self._browse_dir)
        dir_layout.addWidget(browse_btn)
        layout.addLayout(dir_layout)

        # ── Progress ──
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        # ── File list (after generation) ──
        self._files_label = QLabel("")
        self._files_label.setStyleSheet("color: #8b949e; font-size: 11px;")
        self._files_label.setWordWrap(True)
        self._files_label.setVisible(False)
        layout.addWidget(self._files_label)

        # ── Buttons ──
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._btn_cancel = QPushButton()
        self._btn_cancel.setStyleSheet(
            "QPushButton { background: #21262d; color: #e6edf3; border: 1px solid #30363d; "
            "border-radius: 4px; padding: 6px 16px; }"
            "QPushButton:hover { background: #30363d; }"
        )
        self._btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self._btn_cancel)

        self._btn_open_folder = QPushButton()
        self._btn_open_folder.setStyleSheet(
            "QPushButton { background: #21262d; color: #e6edf3; border: 1px solid #30363d; "
            "border-radius: 4px; padding: 6px 16px; }"
            "QPushButton:hover { background: #30363d; }"
        )
        self._btn_open_folder.clicked.connect(self._open_output_folder)
        self._btn_open_folder.setVisible(False)
        btn_layout.addWidget(self._btn_open_folder)

        self._btn_generate = QPushButton()
        self._btn_generate.setMinimumWidth(200)
        self._btn_generate.setStyleSheet(
            "QPushButton { background: #238636; color: white; border: none; "
            "border-radius: 4px; padding: 8px 20px; font-size: 12px; font-weight: bold; }"
            "QPushButton:hover { background: #2ea043; }"
            "QPushButton:disabled { background: #21262d; color: #484f58; }"
        )
        self._btn_generate.clicked.connect(self._start_generation)
        btn_layout.addWidget(self._btn_generate)

        layout.addLayout(btn_layout)

    # ==================================================================
    # Cost Estimation
    # ==================================================================

    def _update_cost(self):
        mfg_key = self._cmb_manufacturer.currentData()
        quantity = self._spn_quantity.value()

        if not self._board:
            gen = PCBGenerator(self._spec)
            self._board = gen.generate()

        self._cost = estimate_cost(
            self._board, self._spec, mfg_key, quantity
        )
        self._display_cost(self._cost)

    def _display_cost(self, cost: CostEstimate):
        self._val_board_area.setText(f"{cost.board_area_sqcm:.1f} cm²")
        self._val_pcb_cost.setText(f"${cost.pcb_cost_usd:.2f}")
        self._val_smt_cost.setText(
            f"${cost.smt_cost_usd:.2f}" if cost.smt_cost_usd > 0 else "—"
        )
        self._val_total.setText(f"${cost.total_cost_usd:.2f}")
        self._val_lead_time.setText(
            tr("mfg_lead_time_value", days=cost.lead_time_days)
        )

        if cost.notes:
            self._cost_notes.setText("⚠ " + " | ".join(cost.notes))
            self._cost_notes.setVisible(True)
        else:
            self._cost_notes.setVisible(False)

    # ==================================================================
    # File Generation
    # ==================================================================

    def _browse_dir(self):
        d = QFileDialog.getExistingDirectory(
            self, tr("dialog_select_output")
        )
        if d:
            self._dir_edit.setText(d)

    def _start_generation(self):
        output_dir = self._dir_edit.text().strip()
        if not output_dir:
            QMessageBox.warning(
                self, tr("dialog_warning"), tr("warning_select_folder")
            )
            return

        mfg_key = self._cmb_manufacturer.currentData()

        self._btn_generate.setEnabled(False)
        self._progress.setVisible(True)
        self._files_label.setVisible(False)
        self._btn_open_folder.setVisible(False)

        self._worker = ManufacturingWorker(
            self._spec, output_dir, mfg_key,
            auto_route=True,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, msg: str):
        self._status.setText(msg)
        self._status.setStyleSheet("color: #8b949e;")

    def _on_finished(self, files: dict[str, str]):
        self._progress.setVisible(False)
        self._btn_generate.setEnabled(True)

        count = len(files)
        self._status.setText(tr("mfg_success", count=count))
        self._status.setStyleSheet("color: #3fb950; font-weight: bold;")

        # Show generated files
        lines = []
        labels = {
            "gerber_zip": "📦 Gerber ZIP",
            "bom": "📋 BOM (CSV)",
            "cpl": "📍 Pick & Place (CPL)",
            "kicad_pcb": "🔧 KiCad PCB",
        }
        for key, path_str in files.items():
            label = labels.get(key, key)
            fname = Path(path_str).name
            lines.append(f"  {label}: {fname}")

        self._files_label.setText("\n".join(lines))
        self._files_label.setVisible(True)
        self._btn_open_folder.setVisible(True)

        QMessageBox.information(
            self,
            tr("dialog_success"),
            tr("mfg_complete_msg", count=count),
        )

    def _on_error(self, msg: str):
        self._progress.setVisible(False)
        self._btn_generate.setEnabled(True)
        self._status.setText(tr("error_export", error=msg))
        self._status.setStyleSheet("color: #f85149;")
        QMessageBox.critical(self, tr("dialog_error"), msg)

    def _open_output_folder(self):
        output_dir = self._dir_edit.text().strip()
        if output_dir and Path(output_dir).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(output_dir))

    # ==================================================================
    # i18n
    # ==================================================================

    def _retranslate(self):
        self.setWindowTitle(tr("mfg_title"))
        self._title.setText(tr("mfg_heading"))
        self._subtitle.setText(tr("mfg_subtitle"))
        self._mfg_group.setTitle(tr("mfg_group_config"))
        self._lbl_manufacturer.setText(tr("mfg_manufacturer"))
        self._lbl_quantity.setText(tr("mfg_quantity"))
        self._cost_title.setText(tr("mfg_cost_title"))
        self._lbl_board_area.setText(tr("mfg_board_area"))
        self._lbl_pcb_cost.setText(tr("mfg_pcb_cost"))
        self._lbl_smt_cost.setText(tr("mfg_smt_cost"))
        self._lbl_total.setText(tr("mfg_total"))
        self._lbl_lead_time.setText(tr("mfg_lead_time"))
        self._lbl_output.setText(tr("label_output_folder"))
        self._btn_cancel.setText(tr("button_cancel"))
        self._btn_open_folder.setText(tr("mfg_open_folder"))
        self._btn_generate.setText(tr("mfg_generate"))
