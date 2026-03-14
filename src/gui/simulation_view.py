"""Simulation tab — SPICE simulation controls and waveform display."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

import numpy as np

try:
    import pyqtgraph as pg

    pg.setConfigOptions(antialias=True, background="#0d1117", foreground="#e6edf3")
    _HAS_PG = True
except ImportError:
    _HAS_PG = False

from src.gui.i18n import tr, Translator
from src.gui.theme import tc, ThemeManager
from src.simulation.engine import NgSpiceEngine
from src.simulation.netlist_writer import SpiceNetlistWriter
from src.simulation.python_solver import PythonSolver
from src.simulation.results import AnalysisConfig, SimulationResult

if TYPE_CHECKING:
    from src.ai.schemas import CircuitSpec

log = logging.getLogger(__name__)

# Oscilloscope-style signal colors
_SIGNAL_COLORS = [
    "#3fb950",  # green
    "#58a6ff",  # blue
    "#f0883e",  # orange
    "#ff7b72",  # red
    "#d2a8ff",  # purple
    "#79c0ff",  # light blue
    "#ffa657",  # amber
    "#7ee787",  # lime
    "#ff9bce",  # pink
    "#a5d6ff",  # sky
]


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

class _SimWorker(QThread):
    """Run simulation in a background thread."""

    finished = Signal(SimulationResult)

    def __init__(self, netlist: str, config: AnalysisConfig, parent=None):
        super().__init__(parent)
        self._netlist = netlist
        self._config = config

    def run(self):
        engine = NgSpiceEngine()
        if engine.available:
            result = engine.run(self._netlist, self._config)
        else:
            solver = PythonSolver()
            result = solver.solve(self._netlist, self._config)
            if not result.engine_used:
                result.engine_used = "built-in"
        self.finished.emit(result)


# ---------------------------------------------------------------------------
# SimulationView
# ---------------------------------------------------------------------------

class SimulationView(QWidget):
    """SPICE simulation tab with controls and waveform display."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._spec: CircuitSpec | None = None
        self._writer: SpiceNetlistWriter | None = None
        self._worker: _SimWorker | None = None
        self._last_result: SimulationResult | None = None

        self._setup_ui()
        Translator.instance().language_changed.connect(self._retranslate)
        ThemeManager.instance().theme_changed.connect(self._apply_theme)
        self._retranslate()
        self._apply_theme()

    # ------------------------------------------------------------------ UI

    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ---- Left panel: controls ----
        left = QWidget()
        left.setMaximumWidth(320)
        left.setMinimumWidth(250)
        lv = QVBoxLayout(left)
        lv.setContentsMargins(8, 8, 8, 8)

        # Analysis type
        self._grp_analysis = QGroupBox()
        ga = QVBoxLayout(self._grp_analysis)

        self._lbl_type = QLabel()
        self._cmb_type = QComboBox()
        self._cmb_type.addItems(["DC Operating Point", "Transient", "AC Sweep", "DC Sweep"])
        self._cmb_type.currentIndexChanged.connect(self._on_type_changed)
        ga.addWidget(self._lbl_type)
        ga.addWidget(self._cmb_type)
        lv.addWidget(self._grp_analysis)

        # Stacked parameter panels
        self._grp_params = QGroupBox()
        gp = QVBoxLayout(self._grp_params)

        self._param_stack = QStackedWidget()

        # Page 0: DC OP (no params)
        self._page_op = QWidget()
        QVBoxLayout(self._page_op).addWidget(QLabel(""))
        self._param_stack.addWidget(self._page_op)

        # Page 1: Transient
        self._page_tran = QWidget()
        tv = QVBoxLayout(self._page_tran)
        self._lbl_tstep = QLabel()
        self._spn_tstep = QDoubleSpinBox()
        self._spn_tstep.setDecimals(9)
        self._spn_tstep.setRange(1e-12, 1.0)
        self._spn_tstep.setValue(1e-6)
        self._spn_tstep.setSuffix(" s")
        tv.addWidget(self._lbl_tstep)
        tv.addWidget(self._spn_tstep)

        self._lbl_tstop = QLabel()
        self._spn_tstop = QDoubleSpinBox()
        self._spn_tstop.setDecimals(6)
        self._spn_tstop.setRange(1e-9, 100.0)
        self._spn_tstop.setValue(1e-3)
        self._spn_tstop.setSuffix(" s")
        tv.addWidget(self._lbl_tstop)
        tv.addWidget(self._spn_tstop)
        tv.addStretch()
        self._param_stack.addWidget(self._page_tran)

        # Page 2: AC Sweep
        self._page_ac = QWidget()
        av = QVBoxLayout(self._page_ac)
        self._lbl_fstart = QLabel()
        self._spn_fstart = QDoubleSpinBox()
        self._spn_fstart.setDecimals(1)
        self._spn_fstart.setRange(0.001, 1e12)
        self._spn_fstart.setValue(1.0)
        self._spn_fstart.setSuffix(" Hz")
        av.addWidget(self._lbl_fstart)
        av.addWidget(self._spn_fstart)

        self._lbl_fstop = QLabel()
        self._spn_fstop = QDoubleSpinBox()
        self._spn_fstop.setDecimals(1)
        self._spn_fstop.setRange(1.0, 1e12)
        self._spn_fstop.setValue(1e6)
        self._spn_fstop.setSuffix(" Hz")
        av.addWidget(self._lbl_fstop)
        av.addWidget(self._spn_fstop)

        self._lbl_npoints = QLabel("Points:")
        self._spn_npoints = QDoubleSpinBox()
        self._spn_npoints.setDecimals(0)
        self._spn_npoints.setRange(10, 10000)
        self._spn_npoints.setValue(100)
        av.addWidget(self._lbl_npoints)
        av.addWidget(self._spn_npoints)

        self._lbl_sweep_type = QLabel("Sweep:")
        self._cmb_sweep = QComboBox()
        self._cmb_sweep.addItems(["dec", "lin", "oct"])
        av.addWidget(self._lbl_sweep_type)
        av.addWidget(self._cmb_sweep)
        av.addStretch()
        self._param_stack.addWidget(self._page_ac)

        # Page 3: DC Sweep
        self._page_dc = QWidget()
        dv = QVBoxLayout(self._page_dc)
        self._lbl_source = QLabel()
        self._cmb_source = QComboBox()
        dv.addWidget(self._lbl_source)
        dv.addWidget(self._cmb_source)

        self._lbl_vstart = QLabel("Start:")
        self._spn_vstart = QDoubleSpinBox()
        self._spn_vstart.setDecimals(3)
        self._spn_vstart.setRange(-1000, 1000)
        self._spn_vstart.setValue(0.0)
        self._spn_vstart.setSuffix(" V")
        dv.addWidget(self._lbl_vstart)
        dv.addWidget(self._spn_vstart)

        self._lbl_vstop = QLabel("Stop:")
        self._spn_vstop = QDoubleSpinBox()
        self._spn_vstop.setDecimals(3)
        self._spn_vstop.setRange(-1000, 1000)
        self._spn_vstop.setValue(5.0)
        self._spn_vstop.setSuffix(" V")
        dv.addWidget(self._lbl_vstop)
        dv.addWidget(self._spn_vstop)

        self._lbl_vstep = QLabel("Step:")
        self._spn_vstep = QDoubleSpinBox()
        self._spn_vstep.setDecimals(3)
        self._spn_vstep.setRange(0.001, 100)
        self._spn_vstep.setValue(0.1)
        self._spn_vstep.setSuffix(" V")
        dv.addWidget(self._lbl_vstep)
        dv.addWidget(self._spn_vstep)
        dv.addStretch()
        self._param_stack.addWidget(self._page_dc)

        gp.addWidget(self._param_stack)
        lv.addWidget(self._grp_params)

        # Run button
        self._btn_run = QPushButton()
        self._btn_run.clicked.connect(self._run_simulation)
        self._btn_run.setEnabled(False)
        lv.addWidget(self._btn_run)

        # Status
        self._lbl_status = QLabel("")
        self._lbl_status.setWordWrap(True)
        lv.addWidget(self._lbl_status)

        # Signal selector
        self._grp_signals = QGroupBox()
        gs = QVBoxLayout(self._grp_signals)
        self._signal_list = QListWidget()
        self._signal_list.itemChanged.connect(self._on_signal_toggled)
        gs.addWidget(self._signal_list)
        lv.addWidget(self._grp_signals)

        # Netlist viewer toggle
        self._btn_netlist = QPushButton("📄 SPICE Netlist")
        self._btn_netlist.setCheckable(True)
        self._btn_netlist.clicked.connect(self._toggle_netlist)
        lv.addWidget(self._btn_netlist)

        lv.addStretch()
        splitter.addWidget(left)

        # ---- Right panel: plot / results ----
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)

        # Stacked: plot or OP table or netlist
        self._result_stack = QStackedWidget()

        # Page 0: placeholder
        self._page_empty = QLabel()
        self._page_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._page_empty.setStyleSheet("font-size: 16px;")
        self._result_stack.addWidget(self._page_empty)

        # Page 1: waveform plot
        if _HAS_PG:
            self._plot_widget = pg.PlotWidget()
            self._plot_widget.showGrid(x=True, y=True, alpha=0.3)
            self._plot_widget.setLabel("bottom", "")
            self._plot_widget.setLabel("left", "")
            self._legend = self._plot_widget.addLegend(
                offset=(10, 10),
                brush=pg.mkBrush("#161b2280"),
                pen=pg.mkPen("#30363d"),
            )
            # Crosshair
            self._vline = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen("#484f58", style=Qt.PenStyle.DashLine))
            self._hline = pg.InfiniteLine(angle=0, movable=False, pen=pg.mkPen("#484f58", style=Qt.PenStyle.DashLine))
            self._plot_widget.addItem(self._vline, ignoreBounds=True)
            self._plot_widget.addItem(self._hline, ignoreBounds=True)
            self._crosshair_label = pg.TextItem(anchor=(0, 1), color="#8b949e")
            self._plot_widget.addItem(self._crosshair_label, ignoreBounds=True)
            self._plot_widget.scene().sigMouseMoved.connect(self._on_mouse_moved)
            self._result_stack.addWidget(self._plot_widget)
        else:
            self._plot_widget = None
            self._result_stack.addWidget(QLabel("pyqtgraph not installed"))

        # Page 2: OP table
        self._op_table = QTableWidget()
        self._op_table.setColumnCount(2)
        self._op_table.setHorizontalHeaderLabels(["Node / Branch", "Value"])
        self._op_table.horizontalHeader().setStretchLastSection(True)
        self._result_stack.addWidget(self._op_table)

        # Page 3: netlist text
        self._netlist_view = QTextEdit()
        self._netlist_view.setReadOnly(True)
        self._result_stack.addWidget(self._netlist_view)

        rv.addWidget(self._result_stack)
        splitter.addWidget(right)

        splitter.setSizes([280, 720])
        layout.addWidget(splitter)

    # ------------------------------------------------------------------ i18n

    def _retranslate(self):
        self._grp_analysis.setTitle(tr("sim_analysis_type"))
        self._cmb_type.setItemText(0, tr("sim_dc_op"))
        self._cmb_type.setItemText(1, tr("sim_transient"))
        self._cmb_type.setItemText(2, tr("sim_ac_sweep"))
        self._cmb_type.setItemText(3, tr("sim_dc_sweep"))
        self._grp_params.setTitle(tr("sim_parameters"))
        self._lbl_tstep.setText(tr("sim_time_step"))
        self._lbl_tstop.setText(tr("sim_time_stop"))
        self._lbl_fstart.setText(tr("sim_freq_start"))
        self._lbl_fstop.setText(tr("sim_freq_stop"))
        self._lbl_source.setText(tr("sim_source"))
        self._btn_run.setText(tr("sim_run"))
        self._grp_signals.setTitle(tr("sim_signals"))
        self._page_empty.setText(tr("sim_no_circuit"))
        self._lbl_type.setText(tr("sim_analysis_type"))

    def _apply_theme(self):
        c = tc()
        self._btn_run.setStyleSheet(
            f"QPushButton {{ background-color: {c.button_green}; color: white; "
            f"font-weight: bold; padding: 8px; border-radius: 6px; }}"
            f"QPushButton:hover {{ background-color: {c.button_green_hover}; }}"
            f"QPushButton:disabled {{ background-color: {c.bg_secondary}; color: {c.text_dim}; }}"
        )
        self._lbl_status.setStyleSheet(f"color: {c.text_dim}; font-size: 11px;")
        self._page_empty.setStyleSheet(f"color: {c.text_dim}; font-size: 16px;")
        self._op_table.setStyleSheet(
            f"QTableWidget {{ background-color: {c.bg}; color: {c.text}; gridline-color: {c.border_light}; }}"
            f"QHeaderView::section {{ background-color: {c.bg_secondary}; color: {c.text}; padding: 4px; }}"
        )
        self._netlist_view.setStyleSheet(
            f"QTextEdit {{ background-color: {c.bg}; color: {c.success}; "
            f"font-family: 'Consolas', 'Courier New', monospace; font-size: 12px; }}"
        )
        if _HAS_PG and self._plot_widget:
            pg.setConfigOptions(background=c.bg, foreground=c.text)
            self._plot_widget.setBackground(c.bg)
            pi = self._plot_widget.plotItem
            for axis_name in ("left", "bottom"):
                ax = pi.getAxis(axis_name)
                ax.setPen(c.text)
                ax.setTextPen(c.text)

    # ------------------------------------------------------------------ API

    def load_circuit(self, spec: CircuitSpec):
        """Load a circuit specification for simulation."""
        self._spec = spec
        self._writer = SpiceNetlistWriter(spec)
        self._btn_run.setEnabled(True)
        self._lbl_status.setText("")

        # Populate signal list from net nodes
        self._signal_list.clear()
        for node in self._writer.get_all_nodes():
            item = QListWidgetItem(f"v({node})")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self._signal_list.addItem(item)

        # Populate voltage source combo for DC sweep
        self._cmb_source.clear()
        sources = self._writer.get_voltage_sources()
        if sources:
            self._cmb_source.addItems(sources)

        self._result_stack.setCurrentIndex(0)

    # ------------------------------------------------------------------ slots

    @Slot(int)
    def _on_type_changed(self, idx: int):
        self._param_stack.setCurrentIndex(idx)

    @Slot()
    def _run_simulation(self):
        if not self._spec or not self._writer:
            return

        config = self._build_config()

        # Generate netlist
        netlist = self._writer.generate(config)
        self._netlist_view.setPlainText(netlist)

        # Disable run button
        self._btn_run.setEnabled(False)
        self._lbl_status.setText(tr("sim_running"))
        self._lbl_status.setStyleSheet(f"color: {tc().info}; font-size: 11px;")

        # Start worker
        self._worker = _SimWorker(netlist, config, self)
        self._worker.finished.connect(self._on_simulation_done)
        self._worker.start()

    @Slot(SimulationResult)
    def _on_simulation_done(self, result: SimulationResult):
        self._btn_run.setEnabled(True)
        self._last_result = result

        if not result.success:
            self._lbl_status.setText(tr("sim_error", error=result.error_message))
            self._lbl_status.setStyleSheet(f"color: {tc().error}; font-size: 11px;")
            return

        engine_msg = ""
        if result.engine_used == "built-in":
            engine_msg = f" ({tr('sim_no_ngspice')})"

        self._lbl_status.setText(tr("sim_complete") + engine_msg)
        self._lbl_status.setStyleSheet(f"color: {tc().success}; font-size: 11px;")

        if result.analysis_type == "op" and result.operating_point:
            self._show_op_results(result)
        else:
            self._show_waveform(result)

        # Update signal list
        self._signal_list.blockSignals(True)
        self._signal_list.clear()
        for name in result.signals:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            self._signal_list.addItem(item)
        self._signal_list.blockSignals(False)

    @Slot(QListWidgetItem)
    def _on_signal_toggled(self, item: QListWidgetItem):
        if self._last_result and self._last_result.analysis_type != "op":
            self._show_waveform(self._last_result)

    @Slot()
    def _toggle_netlist(self):
        if self._btn_netlist.isChecked():
            # Generate current netlist
            if self._writer:
                config = self._build_config()
                netlist = self._writer.generate(config)
                self._netlist_view.setPlainText(netlist)
            self._result_stack.setCurrentIndex(3)
        else:
            if self._last_result:
                if self._last_result.analysis_type == "op":
                    self._result_stack.setCurrentIndex(2)
                else:
                    self._result_stack.setCurrentIndex(1)
            else:
                self._result_stack.setCurrentIndex(0)

    def _on_mouse_moved(self, pos):
        if not _HAS_PG or not self._plot_widget:
            return
        vb = self._plot_widget.plotItem.vb
        mouse_point = vb.mapSceneToView(pos)
        x = mouse_point.x()
        y = mouse_point.y()
        self._vline.setPos(x)
        self._hline.setPos(y)
        self._crosshair_label.setText(f"x={x:.6g}  y={y:.6g}")
        self._crosshair_label.setPos(x, y)

    # ------------------------------------------------------------------ display

    def _show_op_results(self, result: SimulationResult):
        """Show DC operating point in a table."""
        op = result.operating_point
        if not op:
            return

        rows = []
        for name, val in sorted(op.node_voltages.items()):
            rows.append((f"V({name})", f"{val:.6g} V"))
        for name, val in sorted(op.branch_currents.items()):
            rows.append((f"I({name})", f"{val:.6g} A"))

        self._op_table.setRowCount(len(rows))
        for r, (label, value) in enumerate(rows):
            self._op_table.setItem(r, 0, QTableWidgetItem(label))
            self._op_table.setItem(r, 1, QTableWidgetItem(value))

        self._op_table.resizeColumnsToContents()
        self._result_stack.setCurrentIndex(2)

    def _show_waveform(self, result: SimulationResult):
        """Plot waveform data in pyqtgraph."""
        if not _HAS_PG or not self._plot_widget:
            return
        if not result.x_axis or not result.signals:
            return

        self._plot_widget.clear()
        # Re-add crosshair
        self._plot_widget.addItem(self._vline, ignoreBounds=True)
        self._plot_widget.addItem(self._hline, ignoreBounds=True)
        self._plot_widget.addItem(self._crosshair_label, ignoreBounds=True)

        # Add legend
        self._legend = self._plot_widget.addLegend(
            offset=(10, 10),
            brush=pg.mkBrush(tc().bg_secondary + "80"),
            pen=pg.mkPen(tc().border),
        )

        x_data = result.x_axis.values
        self._plot_widget.setLabel("bottom", result.x_axis.name, units=result.x_axis.unit)

        # Get checked signals
        checked: set[str] = set()
        for i in range(self._signal_list.count()):
            item = self._signal_list.item(i)
            if item and item.checkState() == Qt.CheckState.Checked:
                checked.add(item.text())

        color_idx = 0
        for name, waveform in result.signals.items():
            if checked and name not in checked:
                continue
            color = _SIGNAL_COLORS[color_idx % len(_SIGNAL_COLORS)]
            pen = pg.mkPen(color, width=2)
            self._plot_widget.plot(
                x_data[:len(waveform.values)],
                waveform.values[:len(x_data)],
                pen=pen,
                name=name,
            )
            color_idx += 1

        # Set Y label based on analysis
        if result.analysis_type == "ac":
            self._plot_widget.setLabel("left", "Magnitude", units="dB")
            self._plot_widget.setLogMode(x=True, y=False)
        else:
            self._plot_widget.setLabel("left", "Voltage", units="V")
            self._plot_widget.setLogMode(x=False, y=False)

        self._result_stack.setCurrentIndex(1)

    # ------------------------------------------------------------------ helpers

    def _build_config(self) -> AnalysisConfig:
        idx = self._cmb_type.currentIndex()
        config = AnalysisConfig()

        if idx == 0:
            config.analysis_type = "op"
        elif idx == 1:
            config.analysis_type = "tran"
            config.tran_step = self._spn_tstep.value()
            config.tran_stop = self._spn_tstop.value()
        elif idx == 2:
            config.analysis_type = "ac"
            config.ac_f_start = self._spn_fstart.value()
            config.ac_f_stop = self._spn_fstop.value()
            config.ac_n_points = int(self._spn_npoints.value())
            config.ac_sweep_type = self._cmb_sweep.currentText()
        elif idx == 3:
            config.analysis_type = "dc"
            config.dc_source = self._cmb_source.currentText()
            config.dc_start = self._spn_vstart.value()
            config.dc_stop = self._spn_vstop.value()
            config.dc_step = self._spn_vstep.value()

        return config
