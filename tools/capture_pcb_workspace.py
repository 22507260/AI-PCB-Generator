"""Reproducible local visual QA. Requires a desktop OpenGL context, no API key.

Run from the repository root: python tools/capture_pcb_workspace.py
Screenshots go to assets/screenshots/. Synthetic motor fixture is visual QA
only; it is not an electrically validated production design.
"""

from __future__ import annotations

import json
import subprocess
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from src.ai.schemas import CircuitSpec
from src.gui.i18n import Translator
from src.gui.main_window import MainWindow
from src.gui.theme import DARK_THEME, LIGHT_THEME, ThemeManager
from src.gui.view3d import View3D
from src.pcb.generator import PCBGenerator


def motor_spec():
    def comp(ref, value, category, package, count, x, y):
        return {
            "ref": ref,
            "value": value,
            "category": category,
            "package": package,
            "pins": [{"number": str(i + 1), "name": str(i + 1)} for i in range(count)],
            "x_mm": x,
            "y_mm": y,
        }

    return CircuitSpec.model_validate(
        {
            "name": "Motor driver visual fixture",
            "components": [
                comp("U1", "L293D", "ic", "DIP-16", 16, 22, 20),
                comp("J1", "Power", "connector", "PinHeader_1x02_P2.54mm", 2, 8, 9),
                comp("J2", "Motor", "connector", "PinHeader_1x02_P2.54mm", 2, 40, 20),
                comp(
                    "C1", "100uF electrolytic", "capacitor", "CP_Radial_D5.0mm_P2.50mm", 2, 10, 27
                ),
                comp("C2", "100nF", "capacitor", "0805", 2, 31, 9),
                comp("R1", "330", "resistor", "Axial", 2, 25, 35),
                comp("D1", "LED red", "led", "LED_D3.0mm", 2, 39, 35),
            ],
            "nets": [
                {
                    "name": "GND",
                    "connections": [{"ref": ref, "pin": "2"} for ref in ["J1", "J2", "C1", "C2"]],
                }
            ],
        }
    )


def capture():
    out = ROOT / "assets/screenshots"
    out.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    Translator.instance().set_language("en")
    app.setStyleSheet(DARK_THEME)
    specs = {
        name: CircuitSpec.model_validate(
            json.loads((ROOT / "data/examples" / f"{name}.apcb").read_text(encoding="utf-8"))[
                "circuit"
            ]
        )
        for name in ("led_circuit", "voltage_regulator")
    }
    specs["motor_driver"] = motor_spec()
    boards = {name: PCBGenerator(spec).generate() for name, spec in specs.items()}
    # Pinned pre-change renderer, so future screenshots do not silently compare
    # against a moving baseline. This does not modify the checkout.
    source = subprocess.check_output(["git", "show", "9eae9db:src/gui/view3d.py"], cwd=ROOT).decode(
        "utf-8"
    )
    baseline = types.ModuleType("src.gui._baseline_view3d")
    exec(compile(source, "baseline_view3d.py", "exec"), baseline.__dict__)  # noqa: S102 -- Pinned local Git source.
    before = baseline.View3D()
    before.resize(1000, 700)
    before.load_board(boards["motor_driver"])
    before.show()
    QTest.qWait(500)
    # Match physical pitch/yaw and pixel scale across both implementations.
    before._canvas._rot_x, before._canvas._rot_z = 30, 45
    before._canvas._zoom = 8
    before._canvas._dirty = True
    before._canvas.update()
    QTest.qWait(100)
    before.grab().save(str(out / "3d-before.png"))
    before.close()
    view = View3D()
    view.resize(1000, 700)
    view.show()
    QTest.qWait(700)
    if view._using_fallback:
        raise RuntimeError("Visual QA requires a working OpenGL renderer")
    for name, board in boards.items():
        view.load_board(board)
        QTest.qWait(250)
        if view._using_fallback or view._canvas._error:
            raise RuntimeError("OpenGL failed during capture")
        view._canvas.grabFramebuffer().save(str(out / f"3d-{name}.png"))
    view.load_board(boards["motor_driver"])
    QTest.qWait(100)
    o = boards["motor_driver"].outline
    view._canvas.camera.center[:] = (o.x_mm + o.width_mm / 2, -o.y_mm - o.height_mm / 2, 0)
    view._canvas.camera.span = view._canvas.height() / 8
    view._canvas.update()
    QTest.qWait(100)
    view.grab().save(str(out / "3d-after.png"))
    view._camera_action("bottom")
    QTest.qWait(100)
    view._canvas.grabFramebuffer().save(str(out / "3d-bottom.png"))
    view.close()
    window = MainWindow()
    window.show()
    window._on_circuit_generated(specs["motor_driver"])
    window._tab_widget.setCurrentIndex(2)
    QTest.qWait(700)
    if window._view_3d._using_fallback or window._view_3d._canvas._error:
        raise RuntimeError("Workspace OpenGL failed during capture")
    window.grab().save(str(out / "workspace-dark.png"))
    ThemeManager.instance().set_dark(False)
    app.setStyleSheet(LIGHT_THEME)
    Translator.instance().set_language("tr")
    QTest.qWait(200)
    window.grab().save(str(out / "workspace-light-tr.png"))
    for dock in window._docks.values():
        dock.hide()
    window.resize(960, 640)
    QTest.qWait(200)
    window.grab().save(str(out / "workspace-compact.png"))
    window.close()
    print("Captured", out)


if __name__ == "__main__":
    capture()
