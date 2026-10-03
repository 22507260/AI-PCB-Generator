"""Desktop GL smoke test; software CI still exercises geometry and fallback."""

import os

import pytest
from PySide6.QtCore import Qt

from src.gui.view3d import View3D
from src.pcb.generator import Board, BoardOutline, Pad, PlacedComponent, TraceSegment


@pytest.mark.skipif(
    os.environ.get("QT_QPA_PLATFORM") in ("offscreen", "minimal"),
    reason="Requires a desktop OpenGL context",
)
def test_desktop_render_camera_visibility_and_clear(qtbot):
    view = View3D()
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.show()
    qtbot.waitUntil(lambda: view._using_fallback or view._canvas._ready, timeout=3000)
    if view._using_fallback:
        pytest.skip("No desktop OpenGL context available")
    board = Board(
        outline=BoardOutline(0, 0, 30, 20),
        components=[
            PlacedComponent(
                ref="R1",
                x_mm=10,
                y_mm=10,
                footprint="0805",
                pads=[Pad(x_mm=9, y_mm=10), Pad(x_mm=11, y_mm=10)],
            )
        ],
        traces=[TraceSegment(start_x=2, start_y=2, end_x=20, end_y=2)],
    )
    view.load_board(board)
    qtbot.wait(100)
    frame = view._canvas.grabFramebuffer()
    assert not frame.isNull()
    assert not view._canvas._error
    assert not view._using_fallback
    center = frame.pixelColor(frame.width() // 2, frame.height() // 2)
    corner = frame.pixelColor(2, 2)
    assert center != corner
    view._camera_action("bottom")
    assert view._canvas.camera.pitch == 180
    qtbot.mousePress(view._canvas, Qt.MouseButton.LeftButton)
    qtbot.mouseRelease(view._canvas, Qt.MouseButton.LeftButton)
    view._actions["components"].setChecked(False)
    assert not view._canvas.visible_groups["components"]
    view._actions["silk"].setChecked(False)
    assert not view._canvas.show_silk
    view._actions["models"].setChecked(False)
    qtbot.wait(50)
    assert not view._canvas._error
    view.clear_board()
    qtbot.wait(50)
    assert not any(view._canvas.scene.groups.values())
    assert not view._canvas._error
