"""PCB inspection workspace with an optional OpenGL renderer."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from src.config import get_settings
from src.gui.i18n import Translator, tr
from src.gui.theme import ThemeManager
from src.models.model_registry import ModelRegistry
from src.models.pcb_scene import Scene, build_scene
from src.utils.logger import get_logger

log = get_logger("gui.view3d")


class View3D(QWidget):
    """Public board-loading interface shared by both renderers."""

    def __init__(self, parent=None, *, force_fallback=False):
        super().__init__(parent)
        self._board = None
        self._model_registry = ModelRegistry(get_settings().kicad_3dmodels_path)
        self._fallback = None
        self._using_fallback = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        controls = QHBoxLayout()
        controls.setContentsMargins(8, 6, 8, 6)
        controls.setSpacing(4)
        self._buttons = {}
        for name in ("iso", "top", "bottom", "fit"):
            button = QToolButton()
            button.clicked.connect(lambda checked=False, n=name: self._camera_action(n))
            controls.addWidget(button)
            self._buttons[name] = button
        controls.addStretch()
        self._layers = QToolButton()
        self._layers.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._layer_menu = QMenu(self._layers)
        self._layers.setMenu(self._layer_menu)
        self._actions = {}
        for key in ("components", "traces", "silk", "guides", "models"):
            action = self._layer_menu.addAction("")
            action.setCheckable(True)
            action.setChecked(key != "guides")
            action.toggled.connect(lambda checked, k=key: self._visibility(k, checked))
            self._actions[key] = action
        controls.addWidget(self._layers)
        self._color = QComboBox()
        self._color.setMaximumWidth(100)
        for key in ("green", "blue", "red", "black", "white", "purple"):
            self._color.addItem("", key)
        self._color.currentIndexChanged.connect(self._set_color)
        controls.addWidget(self._color)
        layout.addLayout(controls)
        self._stack = QStackedWidget()
        layout.addWidget(self._stack, 1)
        self._status = QLabel()
        self._status.setObjectName("subtitleLabel")
        self._status.setContentsMargins(10, 4, 10, 4)
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        self._canvas = None
        if not force_fallback:
            try:
                from OpenGL import GL  # noqa: F401

                from src.gui.gl_pcb_view import GLPCBView

                self._canvas = GLPCBView()
                self._canvas.failed.connect(
                    self._activate_fallback, Qt.ConnectionType.QueuedConnection
                )
                self._stack.addWidget(self._canvas)
            except (ImportError, RuntimeError) as exc:
                log.warning("OpenGL unavailable: %s", exc)
        if self._canvas is None:
            self._activate_fallback()
        self._retranslate()
        Translator.instance().language_changed.connect(self._retranslate)
        ThemeManager.instance().theme_changed.connect(self._theme_changed)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(500, self._check_context)

    def _check_context(self):
        if self.isVisible() and not self._using_fallback and not self._canvas.isValid():
            self._activate_fallback("Qt could not create an OpenGL context")

    def _activate_fallback(self, reason=""):
        if self._using_fallback:
            return
        from src.gui.legacy_view3d import _Canvas3D

        log.warning("Using software PCB preview: %s", reason)
        self._using_fallback = True
        self._fallback = _Canvas3D(self)
        self._fallback._model_registry = self._model_registry
        self._fallback._show_wires = False
        self._stack.addWidget(self._fallback)
        self._stack.setCurrentWidget(self._fallback)
        if self._board is not None:
            self._fallback.set_board(self._board)
            self._fit_fallback()
        for key, action in self._actions.items():
            self._visibility(key, action.isChecked())
        self._set_color()
        self._retranslate()

    def load_board(self, board):
        self._board = board
        if self._using_fallback:
            self._fallback.set_board(board)
            self._fit_fallback()
        else:
            self._canvas.set_scene(
                build_scene(board, self._model_registry, self._actions["models"].isChecked())
            )
        self._update_status()

    def clear_board(self):
        self._board = None
        if self._using_fallback:
            self._fallback.set_board(None)
            self._fallback.update()
        else:
            self._canvas.set_scene(Scene())
        self._update_status()

    def _fit_fallback(self):
        if self._board is not None:
            o = self._board.outline
            self._fallback._zoom = max(
                0.2,
                min(
                    self._stack.width() / max(1, o.width_mm + o.height_mm),
                    self._stack.height() / max(1, o.width_mm + o.height_mm),
                )
                * 0.9,
            )
        self._fallback._pan.setX(0)
        self._fallback._pan.setY(0)
        self._fallback._dirty = True
        self._fallback.update()

    def _camera_action(self, name):
        if self._using_fallback:
            if name != "fit":
                x, z = {"iso": (30, 45), "top": (90, 0), "bottom": (-90, 0)}[name]
                self._fallback._rot_x, self._fallback._rot_z = x, z
            self._fit_fallback()
        elif name == "fit":
            self._canvas.fit()
        else:
            self._canvas.preset(name)

    def zoom(self, factor):
        if self._using_fallback:
            self._fallback._zoom = max(0.2, min(50, self._fallback._zoom * factor))
            self._fallback._dirty = True
            self._fallback.update()
        else:
            self._canvas.zoom(factor)

    def _visibility(self, key, checked):
        if self._using_fallback:
            attr = {
                "components": "_show_components",
                "traces": "_show_traces",
                "silk": "_show_silkscreen",
                "guides": "_show_wires",
                "models": "_show_3d_models",
            }[key]
            setattr(self._fallback, attr, checked)
            self._fallback._dirty = True
            self._fallback.update()
        elif key == "models" and self._board is not None:
            self._canvas.set_scene(
                build_scene(self._board, self._model_registry, checked), fit=False
            )
        elif self._canvas:
            if key in ("components", "traces"):
                self._canvas.visible_groups[key] = checked
            elif key == "guides":
                self._canvas.show_guides = checked
            elif key == "silk":
                self._canvas.show_silk = checked
            self._canvas.update()

    def _set_color(self, *_):
        key = self._color.currentData()
        colors = {
            "green": "#0e5029",
            "blue": "#184674",
            "red": "#79282b",
            "black": "#202325",
            "white": "#d9dbd1",
            "purple": "#513270",
        }
        if self._using_fallback:
            self._fallback._board_style_override = key
            self._fallback._dirty = True
            self._fallback.update()
        elif self._canvas:
            c = QColor(colors[key])
            self._canvas.mask_color = (c.redF(), c.greenF(), c.blueF())
            self._canvas._dirty = True
            self._canvas.update()

    def _theme_changed(self):
        if self._using_fallback:
            self._fallback._dirty = True
        self._stack.currentWidget().update()

    def _update_status(self):
        if self._using_fallback:
            text = tr("view3d_fallback")
        elif self._board is None:
            text = tr("view3d_empty")
        else:
            o = self._board.outline
            text = tr(
                "view3d_dimensions",
                width=f"{o.width_mm:.1f}",
                height=f"{o.height_mm:.1f}",
                thickness=f"{self._board.thickness_mm:.1f}",
                count=len(self._board.components),
            )
        self._status.setText(text)
        self._status.setToolTip(tr("view3d_hint"))
        if self._board is not None:
            self._status.setText(text + "\n" + tr("view3d_hint"))

    def _retranslate(self):
        for key, button in self._buttons.items():
            button.setText(tr("view3d_" + key))
            button.setToolTip(tr("view3d_" + key))
        self._layers.setText(tr("view3d_layers"))
        for key, action in self._actions.items():
            action.setText(tr("view3d_" + key))
        for i in range(self._color.count()):
            self._color.setItemText(i, tr("color_" + self._color.itemData(i)))
        self._color.setToolTip(tr("view3d_pcb_color"))
        self._update_status()
