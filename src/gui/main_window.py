"""Main application window — assembles all panels and orchestrates the pipeline."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QSplitter, QTabWidget, QMenuBar,
    QStatusBar, QToolBar, QFileDialog, QMessageBox,
    QWidget, QVBoxLayout,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QAction, QKeySequence

from src.ai.schemas import CircuitSpec
from src.pcb.generator import Board, PCBGenerator
from src.pcb.router import FreeroutingRouter
from src.pcb.rules import DRCEngine
from src.gui.input_panel import InputPanel
from src.gui.schematic_view import SchematicView
from src.gui.pcb_view import PCBView
from src.gui.view3d import View3D
from src.gui.simulation_view import SimulationView
from src.gui.component_panel import ComponentPanel
from src.gui.component_palette import ComponentPalette
from src.gui.ai_copilot import AICoPilotPanel
from src.gui.design_review import DesignReviewPanel
from src.gui.export_dialog import ExportDialog
from src.gui.manufacturing_dialog import ManufacturingDialog
from src.gui.settings_dialog import SettingsDialog
from src.gui.i18n import tr, Translator
from src.utils.file_io import save_project, load_project
from src.utils.logger import get_logger

log = get_logger("gui.main_window")


class MainWindow(QMainWindow):
    """Primary application window."""

    def __init__(self):
        super().__init__()
        self._spec: CircuitSpec | None = None
        self._board: Board | None = None

        self.setMinimumSize(1200, 750)
        self.resize(1400, 850)

        self._setup_menubar()
        self._setup_toolbar()
        self._setup_central()
        self._setup_statusbar()
        self._retranslate()

        Translator.instance().language_changed.connect(self._retranslate)

    # ==================================================================
    # UI Setup
    # ==================================================================

    def _setup_menubar(self):
        menu = self.menuBar()

        # File menu
        self._file_menu = menu.addMenu("")

        self._act_new = QAction("", self)
        self._act_new.setShortcut(QKeySequence.StandardKey.New)
        self._act_new.triggered.connect(self._new_project)
        self._file_menu.addAction(self._act_new)

        self._act_open = QAction("", self)
        self._act_open.setShortcut(QKeySequence.StandardKey.Open)
        self._act_open.triggered.connect(self._open_project)
        self._file_menu.addAction(self._act_open)

        self._act_save = QAction("", self)
        self._act_save.setShortcut(QKeySequence.StandardKey.Save)
        self._act_save.triggered.connect(self._save_project)
        self._file_menu.addAction(self._act_save)

        self._file_menu.addSeparator()

        self._act_export = QAction("", self)
        self._act_export.setShortcut(QKeySequence("Ctrl+E"))
        self._act_export.triggered.connect(self._export)
        self._file_menu.addAction(self._act_export)

        self._act_manufacture = QAction("", self)
        self._act_manufacture.setShortcut(QKeySequence("Ctrl+M"))
        self._act_manufacture.triggered.connect(self._manufacture)
        self._file_menu.addAction(self._act_manufacture)

        self._file_menu.addSeparator()

        self._act_exit = QAction("", self)
        self._act_exit.setShortcut(QKeySequence.StandardKey.Quit)
        self._act_exit.triggered.connect(self.close)
        self._file_menu.addAction(self._act_exit)

        # Edit menu
        self._edit_menu = menu.addMenu("")

        self._act_undo = QAction("", self)
        self._act_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self._edit_menu.addAction(self._act_undo)

        self._act_redo = QAction("", self)
        self._act_redo.setShortcut(QKeySequence.StandardKey.Redo)
        self._edit_menu.addAction(self._act_redo)

        self._edit_menu.addSeparator()

        self._act_delete = QAction("", self)
        self._act_delete.setShortcut(QKeySequence.StandardKey.Delete)
        self._edit_menu.addAction(self._act_delete)

        self._edit_menu.addSeparator()

        self._act_settings = QAction("", self)
        self._act_settings.setShortcut(QKeySequence("Ctrl+,"))
        self._act_settings.triggered.connect(self._open_settings)
        self._edit_menu.addAction(self._act_settings)

        # View menu
        self._view_menu = menu.addMenu("")

        self._act_zoom_in = QAction("", self)
        self._act_zoom_in.setShortcut(QKeySequence.StandardKey.ZoomIn)
        self._act_zoom_in.triggered.connect(lambda: self._zoom_active_view(1.25))
        self._view_menu.addAction(self._act_zoom_in)

        self._act_zoom_out = QAction("", self)
        self._act_zoom_out.setShortcut(QKeySequence.StandardKey.ZoomOut)
        self._act_zoom_out.triggered.connect(lambda: self._zoom_active_view(0.8))
        self._view_menu.addAction(self._act_zoom_out)

        # Help menu
        self._help_menu = menu.addMenu("")
        self._act_about = QAction("", self)
        self._act_about.triggered.connect(self._show_about)
        self._help_menu.addAction(self._act_about)

    def _setup_toolbar(self):
        self._toolbar = QToolBar("")
        self._toolbar.setIconSize(QSize(20, 20))
        self._toolbar.setMovable(False)
        self.addToolBar(self._toolbar)

        self._tb_new = self._toolbar.addAction("")
        self._tb_new.triggered.connect(self._new_project)
        self._tb_open = self._toolbar.addAction("")
        self._tb_open.triggered.connect(self._open_project)
        self._tb_save = self._toolbar.addAction("")
        self._tb_save.triggered.connect(self._save_project)
        self._toolbar.addSeparator()
        self._tb_export = self._toolbar.addAction("")
        self._tb_export.triggered.connect(self._export)
        self._tb_manufacture = self._toolbar.addAction("")
        self._tb_manufacture.triggered.connect(self._manufacture)
        self._toolbar.addSeparator()
        self._tb_settings = self._toolbar.addAction("")
        self._tb_settings.triggered.connect(self._open_settings)
        self._toolbar.addSeparator()
        self._tb_wire = self._toolbar.addAction("")
        self._tb_wire.setCheckable(True)
        self._tb_wire.toggled.connect(self._toggle_wire_mode)

    def _setup_central(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        # Main splitter: left (input + palette + BOM) | right (viewers)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left panel
        left_splitter = QSplitter(Qt.Orientation.Vertical)

        self._input_panel = InputPanel()
        self._input_panel.circuit_generated.connect(self._on_circuit_generated)
        self._input_panel.status_message.connect(self._set_status)
        left_splitter.addWidget(self._input_panel)

        self._component_palette = ComponentPalette()
        left_splitter.addWidget(self._component_palette)

        self._component_panel = ComponentPanel()
        left_splitter.addWidget(self._component_panel)

        left_splitter.setSizes([300, 250, 200])
        splitter.addWidget(left_splitter)

        # Right panel — tabbed viewers
        self._tab_widget = QTabWidget()

        # Schematic tab: editor + AI Co-Pilot
        schematic_container = QWidget()
        sch_layout = QVBoxLayout(schematic_container)
        sch_layout.setContentsMargins(0, 0, 0, 0)
        sch_splitter = QSplitter(Qt.Orientation.Vertical)

        self._schematic_view = SchematicView()
        self._schematic_view.circuit_modified.connect(self._on_circuit_modified)
        sch_splitter.addWidget(self._schematic_view)

        self._copilot = AICoPilotPanel()
        self._copilot.component_highlight.connect(
            self._schematic_view.highlight_component
        )
        sch_splitter.addWidget(self._copilot)

        sch_splitter.setSizes([500, 150])
        sch_layout.addWidget(sch_splitter)
        self._tab_widget.addTab(schematic_container, "")

        # Connect undo/redo actions to schematic undo stack
        self._act_undo.triggered.connect(self._schematic_view.undo_stack.undo)
        self._act_redo.triggered.connect(self._schematic_view.undo_stack.redo)
        self._act_delete.triggered.connect(self._schematic_view._delete_selected)

        self._pcb_view = PCBView()
        self._tab_widget.addTab(self._pcb_view, "")

        self._view_3d = View3D()
        self._tab_widget.addTab(self._view_3d, "")

        self._simulation_view = SimulationView()
        self._tab_widget.addTab(self._simulation_view, "")

        self._design_review = DesignReviewPanel()
        self._design_review.component_highlight.connect(
            self._schematic_view.highlight_component
        )
        self._tab_widget.addTab(self._design_review, "")

        splitter.addWidget(self._tab_widget)

        splitter.setSizes([350, 850])
        layout.addWidget(splitter)

    def _setup_statusbar(self):
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)

    # ==================================================================
    # Pipeline
    # ==================================================================

    def _on_circuit_generated(self, spec: CircuitSpec):
        """Handle AI-generated circuit specification."""
        self._spec = spec
        log.info("Circuit received: %s", spec.name)

        # Update all views
        self._schematic_view.load_circuit(spec)
        self._component_panel.load_circuit(spec)

        # Generate board and show PCB
        gen = PCBGenerator(spec)
        self._board = gen.generate()
        self._pcb_view.load_board(self._board)
        self._view_3d.load_board(self._board)

        # Load circuit into simulation view
        self._simulation_view.load_circuit(spec)

        # Run ERC (AI Co-Pilot)
        self._copilot.run_erc(spec)

        # Run DFM / Design Review
        self._design_review.load_board(self._board)

        # Run DRC
        drc = DRCEngine(self._board)
        violations = drc.run_all()
        if violations:
            error_count = sum(1 for v in violations if v.severity == "error")
            warn_count = len(violations) - error_count
            self._set_status(
                tr("status_drc_issues", errors=error_count, warnings=warn_count)
            )
        else:
            self._set_status(tr("status_drc_pass"))

        self._tab_widget.setCurrentIndex(0)  # Show schematic first

    def _on_circuit_modified(self, spec: CircuitSpec):
        """Handle changes from the schematic editor."""
        self._spec = spec
        log.info("Circuit modified: %d components, %d nets",
                 len(spec.components), len(spec.nets))

        # Update downstream views
        self._component_panel.load_circuit(spec)
        self._copilot.run_erc(spec)

        # Regenerate PCB if we have enough data
        if spec.components and spec.nets:
            try:
                gen = PCBGenerator(spec)
                self._board = gen.generate()
                self._pcb_view.load_board(self._board)
                self._view_3d.load_board(self._board)
                self._simulation_view.load_circuit(spec)
                self._design_review.load_board(self._board)
            except Exception as e:
                log.warning("PCB regeneration failed: %s", e)

    def _toggle_wire_mode(self, checked: bool):
        """Toggle wire drawing mode on the schematic view."""
        self._schematic_view.set_wire_mode(checked)
        if checked:
            self._tab_widget.setCurrentIndex(0)

    def _zoom_active_view(self, factor: float) -> None:
        """Scale the currently visible graphics view."""
        idx = self._tab_widget.currentIndex()
        if idx == 0:
            self._schematic_view.scale(factor, factor)
        elif idx == 1:
            self._pcb_view._view.scale(factor, factor)
        # idx == 2 is the 3D view, idx == 3 is simulation — both handle zoom internally

    # ==================================================================
    # Actions
    # ==================================================================

    def _new_project(self):
        self._spec = None
        self._board = None
        empty = CircuitSpec(name="Untitled")
        self._schematic_view.load_circuit(empty)
        self._component_panel.load_circuit(empty)
        self._pcb_view.clear_board()
        self._view_3d.clear_board()
        self._simulation_view.clear_circuit()
        self._copilot.run_erc(None)
        self._design_review.load_board(None)
        self._tab_widget.setCurrentIndex(0)
        self._set_status(tr("status_new_project"))

    def _open_project(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("dialog_open_project"), "", tr("file_filter_project")
        )
        if not path:
            return
        try:
            spec = load_project(path)
            self._on_circuit_generated(spec)
            self._set_status(tr("status_project_loaded", name=spec.name))
        except Exception as e:
            QMessageBox.critical(self, tr("dialog_error"), tr("error_load_project", error=e))

    def _save_project(self):
        if not self._spec:
            QMessageBox.warning(self, tr("dialog_warning"), tr("warning_no_circuit"))
            return

        path, _ = QFileDialog.getSaveFileName(
            self, tr("dialog_save_project"), f"{self._spec.name}.apcb",
            tr("file_filter_apcb"),
        )
        if not path:
            return
        try:
            save_project(self._spec, path)
            self._set_status(tr("status_project_saved", path=path))
        except Exception as e:
            QMessageBox.critical(self, tr("dialog_error"), tr("error_save_project", error=e))

    def _export(self):
        if not self._spec:
            QMessageBox.warning(self, tr("dialog_warning"), tr("warning_design_first"))
            return
        dialog = ExportDialog(self._spec, self)
        dialog.exec()

    def _manufacture(self):
        if not self._spec:
            QMessageBox.warning(self, tr("dialog_warning"), tr("warning_design_first"))
            return
        dialog = ManufacturingDialog(self._spec, self._board, self)
        dialog.exec()

    def _open_settings(self):
        dialog = SettingsDialog(self)
        dialog.exec()

    def _show_about(self):
        QMessageBox.about(
            self,
            tr("about_title"),
            tr("about_text"),
        )

    def _set_status(self, msg: str):
        self._statusbar.showMessage(msg)

    def _retranslate(self):
        """Update all labels to the current language."""
        self.setWindowTitle(tr("app_title"))
        self._file_menu.setTitle(tr("menu_file"))
        self._edit_menu.setTitle(tr("menu_edit"))
        self._view_menu.setTitle(tr("menu_view"))
        self._help_menu.setTitle(tr("menu_help"))
        self._act_new.setText(tr("action_new_project"))
        self._act_open.setText(tr("action_open_project"))
        self._act_save.setText(tr("action_save_project"))
        self._act_export.setText(tr("action_export"))
        self._act_manufacture.setText(tr("action_manufacture"))
        self._act_exit.setText(tr("action_exit"))
        self._act_settings.setText(tr("action_settings"))
        self._act_zoom_in.setText(tr("action_zoom_in"))
        self._act_zoom_out.setText(tr("action_zoom_out"))
        self._act_undo.setText(tr("action_undo"))
        self._act_redo.setText(tr("action_redo"))
        self._act_delete.setText(tr("action_delete"))
        self._act_about.setText(tr("action_about"))
        self._toolbar.setWindowTitle(tr("toolbar_main"))
        self._tb_new.setText(tr("toolbar_new"))
        self._tb_open.setText(tr("toolbar_open"))
        self._tb_save.setText(tr("toolbar_save"))
        self._tb_export.setText(tr("toolbar_export"))
        self._tb_manufacture.setText(tr("toolbar_manufacture"))
        self._tb_settings.setText(tr("toolbar_settings"))
        self._tb_wire.setText(tr("toolbar_wire"))
        self._tab_widget.setTabText(0, tr("tab_schematic"))
        self._tab_widget.setTabText(1, tr("tab_pcb_layout"))
        self._tab_widget.setTabText(2, tr("tab_3d_view"))
        self._tab_widget.setTabText(3, tr("tab_simulation"))
        self._tab_widget.setTabText(4, tr("tab_design_review"))
        self._copilot.retranslate()
        self._design_review.retranslate()
        self._component_palette.retranslate()
        self._statusbar.showMessage(tr("status_ready"))
