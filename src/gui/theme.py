"""Dark theme stylesheet for the application."""

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
