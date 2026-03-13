"""3D PCB component viewer — high-quality isometric rendering.

Aims for Altium Designer / KiCad 3D viewer aesthetics using QPainter
with advanced shading, gradient materials, and realistic proportions.
"""

from __future__ import annotations

import math
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QFrame, QCheckBox, QPushButton,
)
from PySide6.QtCore import Qt, QPoint, QTimer
from PySide6.QtGui import (
    QPainter, QColor, QFont, QMouseEvent, QWheelEvent,
    QPen, QBrush, QLinearGradient, QRadialGradient,
    QPolygonF, QTransform, QPainterPath, QPixmap,
)
from PySide6.QtCore import QPointF, QRectF

from src.pcb.generator import Board
from src.gui.i18n import tr, Translator
from src.models.model_registry import ModelRegistry
from src.config import get_settings

# ── High-quality color palette (Altium-style) ──
_BOARD_TOP = QColor("#1B6B3F")
_BOARD_SIDE = QColor("#0E4226")
_BOARD_BOTTOM = QColor("#13502D")
_COPPER_F = QColor("#D4883A")
_COPPER_B = QColor("#8b5e3c")
_SOLDER_MASK = QColor(18, 90, 45, 170)
_SOLDER_MASK_DARK = QColor(12, 65, 30, 200)
_SILKSCREEN = QColor("#F0F0F0")
_PAD_GOLD = QColor("#E8C854")
_PAD_TH = QColor("#D4D4D4")
_PAD_ANNULAR = QColor("#C8A032")
_VIA_COLOR = QColor("#C8C832")
_DRILL_COLOR = QColor("#181818")
_TEXT_COLOR = QColor("#e0e0e0")
_DIM_TEXT = QColor("#6a7a8a")
_BG_TOP = QColor("#0C1218")
_BG_MID = QColor("#101820")
_BG_BOTTOM = QColor("#0A1014")
_GRID_COLOR = QColor("#1a2530")
_SHADOW = QColor(0, 0, 0, 120)
_SHADOW_SOFT = QColor(0, 0, 0, 50)

# Realistic component colors
_IC_BODY = QColor("#181818")
_IC_TOP = QColor("#282828")
_IC_TEXT = QColor("#B8B8B8")
_IC_MARKING = QColor("#909090")
_HEATSINK_BODY = QColor("#909090")
_HEATSINK_FIN = QColor("#A0A0A0")
_HEATSINK_DARK = QColor("#707070")
_RESISTOR_BODY = QColor("#D0C0A0")
_RESISTOR_BAND_COLORS = [QColor("#CC3333"), QColor("#E06020"), QColor("#CCCC00"),
                          QColor("#33AA33"), QColor("#3366CC"), QColor("#8833CC"),
                          QColor("#333333"), QColor("#CC9933")]
_CAP_ELECTRO_BODY = QColor("#181828")
_CAP_ELECTRO_TOP = QColor("#C8C8C8")
_CAP_ELECTRO_STRIPE = QColor("#D0D0D0")
_CAP_CERAMIC_BODY = QColor("#D0A050")
_CONNECTOR_BODY = QColor("#1858B0")
_CONNECTOR_CLAMP = QColor("#989898")
_CONNECTOR_SCREW = QColor("#D0D0D0")
_LED_COLORS = {
    "red": QColor(220, 30, 30), "green": QColor(30, 180, 30),
    "blue": QColor(30, 80, 220), "yellow": QColor(220, 200, 30),
    "white": QColor(240, 240, 240), "orange": QColor(220, 120, 20),
}
_TRANSISTOR_BODY = QColor("#181818")
_CRYSTAL_BODY = QColor("#D8D8D8")
_INDUCTOR_BODY = QColor("#4A3020")
_INDUCTOR_WIRE = QColor("#D48030")
_DIODE_BODY = QColor("#202020")
_DIODE_BAND = QColor("#D0D0D0")
_LEAD_COLOR = QColor("#C8C8C8")
_SOLDER_COLOR = QColor("#B0A080")


# Cached trig values for projection — avoids recalculating per-vertex
_cached_angles: tuple[float, float] = (0.0, 0.0)
_cached_trig: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)


def _update_projection_cache(angle_x: float, angle_z: float):
    """Pre-compute sin/cos for the current view angles."""
    global _cached_angles, _cached_trig
    if (angle_x, angle_z) != _cached_angles:
        rx = math.radians(angle_x)
        rz = math.radians(angle_z)
        _cached_angles = (angle_x, angle_z)
        _cached_trig = (math.cos(rz), math.sin(rz), math.sin(rx), math.cos(rx))


def _iso_project(x: float, y: float, z: float,
                 angle_x: float = 30, angle_z: float = 45) -> QPointF:
    """Simple isometric-like projection using cached trig."""
    if (angle_x, angle_z) != _cached_angles:
        _update_projection_cache(angle_x, angle_z)
    cz, sz, sx, cx = _cached_trig
    px = x * cz - y * sz
    py = (x * sz + y * cz) * sx - z * cx
    return QPointF(px, py)


def _classify_component(ref: str, value: str) -> str:
    """Classify component into a rendering category from ref designator / value."""
    r = ref.upper()
    v = value.lower() if value else ""
    if r.startswith("RL") or r.startswith("K") or "relay" in v:
        return "relay"
    if r.startswith("RV") or "potentiometer" in v or "trimpot" in v or "pot" in v:
        return "potentiometer"
    if r.startswith("R"):
        return "resistor"
    if r.startswith("C"):
        # Electrolytic if value has uF >= 1 or mentions electrolytic / polarized
        if any(k in v for k in ("electro", "polar", "elko")):
            return "cap_electrolytic"
        try:
            num_part = "".join(c for c in v if c.isdigit() or c == ".")
            if "uf" in v or "µf" in v:
                if num_part and float(num_part) >= 1.0:
                    return "cap_electrolytic"
        except ValueError:
            pass
        return "cap_ceramic"
    if r.startswith("L"):
        return "inductor"
    if r.startswith("D"):
        if "led" in v or "led" in r.lower():
            return "led"
        return "diode"
    if r.startswith("LED"):
        return "led"
    if r.startswith("Q"):
        if any(k in v for k in ("mosfet", "irf", "irl", "irfz", "irlz", "nmos", "pmos", "fet")):
            return "mosfet"
        return "transistor"
    if r.startswith("U"):
        return "ic"
    if r.startswith("J") or r.startswith("P") or r.startswith("CN"):
        return "connector"
    if r.startswith("Y") or r.startswith("X"):
        return "crystal"
    if r.startswith("SW") or "button" in v or "tact" in v:
        return "switch"
    if r.startswith("F"):
        return "fuse"
    if r.startswith("BZ") or r.startswith("LS") or "buzzer" in v or "speaker" in v:
        return "buzzer"
    return "generic"


class View3D(QWidget):
    """Pseudo-3D isometric PCB viewer with component bodies."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._board: Optional[Board] = None
        self._rot_z = 45.0
        self._rot_x = 30.0
        self._zoom = 3.0
        self._pan = QPointF(0, 0)
        self._last_mouse: Optional[QPoint] = None
        self._show_silkscreen = True
        self._show_components = True
        self._show_traces = True
        self._show_wires = True
        self._show_3d_models = True
        self._model_registry = ModelRegistry(get_settings().kicad_3dmodels_path)

        self._setup_ui()
        self._retranslate()
        Translator.instance().language_changed.connect(self._retranslate)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Control bar ──
        ctrl_frame = QFrame()
        ctrl_frame.setObjectName("view3d_controls")
        ctrl_frame.setStyleSheet("""
            #view3d_controls {
                background: #111820;
                border-bottom: 1px solid #1e2a3a;
            }
        """)
        ctrl_layout = QHBoxLayout(ctrl_frame)
        ctrl_layout.setContentsMargins(8, 4, 8, 4)
        ctrl_layout.setSpacing(10)

        self._lbl_title = QLabel()
        self._lbl_title.setStyleSheet("color: #8b949e; font-weight: bold; font-size: 11px;")
        ctrl_layout.addWidget(self._lbl_title)

        self._cb_components = QCheckBox()
        self._cb_components.setChecked(True)
        self._cb_components.setStyleSheet("color: #e0e0e0; font-size: 11px;")
        self._cb_components.toggled.connect(self._on_toggle_components)
        ctrl_layout.addWidget(self._cb_components)

        self._cb_traces = QCheckBox()
        self._cb_traces.setChecked(True)
        self._cb_traces.setStyleSheet("color: #c87533; font-size: 11px;")
        self._cb_traces.toggled.connect(self._on_toggle_traces)
        ctrl_layout.addWidget(self._cb_traces)

        self._cb_wires = QCheckBox()
        self._cb_wires.setChecked(True)
        self._cb_wires.setStyleSheet("color: #40a0e0; font-size: 11px;")
        self._cb_wires.toggled.connect(self._on_toggle_wires)
        ctrl_layout.addWidget(self._cb_wires)

        self._cb_silk = QCheckBox()
        self._cb_silk.setChecked(True)
        self._cb_silk.setStyleSheet("color: #e8e8e8; font-size: 11px;")
        self._cb_silk.toggled.connect(self._on_toggle_silk)
        ctrl_layout.addWidget(self._cb_silk)

        self._cb_3d_models = QCheckBox()
        self._cb_3d_models.setChecked(True)
        self._cb_3d_models.setStyleSheet("color: #b0b0b0; font-size: 11px;")
        self._cb_3d_models.toggled.connect(self._on_toggle_3d_models)
        ctrl_layout.addWidget(self._cb_3d_models)

        ctrl_layout.addStretch()

        self._btn_reset = QPushButton()
        self._btn_reset.setFixedSize(70, 24)
        self._btn_reset.setStyleSheet("""
            QPushButton {
                background: #21262d; color: #c9d1d9;
                border: 1px solid #30363d; border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover { background: #30363d; }
        """)
        self._btn_reset.clicked.connect(self._reset_view)
        ctrl_layout.addWidget(self._btn_reset)

        layout.addWidget(ctrl_frame)

        # ── 3D canvas ──
        self._canvas = _Canvas3D(self)
        layout.addWidget(self._canvas, 1)

    def load_board(self, board: Board):
        self._board = board
        self._canvas.set_board(board)
        self._canvas._model_registry = self._model_registry
        self._canvas._show_3d_models = self._show_3d_models
        self._canvas._show_wires = self._show_wires
        self._canvas._dirty = True
        self._canvas.update()

    def _on_toggle_components(self, checked):
        self._show_components = checked
        self._canvas._show_components = checked
        self._canvas._dirty = True
        self._canvas.update()

    def _on_toggle_traces(self, checked):
        self._show_traces = checked
        self._canvas._show_traces = checked
        self._canvas._dirty = True
        self._canvas.update()

    def _on_toggle_silk(self, checked):
        self._show_silkscreen = checked
        self._canvas._show_silkscreen = checked
        self._canvas._dirty = True
        self._canvas.update()

    def _on_toggle_wires(self, checked):
        self._show_wires = checked
        self._canvas._show_wires = checked
        self._canvas._dirty = True
        self._canvas.update()

    def _on_toggle_3d_models(self, checked):
        self._show_3d_models = checked
        self._canvas._show_3d_models = checked
        self._canvas._dirty = True
        self._canvas.update()

    def _reset_view(self):
        self._canvas._rot_z = 45.0
        self._canvas._rot_x = 30.0
        self._canvas._zoom = 3.0
        self._canvas._pan = QPointF(0, 0)
        self._canvas._dirty = True
        self._canvas.update()

    def _retranslate(self):
        self._lbl_title.setText(tr("view3d_title"))
        self._cb_components.setText(tr("view3d_components"))
        self._cb_traces.setText(tr("view3d_traces"))
        self._cb_silk.setText(tr("view3d_silkscreen"))
        self._btn_reset.setText(tr("view3d_reset"))
        self._cb_wires.setText(tr("view3d_wires"))
        self._cb_3d_models.setText(tr("view3d_3d_models"))


class _Canvas3D(QWidget):
    """Custom paint widget for realistic isometric 3D PCB rendering."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._board: Optional[Board] = None
        self._rot_z = 45.0
        self._rot_x = 30.0
        self._zoom = 3.0
        self._pan = QPointF(0, 0)
        self._last_mouse: Optional[QPoint] = None
        self._show_components = True
        self._show_traces = True
        self._show_wires = True
        self._show_silkscreen = True
        self._show_3d_models = True
        self._model_registry: ModelRegistry | None = None
        self._dirty = True
        self._cached_pixmap: QPixmap | None = None
        self._throttle_timer: QTimer | None = None

        self.setMinimumSize(400, 300)
        self.setMouseTracking(True)

    def set_board(self, board: Board):
        self._board = board
        self._dirty = True

    def _project(self, x: float, y: float, z: float) -> QPointF:
        p = _iso_project(x, y, z, self._rot_x, self._rot_z)
        cx = self.width() / 2 + self._pan.x()
        cy = self.height() / 2 + self._pan.y()
        return QPointF(cx + p.x() * self._zoom, cy + p.y() * self._zoom)

    def _draw_quad(self, painter: QPainter, pts: list[QPointF], color: QColor,
                   border: QColor | None = None):
        poly = QPolygonF(pts)
        painter.setPen(QPen(border, 0.5) if border else Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawPolygon(poly)

    def _draw_quad_gradient(self, painter: QPainter, pts: list[QPointF],
                            color_top: QColor, color_bot: QColor,
                            border: QColor | None = None):
        """Draw quad with gradient for realistic material look."""
        if len(pts) < 3:
            return
        poly = QPolygonF(pts)
        min_y = min(p.y() for p in pts)
        max_y = max(p.y() for p in pts)
        min_x = min(p.x() for p in pts)
        max_x = max(p.x() for p in pts)
        grad = QLinearGradient(min_x, min_y, max_x, max_y)
        grad.setColorAt(0, color_top)
        grad.setColorAt(1, color_bot)
        painter.setPen(QPen(border, 0.5) if border else Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawPolygon(poly)

    def _draw_box_gradient(self, painter: QPainter, p3, x, y, z, w, d, h,
                           body_color: QColor, top_color: QColor | None = None,
                           border: QColor | None = None):
        """Draw 3D box with gradient shading on each face."""
        if top_color is None:
            top_color = body_color.lighter(115)
        light = body_color.lighter(125)
        mid = body_color
        dark = body_color.darker(130)
        darkest = body_color.darker(160)
        # Front
        f = [p3(x, y + d, z), p3(x + w, y + d, z),
             p3(x + w, y + d, z + h), p3(x, y + d, z + h)]
        self._draw_quad_gradient(painter, f, mid, light, border)
        # Right
        r = [p3(x + w, y, z), p3(x + w, y + d, z),
             p3(x + w, y + d, z + h), p3(x + w, y, z + h)]
        self._draw_quad_gradient(painter, r, light, mid, border)
        # Left
        lf = [p3(x, y, z), p3(x, y + d, z),
              p3(x, y + d, z + h), p3(x, y, z + h)]
        self._draw_quad_gradient(painter, lf, dark, darkest, border)
        # Back
        bk = [p3(x, y, z), p3(x + w, y, z),
              p3(x + w, y, z + h), p3(x, y, z + h)]
        self._draw_quad_gradient(painter, bk, darkest, dark, border)
        # Top
        t = [p3(x, y, z + h), p3(x + w, y, z + h),
             p3(x + w, y + d, z + h), p3(x, y + d, z + h)]
        self._draw_quad_gradient(painter, t, top_color, top_color.darker(110), border)

    # ── Cylinder helper ──
    def _draw_cylinder(self, painter: QPainter, p3, cx, cy, z_base, z_top,
                       radius: float, body_color: QColor, top_color: QColor,
                       segments: int = 12, stripe_angle: int = -1,
                       stripe_color: QColor | None = None):
        """Draw a 3D cylinder (for capacitors, LEDs, etc)."""
        h = z_top - z_base
        # Draw side faces as quads around circumference
        points_bottom = []
        points_top = []
        for i in range(segments + 1):
            angle = 2 * math.pi * i / segments
            dx = radius * math.cos(angle)
            dy = radius * math.sin(angle)
            points_bottom.append((cx + dx, cy + dy, z_base))
            points_top.append((cx + dx, cy + dy, z_top))

        # Draw side quads (back to front for occlusion)
        for i in range(segments):
            b0 = points_bottom[i]
            b1 = points_bottom[i + 1]
            t0 = points_top[i]
            t1 = points_top[i + 1]

            # Shading based on face normal direction
            angle = 2 * math.pi * (i + 0.5) / segments
            shade = int(100 + 55 * math.cos(angle - math.radians(self._rot_z)))
            shade = max(60, min(180, shade))
            c = QColor(body_color.red() * shade // 128,
                       body_color.green() * shade // 128,
                       body_color.blue() * shade // 128)

            # Stripe on electrolytic cap
            if stripe_color and stripe_angle >= 0:
                if abs(i - stripe_angle) <= 1 or abs(i - stripe_angle - segments) <= 1:
                    c = stripe_color

            face = [p3(*b0), p3(*b1), p3(*t1), p3(*t0)]
            self._draw_quad(painter, face, c)

        # Top ellipse
        top_pts = [p3(*p) for p in points_top[:-1]]
        self._draw_quad(painter, top_pts, top_color)

    # ── Box helper ──
    def _draw_box(self, painter: QPainter, p3, x, y, z, w, d, h,
                  body_color: QColor, top_color: QColor | None = None,
                  border: QColor | None = None):
        """Draw a 3D box (for ICs, connectors, etc)."""
        if top_color is None:
            top_color = body_color.lighter(115)

        # Front
        f = [p3(x, y + d, z), p3(x + w, y + d, z),
             p3(x + w, y + d, z + h), p3(x, y + d, z + h)]
        self._draw_quad(painter, f, body_color.lighter(105), border)
        # Right
        r = [p3(x + w, y, z), p3(x + w, y + d, z),
             p3(x + w, y + d, z + h), p3(x + w, y, z + h)]
        self._draw_quad(painter, r, body_color.lighter(115), border)
        # Left
        lf = [p3(x, y, z), p3(x, y + d, z),
              p3(x, y + d, z + h), p3(x, y, z + h)]
        self._draw_quad(painter, lf, body_color.darker(108), border)
        # Back
        bk = [p3(x, y, z), p3(x + w, y, z),
              p3(x + w, y, z + h), p3(x, y, z + h)]
        self._draw_quad(painter, bk, body_color.darker(115), border)
        # Top
        t = [p3(x, y, z + h), p3(x + w, y, z + h),
             p3(x + w, y + d, z + h), p3(x, y + d, z + h)]
        self._draw_quad(painter, t, top_color, border)

    # ── Realistic component drawing methods ──

    def _draw_resistor(self, painter, p3, cx, cy, cw, ch, pads):
        """Axial resistor: cylindrical tan body with color bands + bent wire leads."""
        z_base = 0.6
        body_r = max(min(cw, ch) * 0.18, 0.6)
        body_len = max(cw * 0.50, 2.0)
        center_x = cx + cw / 2
        center_y = cy + ch / 2
        bx_start = center_x - body_len / 2

        # Wire leads (L-shaped bent from pad to body) — at actual pad positions
        sorted_pads = sorted(pads, key=lambda p: p.x_mm)
        lp, rp = sorted_pads[0], sorted_pads[-1]
        lead_pen = QPen(_LEAD_COLOR, max(1.0, self._zoom * 0.35))
        lead_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(lead_pen)
        painter.drawLine(p3(lp.x_mm, lp.y_mm, 0), p3(lp.x_mm, lp.y_mm, z_base))
        painter.drawLine(p3(lp.x_mm, lp.y_mm, z_base), p3(bx_start, center_y, z_base))
        painter.drawLine(p3(rp.x_mm, rp.y_mm, 0), p3(rp.x_mm, rp.y_mm, z_base))
        painter.drawLine(p3(rp.x_mm, rp.y_mm, z_base),
                         p3(bx_start + body_len, center_y, z_base))

        # Cylindrical body (horizontal, multi-segment)
        segments = 10
        for i in range(segments):
            angle0 = 2 * math.pi * i / segments
            angle1 = 2 * math.pi * (i + 1) / segments
            dy0, dz0 = body_r * math.cos(angle0), body_r * math.sin(angle0)
            dy1, dz1 = body_r * math.cos(angle1), body_r * math.sin(angle1)
            shade = int(110 + 50 * math.cos(angle0 - math.radians(self._rot_z)))
            shade = max(60, min(200, shade))
            c = QColor(_RESISTOR_BODY.red() * shade // 128,
                       _RESISTOR_BODY.green() * shade // 128,
                       _RESISTOR_BODY.blue() * shade // 128)
            face = [p3(bx_start, center_y + dy0, z_base + dz0),
                    p3(bx_start + body_len, center_y + dy0, z_base + dz0),
                    p3(bx_start + body_len, center_y + dy1, z_base + dz1),
                    p3(bx_start, center_y + dy1, z_base + dz1)]
            self._draw_quad(painter, face, c)

        # End caps
        cap_l, cap_r = [], []
        for i in range(segments):
            a = 2 * math.pi * i / segments
            dy, dz = body_r * math.cos(a), body_r * math.sin(a)
            cap_l.append(p3(bx_start, center_y + dy, z_base + dz))
            cap_r.append(p3(bx_start + body_len, center_y + dy, z_base + dz))
        self._draw_quad(painter, cap_l, _RESISTOR_BODY.darker(115))
        self._draw_quad(painter, cap_r, _RESISTOR_BODY.lighter(105))

        # Color bands wrapping around cylinder
        num_bands = 4
        band_spacing = body_len / (num_bands + 2)
        for bi in range(num_bands):
            band_color = _RESISTOR_BAND_COLORS[bi % len(_RESISTOR_BAND_COLORS)]
            bx_pos = bx_start + band_spacing * (bi + 1)
            bw_b = band_spacing * 0.35
            for i in range(segments):
                a0 = 2 * math.pi * i / segments
                a1 = 2 * math.pi * (i + 1) / segments
                dy0 = body_r * 1.01 * math.cos(a0)
                dz0 = body_r * 1.01 * math.sin(a0)
                dy1 = body_r * 1.01 * math.cos(a1)
                dz1 = body_r * 1.01 * math.sin(a1)
                shade = int(100 + 40 * math.cos(a0 - math.radians(self._rot_z)))
                shade = max(60, min(180, shade))
                bc = QColor(band_color.red() * shade // 128,
                            band_color.green() * shade // 128,
                            band_color.blue() * shade // 128)
                bf = [p3(bx_pos, center_y + dy0, z_base + dz0),
                      p3(bx_pos + bw_b, center_y + dy0, z_base + dz0),
                      p3(bx_pos + bw_b, center_y + dy1, z_base + dz1),
                      p3(bx_pos, center_y + dy1, z_base + dz1)]
                self._draw_quad(painter, bf, bc)

    def _draw_cap_electrolytic(self, painter, p3, cx, cy, cw, ch, pads):
        """Electrolytic capacitor: tall vertical cylinder with silver top + polarity stripe."""
        radius = max(min(cw, ch) * 0.4, 1.2)
        cap_h = max(radius * 3.0, 4.0)
        center_x = cx + cw / 2
        center_y = cy + ch / 2
        z_base = 0.15

        # Wire leads at actual pad positions
        lead_pen = QPen(_LEAD_COLOR, max(0.8, self._zoom * 0.25))
        lead_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(lead_pen)
        for pad in pads:
            painter.drawLine(p3(pad.x_mm, pad.y_mm, 0),
                             p3(pad.x_mm, pad.y_mm, z_base))

        # Cylinder body
        stripe_seg = 2  # which segment gets the white stripe
        self._draw_cylinder(painter, p3, center_x, center_y, z_base,
                           z_base + cap_h, radius, _CAP_ELECTRO_BODY,
                           _CAP_ELECTRO_TOP, segments=14,
                           stripe_angle=stripe_seg, stripe_color=_CAP_ELECTRO_STRIPE)

        # Top vent cross (K-shaped scores on aluminum cap)
        vr = radius * 0.5
        top_z = z_base + cap_h + 0.02
        painter.setPen(QPen(QColor(100, 100, 100), max(0.5, self._zoom * 0.15)))
        painter.drawLine(p3(center_x - vr, center_y, top_z),
                         p3(center_x + vr, center_y, top_z))
        painter.drawLine(p3(center_x, center_y - vr, top_z),
                         p3(center_x, center_y + vr, top_z))

    def _draw_cap_ceramic(self, painter, p3, cx, cy, cw, ch):
        """Ceramic/MLCC capacitor with rounded body and metallic end caps."""
        z_base = 0.15
        body_w = max(cw * 0.5, 1.5)
        body_d = max(ch * 0.5, 1.0)
        body_h = 0.7
        bx = cx + (cw - body_w) / 2
        by = cy + (ch - body_d) / 2

        self._draw_box_gradient(painter, p3, bx, by, z_base, body_w, body_d, body_h,
                                _CAP_CERAMIC_BODY, _CAP_CERAMIC_BODY.lighter(115))

        # Metallic end caps with solder color
        cap_w = body_w * 0.18
        self._draw_box_gradient(painter, p3, bx, by, z_base, cap_w, body_d, body_h,
                                _SOLDER_COLOR, _SOLDER_COLOR.lighter(120))
        self._draw_box_gradient(painter, p3, bx + body_w - cap_w, by, z_base,
                                cap_w, body_d, body_h,
                                _SOLDER_COLOR, _SOLDER_COLOR.lighter(120))

    def _draw_ic(self, painter, p3, cx, cy, cw, ch, ref: str, value: str, n_pins: int = 0, pads=None):
        """IC package: DIP/SOIC with detailed leads, text, pin-1 notch."""
        z_base = 0.15
        body_h = max(1.4, min(cw, ch) * 0.12)
        margin = 0.4
        bx, by_s = cx + margin, cy + margin
        bw, bd = cw - 2 * margin, ch - 2 * margin

        # IC body with gradient
        self._draw_box_gradient(painter, p3, bx, by_s, z_base, bw, bd, body_h,
                                _IC_BODY, _IC_TOP, QColor(35, 35, 35))

        # Pin 1 notch (semicircle indent on top face)
        notch_p = p3(bx + bw * 0.10, by_s + bd * 0.12, z_base + body_h + 0.02)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(100, 100, 100, 140)))
        nr = max(1.5, min(bw, bd) * 0.06 * self._zoom * 0.3)
        painter.drawEllipse(notch_p, nr, nr)

        # IC text: value (bold) + ref below
        tp = p3(cx + cw / 2, cy + ch / 2, z_base + body_h + 0.03)
        font_sz = max(5, int(self._zoom * 1.5))
        painter.setFont(QFont("Consolas", font_sz, QFont.Weight.Bold))
        painter.setPen(_IC_TEXT)
        text = value[:12] if value else ref
        half_w = max(40, self._zoom * 12)
        half_h = max(10, font_sz * 1.5)
        rect = QRectF(tp.x() - half_w, tp.y() - half_h / 2, half_w * 2, half_h)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
        if value and ref:
            painter.setFont(QFont("Consolas", max(4, font_sz - 2)))
            painter.setPen(_IC_MARKING)
            rect2 = QRectF(tp.x() - half_w, tp.y() + half_h * 0.2, half_w * 2, half_h)
            painter.drawText(rect2, Qt.AlignmentFlag.AlignCenter, ref)

        # DIP/SOIC legs on left/right sides — at actual pad positions
        leg_w = 0.35
        leg_ext = 0.6
        leg_h = 0.1
        if pads:
            center_body_x = bx + bw / 2
            left_pads = sorted([p for p in pads if p.x_mm < center_body_x], key=lambda p: p.y_mm)
            right_pads = sorted([p for p in pads if p.x_mm >= center_body_x], key=lambda p: p.y_mm)
            for pad in left_pads:
                ly = pad.y_mm - leg_w / 2
                leg_l = [p3(pad.x_mm, ly, z_base),
                         p3(pad.x_mm, ly + leg_w, z_base),
                         p3(bx, ly + leg_w, z_base + leg_h),
                         p3(bx, ly, z_base + leg_h)]
                self._draw_quad(painter, leg_l, _LEAD_COLOR.lighter(110))
            for pad in right_pads:
                ly = pad.y_mm - leg_w / 2
                leg_r = [p3(bx + bw, ly, z_base + leg_h),
                         p3(bx + bw, ly + leg_w, z_base + leg_h),
                         p3(pad.x_mm, ly + leg_w, z_base),
                         p3(pad.x_mm, ly, z_base)]
                self._draw_quad(painter, leg_r, _LEAD_COLOR)
        else:
            half_pins = max(n_pins // 2, max(2, int(max(cw, ch) / 1.5)))
            leg_spacing = bd / max(half_pins, 1)
            for i in range(half_pins):
                ly = by_s + i * leg_spacing + leg_spacing * 0.3
                leg_l = [p3(bx - leg_ext, ly, z_base),
                         p3(bx - leg_ext, ly + leg_w, z_base),
                         p3(bx, ly + leg_w, z_base + leg_h),
                         p3(bx, ly, z_base + leg_h)]
                self._draw_quad(painter, leg_l, _LEAD_COLOR.lighter(110))
                leg_r = [p3(bx + bw, ly, z_base + leg_h),
                         p3(bx + bw, ly + leg_w, z_base + leg_h),
                         p3(bx + bw + leg_ext, ly + leg_w, z_base),
                         p3(bx + bw + leg_ext, ly, z_base)]
                self._draw_quad(painter, leg_r, _LEAD_COLOR)

        # Heatsink tab on large ICs (regulators, motor drivers)
        v_low = (value or "").lower()
        if any(k in v_low for k in ("7805", "7812", "7815", "7905", "lm", "l298", "l293",
                                     "reg", "ams1117", "78", "79", "voltage")):
            hs_w = bw * 0.85
            hs_d = bd * 0.12
            hs_h = body_h + 2.0
            hx = bx + (bw - hs_w) / 2
            hy = by_s - hs_d * 0.5

            self._draw_box_gradient(painter, p3, hx, hy, z_base, hs_w, hs_d, hs_h,
                                    _HEATSINK_BODY, _HEATSINK_FIN, QColor(65, 65, 65))

            # Fin ridges
            n_fins = max(4, int(hs_w / 0.6))
            fin_spacing = hs_w / n_fins
            for fi in range(n_fins):
                fx = hx + fi * fin_spacing
                c = _HEATSINK_FIN if fi % 2 == 0 else _HEATSINK_DARK
                fin_top = [p3(fx, hy, z_base + hs_h),
                           p3(fx + fin_spacing * 0.45, hy, z_base + hs_h),
                           p3(fx + fin_spacing * 0.45, hy + hs_d, z_base + hs_h),
                           p3(fx, hy + hs_d, z_base + hs_h)]
                self._draw_quad(painter, fin_top, c)

            # Mounting hole
            hole_p = p3(hx + hs_w / 2, hy + hs_d / 2, z_base + hs_h + 0.02)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(50, 50, 50)))
            hr = max(1.5, self._zoom * 0.4)
            painter.drawEllipse(hole_p, hr, hr)
            painter.setBrush(QBrush(_HEATSINK_DARK))
            painter.drawEllipse(hole_p, hr * 0.5, hr * 0.5)

    def _draw_connector(self, painter, p3, cx, cy, cw, ch, n_pins: int, pads=None):
        """Pin header / terminal block connector with detailed housing."""
        z_base = 0.15
        body_h = max(4.0, ch * 0.6)
        pin_w = max(cw / max(n_pins, 1), 2.5)

        # Main body with gradient
        self._draw_box_gradient(painter, p3, cx, cy, z_base, cw, ch, body_h,
                                _CONNECTOR_BODY, _CONNECTOR_BODY.lighter(120),
                                QColor(20, 50, 130))

        # Individual pin housings — positioned at actual pad locations
        sorted_pads = sorted(pads, key=lambda p: p.x_mm) if pads else []
        pin_positions = [(pad.x_mm, pad.y_mm) for pad in sorted_pads] if sorted_pads else [
            (cx + i * pin_w + pin_w / 2, cy + ch / 2) for i in range(n_pins)
        ]
        for pin_x, pin_y in pin_positions:
            px = pin_x - pin_w / 2

            # Front opening (wire entry)
            slot_w = pin_w * 0.60
            slot_h = body_h * 0.38
            slot_x = px + (pin_w - slot_w) / 2
            slot = [p3(slot_x, cy + ch, z_base + body_h * 0.15),
                    p3(slot_x + slot_w, cy + ch, z_base + body_h * 0.15),
                    p3(slot_x + slot_w, cy + ch, z_base + body_h * 0.15 + slot_h),
                    p3(slot_x, cy + ch, z_base + body_h * 0.15 + slot_h)]
            self._draw_quad(painter, slot, QColor(10, 25, 55))

            # Metal clamp
            clamp_h = slot_h * 0.35
            clamp = [p3(slot_x + slot_w * 0.1, cy + ch - 0.05, z_base + body_h * 0.25),
                     p3(slot_x + slot_w * 0.9, cy + ch - 0.05, z_base + body_h * 0.25),
                     p3(slot_x + slot_w * 0.9, cy + ch - 0.05, z_base + body_h * 0.25 + clamp_h),
                     p3(slot_x + slot_w * 0.1, cy + ch - 0.05, z_base + body_h * 0.25 + clamp_h)]
            self._draw_quad(painter, clamp, _CONNECTOR_CLAMP)

            # Screw head with metallic radial gradient
            screw_cy_pos = cy + ch / 2
            screw_r = min(pin_w * 0.20, 0.85)
            screw_p = p3(pin_x, screw_cy_pos, z_base + body_h + 0.05)
            sr = max(screw_r * self._zoom * 0.35, 2.0)
            grad = QRadialGradient(screw_p, sr)
            grad.setColorAt(0, QColor(220, 220, 220))
            grad.setColorAt(0.7, QColor(180, 180, 180))
            grad.setColorAt(1, QColor(140, 140, 140))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(grad))
            painter.drawEllipse(screw_p, sr, sr)

            # Phillips cross
            sl = screw_r * 0.55
            painter.setPen(QPen(QColor(60, 60, 60), max(0.7, self._zoom * 0.14)))
            painter.drawLine(
                p3(pin_x - sl, screw_cy_pos, z_base + body_h + 0.06),
                p3(pin_x + sl, screw_cy_pos, z_base + body_h + 0.06))
            painter.drawLine(
                p3(pin_x, screw_cy_pos - sl, z_base + body_h + 0.06),
                p3(pin_x, screw_cy_pos + sl, z_base + body_h + 0.06))

            # Through-hole pin at actual pad position
            painter.setPen(QPen(_LEAD_COLOR, max(0.8, self._zoom * 0.25)))
            painter.drawLine(p3(pin_x, pin_y, 0),
                             p3(pin_x, pin_y, z_base))

    def _draw_led(self, painter, p3, cx, cy, cw, ch, value: str, pads=None):
        """LED: taller cylindrical body with dome top + flat edge (cathode marker)."""
        radius = max(min(cw, ch) * 0.35, 1.0)
        led_h = 2.5
        center_x = cx + cw / 2
        center_y = cy + ch / 2
        z_base = 0.15

        # Determine color from value
        v_low = (value or "").lower()
        led_color = _LED_COLORS.get("red")  # default
        for color_name, color_val in _LED_COLORS.items():
            if color_name in v_low:
                led_color = color_val
                break

        # Semi-transparent lens body
        lens_color = QColor(led_color.red(), led_color.green(), led_color.blue(), 160)
        lens_top = QColor(led_color.red(), led_color.green(), led_color.blue(), 200)

        # Wire leads at actual pad positions
        lead_pen = QPen(_LEAD_COLOR, max(0.6, self._zoom * 0.22))
        lead_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(lead_pen)
        if pads:
            for pad in pads:
                painter.drawLine(p3(pad.x_mm, pad.y_mm, 0),
                                 p3(pad.x_mm, pad.y_mm, z_base))
        else:
            painter.drawLine(p3(center_x - radius * 0.3, center_y, 0),
                             p3(center_x - radius * 0.3, center_y, z_base))
            painter.drawLine(p3(center_x + radius * 0.3, center_y, 0),
                             p3(center_x + radius * 0.3, center_y, z_base))

        # Cylinder body
        self._draw_cylinder(painter, p3, center_x, center_y, z_base,
                           z_base + led_h, radius, lens_color, lens_top, segments=12)

        # Cathode flat edge indicator (small dark flat on one side)
        flat_pts = [p3(center_x + radius * 0.85, center_y - radius * 0.3, z_base),
                    p3(center_x + radius * 0.85, center_y + radius * 0.3, z_base),
                    p3(center_x + radius * 0.85, center_y + radius * 0.3, z_base + led_h),
                    p3(center_x + radius * 0.85, center_y - radius * 0.3, z_base + led_h)]
        self._draw_quad(painter, flat_pts, QColor(led_color.red() // 2,
                        led_color.green() // 2, led_color.blue() // 2, 180))

        # Glow effect (larger, brighter)
        glow_p = p3(center_x, center_y, z_base + led_h + 0.5)
        glow_r = radius * self._zoom * 1.0
        glow_c = QColor(led_color.red(), led_color.green(), led_color.blue(), 120)
        grad = QRadialGradient(glow_p, glow_r)
        grad.setColorAt(0, glow_c)
        grad.setColorAt(1, QColor(0, 0, 0, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawEllipse(glow_p, glow_r, glow_r)

    def _draw_diode(self, painter, p3, cx, cy, cw, ch, pads):
        """Diode: cylindrical black body with silver cathode band."""
        z_base = 0.5
        body_r = max(min(cw, ch) * 0.15, 0.5)
        body_len = max(cw * 0.45, 1.5)
        center_x = cx + cw / 2
        center_y = cy + ch / 2
        bx_start = center_x - body_len / 2

        # Wire leads (bent L-shape) — at actual pad positions
        sorted_pads = sorted(pads, key=lambda p: p.x_mm)
        lp, rp = sorted_pads[0], sorted_pads[-1]
        lead_pen = QPen(_LEAD_COLOR, max(0.8, self._zoom * 0.28))
        lead_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(lead_pen)
        painter.drawLine(p3(lp.x_mm, lp.y_mm, 0), p3(lp.x_mm, lp.y_mm, z_base))
        painter.drawLine(p3(lp.x_mm, lp.y_mm, z_base), p3(bx_start, center_y, z_base))
        painter.drawLine(p3(rp.x_mm, rp.y_mm, 0), p3(rp.x_mm, rp.y_mm, z_base))
        painter.drawLine(p3(rp.x_mm, rp.y_mm, z_base),
                         p3(bx_start + body_len, center_y, z_base))

        # Cylindrical body (horizontal)
        segments = 8
        for i in range(segments):
            a0 = 2 * math.pi * i / segments
            a1 = 2 * math.pi * (i + 1) / segments
            dy0, dz0 = body_r * math.cos(a0), body_r * math.sin(a0)
            dy1, dz1 = body_r * math.cos(a1), body_r * math.sin(a1)
            shade = int(100 + 40 * math.cos(a0 - math.radians(self._rot_z)))
            shade = max(50, min(170, shade))
            c = QColor(_DIODE_BODY.red() * shade // 100,
                       _DIODE_BODY.green() * shade // 100,
                       _DIODE_BODY.blue() * shade // 100)
            face = [p3(bx_start, center_y + dy0, z_base + dz0),
                    p3(bx_start + body_len, center_y + dy0, z_base + dz0),
                    p3(bx_start + body_len, center_y + dy1, z_base + dz1),
                    p3(bx_start, center_y + dy1, z_base + dz1)]
            self._draw_quad(painter, face, c)

        # Cathode band (silver ring near one end)
        band_x = bx_start + body_len * 0.78
        band_w_b = body_len * 0.10
        for i in range(segments):
            a0 = 2 * math.pi * i / segments
            a1 = 2 * math.pi * (i + 1) / segments
            dy0 = body_r * 1.02 * math.cos(a0)
            dz0 = body_r * 1.02 * math.sin(a0)
            dy1 = body_r * 1.02 * math.cos(a1)
            dz1 = body_r * 1.02 * math.sin(a1)
            shade = int(180 + 40 * math.cos(a0 - math.radians(self._rot_z)))
            shade = max(140, min(255, shade))
            bc = QColor(shade, shade, shade)
            bf = [p3(band_x, center_y + dy0, z_base + dz0),
                  p3(band_x + band_w_b, center_y + dy0, z_base + dz0),
                  p3(band_x + band_w_b, center_y + dy1, z_base + dz1),
                  p3(band_x, center_y + dy1, z_base + dz1)]
            self._draw_quad(painter, bf, bc)

    def _draw_transistor(self, painter, p3, cx, cy, cw, ch, pads):
        """TO-92 transistor: half-cylinder body with flat face + 3 legs."""
        z_base = 0.15
        body_h = 2.0
        radius = max(min(cw, ch) * 0.3, 0.8)
        center_x = cx + cw / 2
        center_y = cy + ch / 2

        # Draw as half-cylinder (flat front)
        self._draw_cylinder(painter, p3, center_x, center_y, z_base,
                           z_base + body_h, radius, _TRANSISTOR_BODY,
                           _TRANSISTOR_BODY.lighter(115), segments=8)

        # Flat face
        ff = [p3(center_x - radius, center_y, z_base),
              p3(center_x + radius, center_y, z_base),
              p3(center_x + radius, center_y, z_base + body_h),
              p3(center_x - radius, center_y, z_base + body_h)]
        self._draw_quad(painter, ff, _TRANSISTOR_BODY.lighter(108))

        # Wire legs at actual pad positions
        painter.setPen(QPen(_LEAD_COLOR, max(0.5, self._zoom * 0.2)))
        for pad in pads:
            painter.drawLine(p3(pad.x_mm, pad.y_mm, 0), p3(pad.x_mm, pad.y_mm, z_base))

    def _draw_inductor(self, painter, p3, cx, cy, cw, ch, pads):
        """Inductor: brown toroidal body with copper winding."""
        radius = max(min(cw, ch) * 0.3, 1.0)
        ind_h = 1.5
        center_x = cx + cw / 2
        center_y = cy + ch / 2
        z_base = 0.15

        # Brown body cylinder
        self._draw_cylinder(painter, p3, center_x, center_y, z_base,
                           z_base + ind_h, radius, _INDUCTOR_BODY,
                           _INDUCTOR_BODY.lighter(120), segments=10)

        # Copper winding lines on top
        n_winds = 6
        for i in range(n_winds):
            angle = 2 * math.pi * i / n_winds
            x1 = center_x + radius * 0.8 * math.cos(angle)
            y1 = center_y + radius * 0.8 * math.sin(angle)
            x2 = center_x + radius * 0.8 * math.cos(angle + 0.3)
            y2 = center_y + radius * 0.8 * math.sin(angle + 0.3)
            painter.setPen(QPen(_INDUCTOR_WIRE, max(0.6, self._zoom * 0.2)))
            painter.drawLine(p3(x1, y1, z_base + ind_h * 0.3),
                             p3(x2, y2, z_base + ind_h + 0.05))

        # Wire leads at actual pad positions
        sorted_pads = sorted(pads, key=lambda p: p.x_mm)
        lp, rp = sorted_pads[0], sorted_pads[-1]
        painter.setPen(QPen(_LEAD_COLOR, max(0.5, self._zoom * 0.2)))
        painter.drawLine(p3(lp.x_mm, lp.y_mm, 0), p3(lp.x_mm, lp.y_mm, z_base))
        painter.drawLine(p3(rp.x_mm, rp.y_mm, 0), p3(rp.x_mm, rp.y_mm, z_base))

    def _draw_crystal(self, painter, p3, cx, cy, cw, ch, pads):
        """Crystal oscillator: silver metal can."""
        z_base = 0.15
        body_h = 1.5
        margin = 0.3
        self._draw_box(painter, p3, cx + margin, cy + margin, z_base,
                       cw - 2 * margin, ch - 2 * margin, body_h,
                       _CRYSTAL_BODY, _CRYSTAL_BODY.lighter(110),
                       QColor(160, 160, 160))

        # Wire leads at actual pad positions
        sorted_pads = sorted(pads, key=lambda p: p.x_mm)
        lp, rp = sorted_pads[0], sorted_pads[-1]
        painter.setPen(QPen(_LEAD_COLOR, max(0.5, self._zoom * 0.2)))
        painter.drawLine(p3(lp.x_mm, lp.y_mm, 0), p3(lp.x_mm, lp.y_mm, z_base))
        painter.drawLine(p3(rp.x_mm, rp.y_mm, 0), p3(rp.x_mm, rp.y_mm, z_base))

    def _draw_mesh_component(self, painter: QPainter, p3,
                              comp_x: float, comp_y: float,
                              mesh: 'Mesh3D', rot_deg: float = 0.0,
                              scale: float = 1.0):
        """Render a KiCad VRML mesh centered on (comp_x, comp_y)."""
        rot_rad = math.radians(rot_deg)
        cos_r = math.cos(rot_rad)
        sin_r = math.sin(rot_rad)

        # Center mesh around its own bbox center
        mcx = (mesh.bbox_min[0] + mesh.bbox_max[0]) * 0.5
        mcy = (mesh.bbox_min[1] + mesh.bbox_max[1]) * 0.5

        projected_faces: list[tuple[float, list[QPointF], QColor]] = []

        for face in mesh.faces:
            pts_2d: list[QPointF] = []
            depth_sum = 0.0

            for vx, vy, vz in face.vertices:
                # Center then scale
                lx = (vx - mcx) * scale
                ly = (vy - mcy) * scale
                lz = vz * scale
                # Apply component rotation around Z
                rx = lx * cos_r - ly * sin_r
                ry = lx * sin_r + ly * cos_r
                pt = p3(comp_x + rx, comp_y + ry, lz)
                pts_2d.append(pt)
                depth_sum += pt.y()

            if len(pts_2d) < 3:
                continue

            # Back-face culling
            e1x = pts_2d[1].x() - pts_2d[0].x()
            e1y = pts_2d[1].y() - pts_2d[0].y()
            e2x = pts_2d[2].x() - pts_2d[0].x()
            e2y = pts_2d[2].y() - pts_2d[0].y()
            if e1x * e2y - e1y * e2x > 0:
                continue

            # Lighting from face normal
            v0, v1, v2 = face.vertices[0], face.vertices[1], face.vertices[2]
            ax = v1[0] - v0[0]; ay = v1[1] - v0[1]; az = v1[2] - v0[2]
            bx = v2[0] - v0[0]; by = v2[1] - v0[1]; bz = v2[2] - v0[2]
            nx = ay * bz - az * by
            ny = az * bx - ax * bz
            nz = ax * by - ay * bx
            nl = math.sqrt(nx*nx + ny*ny + nz*nz)
            if nl > 1e-9:
                nx /= nl; ny /= nl; nz /= nl
            light = 0.3 + 0.7 * max(0.0, nx * 0.3 + ny * -0.4 + nz * 0.866)

            r = min(255, int(face.color[0] * 255 * light))
            g = min(255, int(face.color[1] * 255 * light))
            b = min(255, int(face.color[2] * 255 * light))

            projected_faces.append((depth_sum / len(pts_2d), pts_2d, QColor(r, g, b)))

        projected_faces.sort(key=lambda f: -f[0])

        painter.setPen(Qt.PenStyle.NoPen)
        for _, pts, color in projected_faces:
            painter.setBrush(QBrush(color))
            painter.drawPolygon(QPolygonF(pts))

    def _draw_switch(self, painter, p3, cx, cy, cw, ch, pads):
        """Tactile switch: square body with round button on top."""
        z_base = 0.15
        body_h = 1.8
        body_s = max(min(cw, ch) * 0.8, 3.0)
        center_x = cx + cw / 2
        center_y = cy + ch / 2
        bx = center_x - body_s / 2
        by = center_y - body_s / 2

        # Square body
        self._draw_box_gradient(painter, p3, bx, by, z_base, body_s, body_s, body_h,
                                QColor("#1a1a1a"), QColor("#2a2a2a"), QColor(30, 30, 30))

        # Round button on top
        btn_r = body_s * 0.28
        btn_h = 0.6
        self._draw_cylinder(painter, p3, center_x, center_y,
                           z_base + body_h, z_base + body_h + btn_h,
                           btn_r, QColor("#d0d0d0"), QColor("#e8e8e8"), segments=10)

        # Legs at actual pad positions
        painter.setPen(QPen(_LEAD_COLOR, max(0.6, self._zoom * 0.22)))
        for pad in pads:
            painter.drawLine(p3(pad.x_mm, pad.y_mm, 0), p3(pad.x_mm, pad.y_mm, z_base))

    def _draw_potentiometer(self, painter, p3, cx, cy, cw, ch, pads):
        """Potentiometer: cylindrical body with shaft/knob on top, 3 pins."""
        z_base = 0.15
        radius = max(min(cw, ch) * 0.35, 2.0)
        body_h = 2.5
        center_x = cx + cw / 2
        center_y = cy + ch / 2

        # Cylindrical body (blue)
        self._draw_cylinder(painter, p3, center_x, center_y, z_base,
                           z_base + body_h, radius,
                           QColor("#1858B0"), QColor("#2868C0"), segments=14)

        # Metal shaft
        shaft_r = radius * 0.15
        shaft_h = 2.0
        self._draw_cylinder(painter, p3, center_x, center_y,
                           z_base + body_h, z_base + body_h + shaft_h,
                           shaft_r, QColor("#c0c0c0"), QColor("#d8d8d8"), segments=8)

        # Indicator slot on shaft top
        top_z = z_base + body_h + shaft_h + 0.02
        sl = shaft_r * 0.7
        painter.setPen(QPen(QColor(60, 60, 60), max(0.6, self._zoom * 0.12)))
        painter.drawLine(p3(center_x - sl, center_y, top_z),
                         p3(center_x + sl, center_y, top_z))

        # Legs at actual pad positions
        painter.setPen(QPen(_LEAD_COLOR, max(0.6, self._zoom * 0.22)))
        for pad in pads:
            painter.drawLine(p3(pad.x_mm, pad.y_mm, 0), p3(pad.x_mm, pad.y_mm, z_base))

    def _draw_fuse(self, painter, p3, cx, cy, cw, ch, pads):
        """Fuse: glass tube body with silver end caps."""
        z_base = 0.4
        body_r = max(min(cw, ch) * 0.12, 0.4)
        body_len = max(cw * 0.50, 2.0)
        center_x = cx + cw / 2
        center_y = cy + ch / 2
        bx_start = center_x - body_len / 2

        # Leads at actual pad positions
        sorted_pads = sorted(pads, key=lambda p: p.x_mm)
        lp, rp = sorted_pads[0], sorted_pads[-1]
        lead_pen = QPen(_LEAD_COLOR, max(0.8, self._zoom * 0.28))
        lead_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(lead_pen)
        painter.drawLine(p3(lp.x_mm, lp.y_mm, 0), p3(lp.x_mm, lp.y_mm, z_base))
        painter.drawLine(p3(lp.x_mm, lp.y_mm, z_base), p3(bx_start, center_y, z_base))
        painter.drawLine(p3(rp.x_mm, rp.y_mm, 0), p3(rp.x_mm, rp.y_mm, z_base))
        painter.drawLine(p3(rp.x_mm, rp.y_mm, z_base),
                         p3(bx_start + body_len, center_y, z_base))

        # Glass tube body (semi-transparent)
        segments = 8
        for i in range(segments):
            a0 = 2 * math.pi * i / segments
            a1 = 2 * math.pi * (i + 1) / segments
            dy0, dz0 = body_r * math.cos(a0), body_r * math.sin(a0)
            dy1, dz1 = body_r * math.cos(a1), body_r * math.sin(a1)
            shade = int(160 + 50 * math.cos(a0 - math.radians(self._rot_z)))
            shade = max(120, min(220, shade))
            c = QColor(shade, shade, shade + 20, 140)
            face = [p3(bx_start, center_y + dy0, z_base + dz0),
                    p3(bx_start + body_len, center_y + dy0, z_base + dz0),
                    p3(bx_start + body_len, center_y + dy1, z_base + dz1),
                    p3(bx_start, center_y + dy1, z_base + dz1)]
            self._draw_quad(painter, face, c)

        # Silver end caps
        cap_w = body_len * 0.12
        for sx in (bx_start, bx_start + body_len - cap_w):
            for i in range(segments):
                a0 = 2 * math.pi * i / segments
                a1 = 2 * math.pi * (i + 1) / segments
                dy0, dz0 = body_r * 1.05 * math.cos(a0), body_r * 1.05 * math.sin(a0)
                dy1, dz1 = body_r * 1.05 * math.cos(a1), body_r * 1.05 * math.sin(a1)
                fc = [p3(sx, center_y + dy0, z_base + dz0),
                      p3(sx + cap_w, center_y + dy0, z_base + dz0),
                      p3(sx + cap_w, center_y + dy1, z_base + dz1),
                      p3(sx, center_y + dy1, z_base + dz1)]
                self._draw_quad(painter, fc, QColor(200, 200, 200))

        # Thin wire inside
        painter.setPen(QPen(QColor(180, 180, 180), max(0.3, self._zoom * 0.08)))
        painter.drawLine(p3(bx_start + cap_w, center_y, z_base),
                         p3(bx_start + body_len - cap_w, center_y, z_base))

    def _draw_buzzer(self, painter, p3, cx, cy, cw, ch, pads):
        """Buzzer: cylindrical body with sound hole on top."""
        z_base = 0.15
        radius = max(min(cw, ch) * 0.35, 1.5)
        body_h = 3.0
        center_x = cx + cw / 2
        center_y = cy + ch / 2

        # Black cylindrical body
        self._draw_cylinder(painter, p3, center_x, center_y, z_base,
                           z_base + body_h, radius,
                           QColor("#181818"), QColor("#282828"), segments=14)

        # Sound hole on top
        hole_p = p3(center_x, center_y, z_base + body_h + 0.02)
        hr = max(radius * 0.4 * self._zoom * 0.3, 2.0)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(50, 50, 50)))
        painter.drawEllipse(hole_p, hr, hr)

        # Polarity marker (+)
        sl = radius * 0.15
        painter.setPen(QPen(QColor(200, 200, 200), max(0.5, self._zoom * 0.12)))
        painter.drawLine(p3(center_x + radius * 0.5 - sl, center_y, z_base + body_h + 0.03),
                         p3(center_x + radius * 0.5 + sl, center_y, z_base + body_h + 0.03))
        painter.drawLine(p3(center_x + radius * 0.5, center_y - sl, z_base + body_h + 0.03),
                         p3(center_x + radius * 0.5, center_y + sl, z_base + body_h + 0.03))

        # Legs at actual pad positions
        painter.setPen(QPen(_LEAD_COLOR, max(0.5, self._zoom * 0.2)))
        for pad in pads:
            painter.drawLine(p3(pad.x_mm, pad.y_mm, 0), p3(pad.x_mm, pad.y_mm, z_base))

    def _draw_relay(self, painter, p3, cx, cy, cw, ch, pads):
        """Relay: tall rectangular box with blue housing."""
        z_base = 0.15
        body_h = max(5.0, min(cw, ch) * 0.6)
        margin = 0.3

        # Main body (blue housing)
        self._draw_box_gradient(painter, p3, cx + margin, cy + margin, z_base,
                                cw - 2 * margin, ch - 2 * margin, body_h,
                                QColor("#1848A0"), QColor("#2060C0"),
                                QColor(15, 40, 100))

        # Label area on top
        lx = cx + margin + (cw - 2 * margin) * 0.1
        ly = cy + margin + (ch - 2 * margin) * 0.1
        lw = (cw - 2 * margin) * 0.8
        ld = (ch - 2 * margin) * 0.8
        top_z = z_base + body_h + 0.01
        label_pts = [p3(lx, ly, top_z), p3(lx + lw, ly, top_z),
                     p3(lx + lw, ly + ld, top_z), p3(lx, ly + ld, top_z)]
        self._draw_quad(painter, label_pts, QColor(220, 220, 220, 80))

        # Legs at actual pad positions
        painter.setPen(QPen(_LEAD_COLOR, max(0.6, self._zoom * 0.22)))
        for pad in pads:
            painter.drawLine(p3(pad.x_mm, pad.y_mm, 0), p3(pad.x_mm, pad.y_mm, z_base))

    def _draw_mosfet(self, painter, p3, cx, cy, cw, ch, pads):
        """MOSFET in TO-220: body with heatsink tab + legs."""
        z_base = 0.15
        body_h = max(2.0, min(cw, ch) * 0.15)
        margin = 0.4
        bx, by_s = cx + margin, cy + margin
        bw, bd = cw - 2 * margin, ch - 2 * margin

        # IC body
        self._draw_box_gradient(painter, p3, bx, by_s, z_base, bw, bd, body_h,
                                _IC_BODY, _IC_TOP, QColor(35, 35, 35))

        # Heatsink tab
        hs_w = bw * 0.85
        hs_d = bd * 0.12
        hs_h = body_h + 2.0
        hx = bx + (bw - hs_w) / 2
        hy = by_s - hs_d * 0.5
        self._draw_box_gradient(painter, p3, hx, hy, z_base, hs_w, hs_d, hs_h,
                                _HEATSINK_BODY, _HEATSINK_FIN, QColor(65, 65, 65))

        # Fin ridges
        n_fins = max(4, int(hs_w / 0.6))
        fin_spacing = hs_w / n_fins
        for fi in range(n_fins):
            fx = hx + fi * fin_spacing
            c = _HEATSINK_FIN if fi % 2 == 0 else _HEATSINK_DARK
            fin_top = [p3(fx, hy, z_base + hs_h),
                       p3(fx + fin_spacing * 0.45, hy, z_base + hs_h),
                       p3(fx + fin_spacing * 0.45, hy + hs_d, z_base + hs_h),
                       p3(fx, hy + hs_d, z_base + hs_h)]
            self._draw_quad(painter, fin_top, c)

        # Mounting hole
        hole_p = p3(hx + hs_w / 2, hy + hs_d / 2, z_base + hs_h + 0.02)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(50, 50, 50)))
        hr = max(1.5, self._zoom * 0.4)
        painter.drawEllipse(hole_p, hr, hr)
        painter.setBrush(QBrush(_HEATSINK_DARK))
        painter.drawEllipse(hole_p, hr * 0.5, hr * 0.5)

        # Value text on body
        tp = p3(cx + cw / 2, cy + ch / 2, z_base + body_h + 0.03)
        font_sz = max(5, int(self._zoom * 1.3))
        painter.setFont(QFont("Consolas", font_sz, QFont.Weight.Bold))
        painter.setPen(_IC_TEXT)
        half_w = max(30, self._zoom * 10)
        half_h = max(8, font_sz * 1.2)
        rect = QRectF(tp.x() - half_w, tp.y() - half_h / 2, half_w * 2, half_h)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "MOSFET")

        # Legs at actual pad positions
        painter.setPen(QPen(_LEAD_COLOR, max(0.6, self._zoom * 0.22)))
        for pad in pads:
            painter.drawLine(p3(pad.x_mm, pad.y_mm, 0), p3(pad.x_mm, pad.y_mm, z_base))

    def _draw_generic(self, painter, p3, cx, cy, cw, ch):
        """Generic component: dark box with gradient."""
        z_base = 0.15
        body_h = max(0.8, min(cw, ch) * 0.1)
        self._draw_box_gradient(painter, p3, cx, cy, z_base, cw, ch, body_h,
                                QColor("#1a1a1a"), QColor("#2a2a2a"), QColor(30, 30, 30))

    def paintEvent(self, event):
        if not self._board:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            grad = QLinearGradient(0, 0, 0, self.height())
            grad.setColorAt(0, _BG_TOP)
            grad.setColorAt(1, _BG_BOTTOM)
            painter.fillRect(self.rect(), grad)
            painter.setPen(_DIM_TEXT)
            painter.setFont(QFont("Segoe UI", 14))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, tr("view3d_no_board"))
            painter.end()
            return

        # ── QPixmap cache: only re-render when dirty ──
        w, h = self.width(), self.height()
        if (not self._dirty and self._cached_pixmap is not None
                and self._cached_pixmap.width() == w
                and self._cached_pixmap.height() == h):
            painter = QPainter(self)
            painter.drawPixmap(0, 0, self._cached_pixmap)
            painter.end()
            return

        # Pre-compute projection trig for this frame
        _update_projection_cache(self._rot_x, self._rot_z)

        pm = QPixmap(w, h)
        pm.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # ── Background gradient (3-stop for depth) ──
        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0, _BG_TOP)
        grad.setColorAt(0.5, _BG_MID)
        grad.setColorAt(1, _BG_BOTTOM)
        painter.fillRect(self.rect(), grad)

        board = self._board
        o = board.outline
        bx, by = o.x_mm, o.y_mm
        bw, bh = o.width_mm, o.height_mm
        board_thickness = 1.6

        cx_off = -(bx + bw / 2)
        cy_off = -(by + bh / 2)

        def p3(x, y, z):
            return self._project(x + cx_off, y + cy_off, z)

        # ── Board shadow ──
        shadow_z = -board_thickness - 2
        s_pts = [p3(bx + 3, by + 3, shadow_z), p3(bx + bw + 3, by + 3, shadow_z),
                 p3(bx + bw + 3, by + bh + 3, shadow_z), p3(bx + 3, by + bh + 3, shadow_z)]
        self._draw_quad(painter, s_pts, _SHADOW)

        # ── Board bottom ──
        z_bot = -board_thickness
        bot_pts = [p3(bx, by, z_bot), p3(bx + bw, by, z_bot),
                   p3(bx + bw, by + bh, z_bot), p3(bx, by + bh, z_bot)]
        self._draw_quad(painter, bot_pts, _BOARD_BOTTOM, QColor("#0a2a15"))

        # ── Board sides ──
        front = [p3(bx, by + bh, z_bot), p3(bx + bw, by + bh, z_bot),
                 p3(bx + bw, by + bh, 0), p3(bx, by + bh, 0)]
        self._draw_quad(painter, front, _BOARD_SIDE, QColor("#0a2a15"))

        right = [p3(bx + bw, by, z_bot), p3(bx + bw, by + bh, z_bot),
                 p3(bx + bw, by + bh, 0), p3(bx + bw, by, 0)]
        self._draw_quad(painter, right, _BOARD_SIDE.lighter(110), QColor("#0a2a15"))

        left = [p3(bx, by, z_bot), p3(bx, by + bh, z_bot),
                p3(bx, by + bh, 0), p3(bx, by, 0)]
        self._draw_quad(painter, left, _BOARD_SIDE.darker(110), QColor("#0a2a15"))

        back = [p3(bx, by, z_bot), p3(bx + bw, by, z_bot),
                p3(bx + bw, by, 0), p3(bx, by, 0)]
        self._draw_quad(painter, back, _BOARD_SIDE.darker(120), QColor("#0a2a15"))

        # ── Board top (solder mask with texture gradient) ──
        top_pts = [p3(bx, by, 0), p3(bx + bw, by, 0),
                   p3(bx + bw, by + bh, 0), p3(bx, by + bh, 0)]
        self._draw_quad_gradient(painter, top_pts,
                                 _BOARD_TOP, _BOARD_TOP.darker(108),
                                 QColor("#1a6a3a"))
        self._draw_quad(painter, top_pts, _SOLDER_MASK)

        # Solder mask openings around pads (exposed copper annular rings)
        for comp in board.components:
            for pad in comp.pads:
                pp = p3(pad.x_mm, pad.y_mm, 0.06)
                pr = max(pad.width_mm * self._zoom * 0.45, 2.2)
                mask_grad = QRadialGradient(pp, pr)
                mask_grad.setColorAt(0, _PAD_ANNULAR)
                mask_grad.setColorAt(0.65, _PAD_ANNULAR.darker(120))
                mask_grad.setColorAt(1, Qt.GlobalColor.transparent)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(mask_grad))
                painter.drawEllipse(pp, pr, pr)

        # ── Traces (copper with specular highlight) ──
        if self._show_traces:
            for trace in board.traces:
                if trace.layer != "F.Cu":
                    continue
                sp = p3(trace.start_x, trace.start_y, 0.05)
                ep = p3(trace.end_x, trace.end_y, 0.05)
                tw = max(trace.width_mm * self._zoom * 0.7, 1.5)

                # Main copper trace
                pen = QPen(_COPPER_F, tw)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                painter.drawLine(sp, ep)

                # Specular highlight
                hi_pen = QPen(QColor(min(255, _COPPER_F.red() + 30),
                                     min(255, _COPPER_F.green() + 20),
                                     _COPPER_F.blue(), 60),
                              max(tw * 0.3, 0.5))
                hi_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(hi_pen)
                painter.drawLine(sp, ep)

                # Solder endpoint dots with gradient
                painter.setPen(Qt.PenStyle.NoPen)
                jr = tw * 0.45
                for pt in (sp, ep):
                    g = QRadialGradient(pt, jr)
                    g.setColorAt(0, _COPPER_F.lighter(130))
                    g.setColorAt(1, _COPPER_F)
                    painter.setBrush(QBrush(g))
                    painter.drawEllipse(pt, jr, jr)

        # ── Pads (HASL/gold metallic finish) ──
        for comp in board.components:
            for pad in comp.pads:
                pp = p3(pad.x_mm, pad.y_mm, 0.1)
                pw = max(pad.width_mm * self._zoom * 0.8, 2.5)
                ph = max(pad.height_mm * self._zoom * 0.8, 2.5)
                is_th = pad.drill_mm > 0
                base_color = _PAD_TH if is_th else _PAD_GOLD

                # Metallic radial gradient
                pad_grad = QRadialGradient(pp, max(pw, ph) / 2)
                pad_grad.setColorAt(0, base_color.lighter(130))
                pad_grad.setColorAt(0.5, base_color)
                pad_grad.setColorAt(1, base_color.darker(120))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(pad_grad))
                if pad.shape == "circle" or is_th:
                    painter.drawEllipse(pp, pw / 2, ph / 2)
                else:
                    painter.drawRoundedRect(
                        QRectF(pp.x() - pw/2, pp.y() - ph/2, pw, ph),
                        pw * 0.2, ph * 0.2)

                # Drill hole with bevel
                if is_th:
                    dr = max(pad.drill_mm * self._zoom * 0.4, 1.2)
                    painter.setBrush(QBrush(QColor(40, 40, 40)))
                    painter.drawEllipse(pp, dr + 0.5, dr + 0.5)
                    painter.setBrush(QBrush(_DRILL_COLOR))
                    painter.drawEllipse(pp, dr, dr)

        # ── Vias ──
        for via in board.vias:
            vp = p3(via.x_mm, via.y_mm, 0.1)
            vr = max(via.diameter_mm * self._zoom * 0.4, 1.5)
            dr = max(via.drill_mm * self._zoom * 0.3, 0.8)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(_VIA_COLOR))
            painter.drawEllipse(vp, vr, vr)
            painter.setBrush(QBrush(_DRILL_COLOR))
            painter.drawEllipse(vp, dr, dr)

        # ── 3D Component bodies ──
        if self._show_components:
            sorted_comps = sorted(board.components,
                                  key=lambda c: -self._project(
                                      c.x_mm + cx_off, c.y_mm + cy_off, 0).y())

            for comp in sorted_comps:
                if not comp.pads:
                    continue

                # Component bounding box from pads
                min_x = min(p.x_mm for p in comp.pads)
                max_x = max(p.x_mm for p in comp.pads)
                min_y = min(p.y_mm for p in comp.pads)
                max_y = max(p.y_mm for p in comp.pads)
                pad_w = max(p.width_mm for p in comp.pads)
                margin = pad_w * 0.5
                cx1 = min_x - margin
                cy1 = min_y - margin
                cw = max((max_x - min_x) + 2 * margin, 3.0)
                ch = max((max_y - min_y) + 2 * margin, 2.0)

                category = _classify_component(comp.ref, comp.value)
                n_pins = len(comp.pads)

                # Try KiCad 3D model first
                _used_mesh = False
                if (self._show_3d_models and self._model_registry
                        and self._model_registry.available):
                    _mesh = self._model_registry.get_mesh(
                        category, getattr(comp, 'footprint', '') or '')
                    if _mesh:
                        # Use pad bbox center for alignment
                        pad_cx = (min_x + max_x) * 0.5
                        pad_cy = (min_y + max_y) * 0.5
                        self._draw_mesh_component(
                            painter, p3,
                            pad_cx, pad_cy, _mesh,
                            getattr(comp, 'rotation_deg', 0.0))
                        _used_mesh = True

                if not _used_mesh and category == "resistor":
                    self._draw_resistor(painter, p3, cx1, cy1, cw, ch, comp.pads)
                elif not _used_mesh and category == "cap_electrolytic":
                    self._draw_cap_electrolytic(painter, p3, cx1, cy1, cw, ch, comp.pads)
                elif not _used_mesh and category == "cap_ceramic":
                    self._draw_cap_ceramic(painter, p3, cx1, cy1, cw, ch)
                elif not _used_mesh and category == "ic":
                    self._draw_ic(painter, p3, cx1, cy1, cw, ch, comp.ref, comp.value, n_pins, comp.pads)
                elif not _used_mesh and category == "connector":
                    self._draw_connector(painter, p3, cx1, cy1, cw, ch, n_pins, comp.pads)
                elif not _used_mesh and category == "led":
                    self._draw_led(painter, p3, cx1, cy1, cw, ch, comp.value, comp.pads)
                elif not _used_mesh and category == "diode":
                    self._draw_diode(painter, p3, cx1, cy1, cw, ch, comp.pads)
                elif not _used_mesh and category == "transistor":
                    self._draw_transistor(painter, p3, cx1, cy1, cw, ch, comp.pads)
                elif not _used_mesh and category == "inductor":
                    self._draw_inductor(painter, p3, cx1, cy1, cw, ch, comp.pads)
                elif not _used_mesh and category == "crystal":
                    self._draw_crystal(painter, p3, cx1, cy1, cw, ch, comp.pads)
                elif not _used_mesh and category == "switch":
                    self._draw_switch(painter, p3, cx1, cy1, cw, ch, comp.pads)
                elif not _used_mesh and category == "potentiometer":
                    self._draw_potentiometer(painter, p3, cx1, cy1, cw, ch, comp.pads)
                elif not _used_mesh and category == "fuse":
                    self._draw_fuse(painter, p3, cx1, cy1, cw, ch, comp.pads)
                elif not _used_mesh and category == "buzzer":
                    self._draw_buzzer(painter, p3, cx1, cy1, cw, ch, comp.pads)
                elif not _used_mesh and category == "relay":
                    self._draw_relay(painter, p3, cx1, cy1, cw, ch, comp.pads)
                elif not _used_mesh and category == "mosfet":
                    self._draw_mosfet(painter, p3, cx1, cy1, cw, ch, comp.pads)
                elif not _used_mesh:
                    self._draw_generic(painter, p3, cx1, cy1, cw, ch)

                # Silkscreen ref label
                if self._show_silkscreen:
                    tp = p3(cx1 + cw / 2, cy1 - 1.5, 0.2)
                    painter.setPen(_SILKSCREEN)
                    silk_sz = max(5, int(self._zoom * 1.8))
                    font = QFont("Consolas", silk_sz)
                    painter.setFont(font)
                    silk_hw = max(30, self._zoom * 10)
                    silk_hh = max(10, silk_sz * 1.2)
                    rect = QRectF(tp.x() - silk_hw, tp.y() - silk_hh / 2, silk_hw * 2, silk_hh)
                    painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, comp.ref)

        # ── 3D Jumper wires (Tinkercad style with catenary curves) ──
        if self._show_wires:
            # Standard breadboard wire colors: power=red, ground=black, signals=colors
            _WIRE_RED = QColor("#e04040")
            _WIRE_BLACK = QColor("#2a2a2a")
            _WIRE_COLORS = [
                QColor("#40a0e0"), QColor("#40c040"),
                QColor("#e0a020"), QColor("#c060c0"), QColor("#e07020"),
                QColor("#60c0c0"), QColor("#f06090"), QColor("#80b040"),
            ]
            _PWR_NAMES = {"VCC", "VDD", "5V", "3V3", "3.3V", "12V", "+5V",
                          "+3.3V", "+12V", "VIN", "V+", "VOUT"}
            _GND_NAMES = {"GND", "VSS", "V-", "0V", "AGND", "DGND", "GROUND"}

            net_names = board.get_net_names()
            color_idx = 0
            for net_name in net_names:
                pads = board.get_pads_for_net(net_name)
                if len(pads) < 2:
                    continue

                n_upper = net_name.upper()
                if n_upper in _GND_NAMES:
                    wc = _WIRE_BLACK
                elif n_upper in _PWR_NAMES:
                    wc = _WIRE_RED
                else:
                    wc = _WIRE_COLORS[color_idx % len(_WIRE_COLORS)]
                    color_idx += 1

                wire_pen = QPen(wc, max(1.8, self._zoom * 0.6))
                wire_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                wire_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

                # Chain pads together with smooth catenary-like arched wires
                for pi in range(len(pads) - 1):
                    p_a = pads[pi]
                    p_b = pads[pi + 1]
                    dist = math.sqrt((p_b.x_mm - p_a.x_mm)**2 + (p_b.y_mm - p_a.y_mm)**2)
                    wire_height = min(2.5 + dist * 0.2, 9.0)

                    # Smooth curve with ~12 control points (catenary approximation)
                    n_seg = 14
                    prev_pt = None
                    painter.setPen(wire_pen)
                    for si in range(n_seg + 1):
                        t = si / n_seg
                        # Interpolate x, y linearly
                        wx = p_a.x_mm + (p_b.x_mm - p_a.x_mm) * t
                        wy = p_a.y_mm + (p_b.y_mm - p_a.y_mm) * t
                        # Z: parabolic arch (catenary approximation)
                        wz = 0.15 + wire_height * 4 * t * (1 - t)
                        pt = p3(wx, wy, wz)
                        if prev_pt is not None:
                            painter.drawLine(prev_pt, pt)
                        prev_pt = pt

                    # Insulated wire end caps (small colored circles at pads)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QBrush(wc.lighter(120)))
                    dr = max(1.2, self._zoom * 0.35)
                    start_pt = p3(p_a.x_mm, p_a.y_mm, 0.15)
                    end_pt = p3(p_b.x_mm, p_b.y_mm, 0.15)
                    painter.drawEllipse(start_pt, dr, dr)
                    painter.drawEllipse(end_pt, dr, dr)

        # ── Info overlay with semi-transparent background ──
        info = f"{bw:.1f} x {bh:.1f} mm  |  {len(board.components)} comp  |  {len(board.traces)} traces"
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0, 100)))
        painter.drawRoundedRect(QRectF(6, self.height() - 28, len(info) * 7 + 16, 22), 4, 4)
        painter.setPen(QColor("#8899AA"))
        painter.setFont(QFont("Consolas", 9))
        painter.drawText(14, self.height() - 12, info)

        painter.setPen(QColor("#3a4a5a"))
        painter.setFont(QFont("Segoe UI", 8))
        painter.drawText(12, 20, tr("view3d_hint"))

        painter.end()

        # Store in cache and blit to screen
        self._cached_pixmap = pm
        self._dirty = False
        screen_painter = QPainter(self)
        screen_painter.drawPixmap(0, 0, pm)
        screen_painter.end()

    # ── Mouse interaction ──
    def mousePressEvent(self, event: QMouseEvent):
        self._last_mouse = event.position().toPoint()

    def _schedule_repaint(self):
        """Throttle repaints to ~60fps max."""
        self._dirty = True
        if self._throttle_timer is None:
            self._throttle_timer = QTimer(self)
            self._throttle_timer.setSingleShot(True)
            self._throttle_timer.timeout.connect(self._do_throttled_update)
        if not self._throttle_timer.isActive():
            self._throttle_timer.start(16)  # ~60fps

    def _do_throttled_update(self):
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._last_mouse is None:
            return
        pos = event.position().toPoint()
        dx = pos.x() - self._last_mouse.x()
        dy = pos.y() - self._last_mouse.y()

        if event.buttons() & Qt.MouseButton.LeftButton:
            self._rot_z += dx * 0.5
            self._rot_x = max(5, min(85, self._rot_x + dy * 0.3))
        elif event.buttons() & Qt.MouseButton.RightButton:
            self._pan += QPointF(dx, dy)
        elif event.buttons() & Qt.MouseButton.MiddleButton:
            self._pan += QPointF(dx, dy)

        self._last_mouse = pos
        self._schedule_repaint()

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._last_mouse = None

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta().y()
        factor = 1.1 if delta > 0 else 1 / 1.1
        self._zoom = max(0.5, min(20.0, self._zoom * factor))
        self._schedule_repaint()
