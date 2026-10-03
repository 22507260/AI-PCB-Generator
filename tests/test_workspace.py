"""Dock visibility, translation and existing zoom-action integration."""

import pytest

from src.gui.i18n import Translator, tr
from src.gui.view3d import View3D


def test_workspace_panels_and_language(qtbot, monkeypatch):
    import src.gui.main_window as main_module

    monkeypatch.setattr(main_module, "View3D", lambda: View3D(force_fallback=True))
    window = main_module.MainWindow()
    qtbot.addWidget(window)
    window.show()
    original = Translator.instance().language
    try:
        for lang in ("en", "tr"):
            Translator.instance().set_language(lang)
            for key, dock in window._docks.items():
                assert dock.windowTitle() == tr("dock_" + key)
                dock.hide()
                assert not dock.isVisible()
                dock.toggleViewAction().trigger()
                assert dock.isVisible()
        window._tab_widget.setCurrentIndex(2)
        before = window._view_3d._fallback._zoom
        window._zoom_active_view(1.25)
        assert window._view_3d._fallback._zoom == pytest.approx(before * 1.25)
        assert window.minimumWidth() <= 960
        assert window._tab_widget.count() == 5
    finally:
        Translator.instance().set_language(original)
