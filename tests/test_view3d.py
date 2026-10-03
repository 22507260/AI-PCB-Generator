"""Camera and software-fallback tests run without a graphics device."""

import numpy as np
import pytest
from PySide6.QtCore import QPointF

from src.gui.gl_pcb_view import Camera
from src.gui.i18n import Translator, tr
from src.gui.view3d import View3D
from src.pcb.generator import Board, BoardOutline


def test_zoom_keeps_cursor_anchor():
    camera = Camera()
    camera.fit(((0, 0, -2), (40, 30, 5)), 800, 600)
    point = (10, 20, 3)
    pos, _ = camera.project(point, 800, 600)
    camera.zoom(1.7, pos, 800, 600)
    after, _ = camera.project(point, 800, 600)
    assert after.x() == pytest.approx(pos.x())
    assert after.y() == pytest.approx(pos.y())


@pytest.mark.parametrize("width,height", [(800, 600), (300, 700)])
def test_fit_contains_all_corners(width, height):
    camera = Camera()
    bounds = ((-20, -50, -2), (40, 30, 8))
    camera.fit(bounds, width, height)
    for x in (bounds[0][0], bounds[1][0]):
        for y in (bounds[0][1], bounds[1][1]):
            for z in (bounds[0][2], bounds[1][2]):
                p, _ = camera.project((x, y, z), width, height)
                assert 0 <= p.x() <= width and 0 <= p.y() <= height


def test_zoom_limits_and_preset_back_orientation():
    camera = Camera(pitch=180, yaw=0)
    assert (camera.rotation() @ np.array([0, 0, 1]))[2] == pytest.approx(-1)
    camera.zoom(1e10, QPointF(0, 0), 800, 600)
    assert camera.span == camera.radius * 0.03


def test_fallback_load_toggle_translate_and_clear(qtbot):
    view = View3D(force_fallback=True)
    qtbot.addWidget(view)
    view.resize(640, 480)
    view.show()
    board = Board(outline=BoardOutline(width_mm=40, height_mm=30))
    view.load_board(board)
    assert view._using_fallback
    assert view._fallback._board is board
    assert not view._fallback._show_wires
    view._actions["components"].setChecked(False)
    assert not view._fallback._show_components
    view._camera_action("bottom")
    assert view._fallback._rot_x == -90
    original = Translator.instance().language
    try:
        for lang in ("en", "tr"):
            Translator.instance().set_language(lang)
            assert view._buttons["top"].text() == tr("view3d_top")
            assert view._status.text().startswith(tr("view3d_fallback"))
    finally:
        Translator.instance().set_language(original)
    view.clear_board()
    assert view._fallback._board is None


def test_fallback_does_not_invent_board_features(qtbot):
    view = View3D(force_fallback=True)
    qtbot.addWidget(view)
    style = view._fallback._determine_board_style(Board())
    assert not style["mounting_holes"]
    assert not style["copper_pour"]
    assert style["style"] == "green"

