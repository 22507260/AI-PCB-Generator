"""Theme stylesheet & dynamic color provider for the application."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor


# =====================================================================
# Dynamic color palette — used by widgets that can't rely on global QSS
# (QGraphicsScene backgrounds, pyqtgraph, custom-painted widgets, etc.)
# =====================================================================

class _Colors:
    """Named color set for one theme variant."""

    __slots__ = (
        "bg", "bg_secondary", "bg_input", "surface",
        "text", "text_dim", "border", "border_light",
        "accent", "accent_hover",
        "success", "warning", "error", "info",
        "scene_bg", "scene_grid", "scene_text",
        "view3d_bg_top", "view3d_bg_mid", "view3d_bg_bottom", "view3d_grid",
        "bar_bg", "bar_border",
        "header_bg", "header_text",
        "hover_bg", "selected_bg",
        "button_green", "button_green_hover",
    )

    def __init__(self, **kw: str):
        for k, v in kw.items():
            setattr(self, k, v)


_DARK = _Colors(
    bg="#0d1117",          bg_secondary="#161b22",   bg_input="#0d1117",
    surface="#1a1a2e",     text="#e6edf3",           text_dim="#8b949e",
    border="#30363d",      border_light="#21262d",
    accent="#8957e5",      accent_hover="#a371f7",
    success="#3fb950",     warning="#d29922",        error="#f85149",
    info="#58a6ff",
    scene_bg="#0d1117",    scene_grid="#1a2030",     scene_text="#e6edf3",
    view3d_bg_top="#0C1218",  view3d_bg_mid="#101820",
    view3d_bg_bottom="#0A1014", view3d_grid="#1a2530",
    bar_bg="#111820",      bar_border="#1e2a3a",
    header_bg="#161b22",   header_text="#8b949e",
    hover_bg="#1c2333",    selected_bg="#1f6feb",
    button_green="#238636", button_green_hover="#2ea043",
)

_LIGHT = _Colors(
    bg="#ffffff",          bg_secondary="#f6f8fa",   bg_input="#ffffff",
    surface="#f6f8fa",     text="#24292f",            text_dim="#57606a",
    border="#d0d7de",      border_light="#eaeef2",
    accent="#6d28d9",      accent_hover="#7c3aed",
    success="#16a34a",     warning="#b45309",         error="#dc2626",
    info="#2563eb",
    scene_bg="#f8f9fb",    scene_grid="#e2e6ea",      scene_text="#24292f",
    view3d_bg_top="#e8ecf0",  view3d_bg_mid="#dce0e5",
    view3d_bg_bottom="#d0d5da", view3d_grid="#c4cad0",
    bar_bg="#f0f2f5",      bar_border="#d0d7de",
    header_bg="#eaeef2",   header_text="#57606a",
    hover_bg="#e2e8f0",    selected_bg="#dbeafe",
    button_green="#1a7f37", button_green_hover="#2da44e",
)


class ThemeManager(QObject):
    """Singleton that tracks the active theme and emits on change."""

    theme_changed = Signal()
    _instance: ThemeManager | None = None

    def __init__(self):
        super().__init__()
        self._dark = True

    @classmethod
    def instance(cls) -> ThemeManager:
        if cls._instance is None:
            cls._instance = ThemeManager()
        return cls._instance

    @property
    def is_dark(self) -> bool:
        return self._dark

    def set_dark(self, dark: bool) -> None:
        if dark != self._dark:
            self._dark = dark
            self.theme_changed.emit()

    @property
    def colors(self) -> _Colors:
        return _DARK if self._dark else _LIGHT


def tc() -> _Colors:
    """Module-level shortcut — returns the active color set."""
    return ThemeManager.instance().colors


# =====================================================================
# Global QSS stylesheets
# =====================================================================

DARK_THEME = """
QMainWindow, QDialog {
    background-color: #1a1a2e;
    color: #e0e0e0;
}

QWidget {
    background-color: #1a1a2e;
    color: #e0e0e0;
    font-family: "Segoe UI", "Arial", sans-serif;
    font-size: 13px;
}

QMenuBar {
    background-color: #16213e;
    color: #e0e0e0;
    border-bottom: 1px solid #0f3460;
    padding: 2px;
}

QMenuBar::item:selected {
    background-color: #0f3460;
    border-radius: 4px;
}

QMenu {
    background-color: #16213e;
    color: #e0e0e0;
    border: 1px solid #0f3460;
}

QMenu::item:selected {
    background-color: #0f3460;
}

QToolBar {
    background-color: #16213e;
    border-bottom: 1px solid #0f3460;
    spacing: 4px;
    padding: 2px;
}

QToolButton {
    background-color: transparent;
    color: #e0e0e0;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 12px;
}

QToolButton:hover {
    background-color: #0f3460;
    border: 1px solid #533483;
}

QToolButton:pressed {
    background-color: #533483;
}

QStatusBar {
    background-color: #16213e;
    color: #a0a0a0;
    border-top: 1px solid #0f3460;
}

QSplitter::handle {
    background-color: #0f3460;
    width: 2px;
    height: 2px;
}

QTabWidget::pane {
    border: 1px solid #0f3460;
    background-color: #1a1a2e;
}

QTabBar::tab {
    background-color: #16213e;
    color: #a0a0a0;
    border: 1px solid #0f3460;
    padding: 8px 16px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}

QTabBar::tab:selected {
    background-color: #1a1a2e;
    color: #e0e0e0;
    border-bottom-color: #1a1a2e;
}

QTabBar::tab:hover {
    background-color: #0f3460;
}

QTextEdit, QPlainTextEdit {
    background-color: #0d1117;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 8px;
    font-family: "Cascadia Code", "Consolas", monospace;
    font-size: 13px;
    selection-background-color: #264f78;
}

QLineEdit {
    background-color: #0d1117;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 6px 10px;
}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border-color: #533483;
}

QPushButton {
    background-color: #533483;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 8px 20px;
    font-weight: bold;
    font-size: 13px;
}

QPushButton:hover {
    background-color: #6c4ab6;
}

QPushButton:pressed {
    background-color: #3d2566;
}

QPushButton:disabled {
    background-color: #3d3d5c;
    color: #6b6b8a;
}

QPushButton#secondaryButton {
    background-color: #0f3460;
    color: #e0e0e0;
}

QPushButton#secondaryButton:hover {
    background-color: #1a4a7a;
}

QPushButton#dangerButton {
    background-color: #c83232;
}

QPushButton#dangerButton:hover {
    background-color: #e04040;
}

QTableWidget, QTableView {
    background-color: #0d1117;
    color: #c9d1d9;
    border: 1px solid #30363d;
    gridline-color: #21262d;
    selection-background-color: #264f78;
    border-radius: 6px;
}

QTableWidget::item {
    padding: 4px 8px;
}

QHeaderView::section {
    background-color: #161b22;
    color: #e0e0e0;
    border: 1px solid #21262d;
    padding: 6px;
    font-weight: bold;
}

QScrollBar:vertical {
    background-color: #1a1a2e;
    width: 10px;
    border: none;
}

QScrollBar::handle:vertical {
    background-color: #30363d;
    border-radius: 5px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background-color: #484f58;
}

QScrollBar::add-line, QScrollBar::sub-line {
    height: 0px;
}

QScrollBar:horizontal {
    background-color: #1a1a2e;
    height: 10px;
    border: none;
}

QScrollBar::handle:horizontal {
    background-color: #30363d;
    border-radius: 5px;
    min-width: 30px;
}

QGroupBox {
    border: 1px solid #30363d;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 16px;
    font-weight: bold;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #8b949e;
}

QComboBox {
    background-color: #0d1117;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 6px 10px;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox QAbstractItemView {
    background-color: #0d1117;
    color: #c9d1d9;
    border: 1px solid #30363d;
    selection-background-color: #264f78;
}

QCheckBox {
    spacing: 8px;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #30363d;
    border-radius: 3px;
    background-color: #0d1117;
}

QCheckBox::indicator:checked {
    background-color: #533483;
    border-color: #533483;
}

QProgressBar {
    border: 1px solid #30363d;
    border-radius: 4px;
    text-align: center;
    background-color: #0d1117;
    color: #e0e0e0;
    height: 20px;
}

QProgressBar::chunk {
    background-color: #533483;
    border-radius: 3px;
}

QLabel#titleLabel {
    font-size: 18px;
    font-weight: bold;
    color: #e0e0e0;
}

QLabel#subtitleLabel {
    font-size: 12px;
    color: #8b949e;
}

QLabel#warningLabel {
    color: #d29922;
}

QLabel#errorLabel {
    color: #f85149;
}

QLabel#successLabel {
    color: #3fb950;
}
"""

LIGHT_THEME = """
QMainWindow, QDialog {
    background-color: #f6f8fa;
    color: #24292f;
}

QWidget {
    background-color: #f6f8fa;
    color: #24292f;
    font-family: "Segoe UI", "Arial", sans-serif;
    font-size: 13px;
}

QMenuBar {
    background-color: #ffffff;
    color: #24292f;
    border-bottom: 1px solid #d0d7de;
    padding: 2px;
}

QMenuBar::item:selected {
    background-color: #e2e8f0;
    border-radius: 4px;
}

QMenu {
    background-color: #ffffff;
    color: #24292f;
    border: 1px solid #d0d7de;
}

QMenu::item:selected {
    background-color: #dbeafe;
    color: #1e40af;
}

QToolBar {
    background-color: #ffffff;
    border-bottom: 1px solid #d0d7de;
    spacing: 4px;
    padding: 2px;
}

QToolButton {
    background-color: transparent;
    color: #24292f;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 12px;
}

QToolButton:hover {
    background-color: #e2e8f0;
    border: 1px solid #6d28d9;
}

QToolButton:pressed {
    background-color: #ddd6fe;
}

QStatusBar {
    background-color: #ffffff;
    color: #57606a;
    border-top: 1px solid #d0d7de;
}

QSplitter::handle {
    background-color: #d0d7de;
    width: 2px;
    height: 2px;
}

QTabWidget::pane {
    border: 1px solid #d0d7de;
    background-color: #f6f8fa;
}

QTabBar::tab {
    background-color: #eaeef2;
    color: #57606a;
    border: 1px solid #d0d7de;
    padding: 8px 16px;
    margin-right: 2px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}

QTabBar::tab:selected {
    background-color: #f6f8fa;
    color: #24292f;
    border-bottom-color: #f6f8fa;
}

QTabBar::tab:hover {
    background-color: #dbeafe;
}

QTextEdit, QPlainTextEdit {
    background-color: #ffffff;
    color: #24292f;
    border: 1px solid #d0d7de;
    border-radius: 6px;
    padding: 8px;
    font-family: "Cascadia Code", "Consolas", monospace;
    font-size: 13px;
    selection-background-color: #bfdbfe;
}

QLineEdit {
    background-color: #ffffff;
    color: #24292f;
    border: 1px solid #d0d7de;
    border-radius: 6px;
    padding: 6px 10px;
}

QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border-color: #6d28d9;
}

QPushButton {
    background-color: #6d28d9;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 8px 20px;
    font-weight: bold;
    font-size: 13px;
}

QPushButton:hover {
    background-color: #7c3aed;
}

QPushButton:pressed {
    background-color: #5b21b6;
}

QPushButton:disabled {
    background-color: #c4b5fd;
    color: #f5f3ff;
}

QPushButton#secondaryButton {
    background-color: #e2e8f0;
    color: #334155;
}

QPushButton#secondaryButton:hover {
    background-color: #cbd5e1;
}

QPushButton#dangerButton {
    background-color: #dc2626;
}

QPushButton#dangerButton:hover {
    background-color: #ef4444;
}

QTableWidget, QTableView {
    background-color: #ffffff;
    color: #24292f;
    border: 1px solid #d0d7de;
    gridline-color: #eaeef2;
    selection-background-color: #dbeafe;
    border-radius: 6px;
    alternate-background-color: #f6f8fa;
}

QTableWidget::item {
    padding: 4px 8px;
}

QHeaderView::section {
    background-color: #eaeef2;
    color: #24292f;
    border: 1px solid #d0d7de;
    padding: 6px;
    font-weight: bold;
}

QScrollBar:vertical {
    background-color: #f6f8fa;
    width: 10px;
    border: none;
}

QScrollBar::handle:vertical {
    background-color: #c1c7cd;
    border-radius: 5px;
    min-height: 30px;
}

QScrollBar::handle:vertical:hover {
    background-color: #9ca3af;
}

QScrollBar::add-line, QScrollBar::sub-line {
    height: 0px;
}

QScrollBar:horizontal {
    background-color: #f6f8fa;
    height: 10px;
    border: none;
}

QScrollBar::handle:horizontal {
    background-color: #c1c7cd;
    border-radius: 5px;
    min-width: 30px;
}

QGroupBox {
    border: 1px solid #d0d7de;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 16px;
    font-weight: bold;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #57606a;
}

QComboBox {
    background-color: #ffffff;
    color: #24292f;
    border: 1px solid #d0d7de;
    border-radius: 6px;
    padding: 6px 10px;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox QAbstractItemView {
    background-color: #ffffff;
    color: #24292f;
    border: 1px solid #d0d7de;
    selection-background-color: #dbeafe;
}

QCheckBox {
    spacing: 8px;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #d0d7de;
    border-radius: 3px;
    background-color: #ffffff;
}

QCheckBox::indicator:checked {
    background-color: #6d28d9;
    border-color: #6d28d9;
}

QProgressBar {
    border: 1px solid #d0d7de;
    border-radius: 4px;
    text-align: center;
    background-color: #eaeef2;
    color: #24292f;
    height: 20px;
}

QProgressBar::chunk {
    background-color: #6d28d9;
    border-radius: 3px;
}

QLabel#titleLabel {
    font-size: 18px;
    font-weight: bold;
    color: #24292f;
}

QLabel#subtitleLabel {
    font-size: 12px;
    color: #57606a;
}

QLabel#warningLabel {
    color: #b45309;
}

QLabel#errorLabel {
    color: #dc2626;
}

QLabel#successLabel {
    color: #16a34a;
}
"""
