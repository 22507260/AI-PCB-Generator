"""Application bootstrap — creates QApplication and launches the main window."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from src.gui.main_window import MainWindow
from src.gui.theme import DARK_THEME, LIGHT_THEME
from src.gui.i18n import Translator
from src.config import get_settings
from src.utils.logger import setup_logging


def main():
    """Application entry point."""
    logger = setup_logging()
    logger.info("Starting AI PCB Generator...")

    app = QApplication(sys.argv)
    app.setApplicationName("AI PCB Generator")
    app.setOrganizationName("AI PCB")
    app.setApplicationVersion("0.1.0")

    # Apply saved settings
    settings = get_settings()
    Translator.instance().set_language(settings.language)

    if settings.theme == "dark":
        app.setStyleSheet(DARK_THEME)
    else:
        app.setStyleSheet(LIGHT_THEME)

    window = MainWindow()
    window.show()

    logger.info("Application window opened.")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
