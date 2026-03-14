"""PCB layout viewer — renders the generated board with KiCad-quality EDA styling."""

from __future__ import annotations

import math

from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsItem, QWidget,
    QVBoxLayout, QHBoxLayout, QCheckBox, QLabel, QFrame,
    QGraphicsDropShadowEffect,
)
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QWheelEvent,
    QLinearGradient, QRadialGradient, QPainterPath,
)

from src.pcb.generator import Board
from src.gui.i18n import tr, Translator

# ── KiCad-style layer colors ──
_LAYER_COLORS = {
    "F.Cu":      QColor("#ff3333"),   # bright red copper
    "B.Cu":      QColor("#4169e1"),   # blue copper
    "In1.Cu":    QColor("#c8c832"),
    "In2.Cu":    QColor("#32c832"),
    "Edge.Cuts": QColor("#e5e500"),   # bright yellow
    "F.SilkS":   QColor("#00e5ff"),   # cyan silkscreen
}

_LAYER_ALPHA = {
    "F.Cu": 240,
    "B.Cu": 210,
}

_BG_COLOR       = QColor("#0a0a0a")
_BOARD_FILL     = QColor("#0d0d0d")
_BOARD_EDGE     = QColor("#e5e500")
_VIA_RING       = QColor("#c8c832")
_VIA_DRILL      = QColor("#0a0a0a")
_PAD_THT        = QColor("#c040c0")   # magenta annular ring
_PAD_SMD_FCU    = QColor("#ff3333")
_PAD_SMD_BCU    = QColor("#4169e1")
_TEXT_COLOR      = QColor("#e0e0e0")
_TEXT_DIM        = QColor("#5a6a7a")
_SILK_COLOR      = QColor("#00e5ff")  # cyan
_GRID_COLOR      = QColor("#111111")
_GRID_MAJOR      = QColor("#1a1a1a")
_ORIGIN_COLOR    = QColor("#2a3a4a")


# ── Component classifier (shared with view3d) ──
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


class _PadItem(QGraphicsItem):
    """Interactive pad with KiCad-style annular ring rendering."""

    def __init__(self, x, y, w, h, shape, drill, color, ref, pad_num, net="", parent=None):
        super().__init__(parent)
        self._x, self._y = x, y
        self._w, self._h = w, h
        self._shape = shape
        self._drill = drill
        self._color = color
        self._ref = ref
        self._pad_num = pad_num
        self._hovered = False

        self.setAcceptHoverEvents(True)
        tip = f"{ref}.{pad_num}"
        if net:
            tip += f"\nNet: {net}"
        self.setToolTip(tip)

    def boundingRect(self) -> QRectF:
        m = 3
        return QRectF(-self._w / 2 - m, -self._h / 2 - m,
                       self._w + 2 * m, self._h + 2 * m)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self._color if not self._hovered else self._color.lighter(130)

        # Highlight outline on hover
        if self._hovered:
            hi_pen = QPen(QColor(255, 255, 255, 100), 1.5)
            if self._shape == "circle":
                painter.setPen(hi_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(QRectF(-self._w / 2 - 1.5, -self._h / 2 - 1.5,
                                            self._w + 3, self._h + 3))
            else:
                painter.setPen(hi_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(QRectF(-self._w / 2 - 1.5, -self._h / 2 - 1.5,
                                         self._w + 3, self._h + 3))

        # Draw pad copper
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))

        if self._shape == "circle":
            painter.drawEllipse(QRectF(-self._w / 2, -self._h / 2, self._w, self._h))
        elif self._shape == "roundrect":
            painter.drawRoundedRect(QRectF(-self._w / 2, -self._h / 2, self._w, self._h),
                                     self._w * 0.25, self._h * 0.25)
        else:
            painter.drawRect(QRectF(-self._w / 2, -self._h / 2, self._w, self._h))

        # Drill hole (dark center for THT)
        if self._drill > 0:
            painter.setBrush(QBrush(_VIA_DRILL))
            painter.drawEllipse(QPointF(0, 0), self._drill / 2, self._drill / 2)

        # Pad number on hover
        if self._hovered:
            font = QFont("Consolas", 5)
            painter.setFont(font)
            painter.setPen(QColor(255, 255, 255, 220))
            painter.drawText(self.boundingRect(), Qt.AlignmentFlag.AlignCenter, self._pad_num)

    def hoverEnterEvent(self, event):
        self._hovered = True
        self.update()

    def hoverLeaveEvent(self, event):
        self._hovered = False
        self.update()


class PCBView(QWidget):
    """Widget containing the PCB graphics view and layer controls."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._board: Board | None = None
        self._visible_layers: set[str] = {"F.Cu", "B.Cu", "Edge.Cuts", "F.SilkS"}
        self._setup_ui()
        self._retranslate()
        Translator.instance().language_changed.connect(self._retranslate)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Layer control bar ──
        layer_frame = QFrame()
        layer_frame.setObjectName("pcb_layer_bar")
        layer_frame.setStyleSheet("""
            #pcb_layer_bar {
                background: #111820;
                border-bottom: 1px solid #1e2a3a;
                padding: 4px 8px;
            }
        """)
        layer_bar = QHBoxLayout(layer_frame)
        layer_bar.setContentsMargins(8, 4, 8, 4)
        layer_bar.setSpacing(12)

        self._layers_label = QLabel()
        self._layers_label.setStyleSheet("color: #8b949e; font-weight: bold; font-size: 11px;")
        layer_bar.addWidget(self._layers_label)

        self._layer_checks: dict[str, QCheckBox] = {}
        for layer_name, color in _LAYER_COLORS.items():
            cb = QCheckBox(layer_name)
            cb.setChecked(layer_name in self._visible_layers)
            cb.setStyleSheet(f"""
                QCheckBox {{
                    color: {color.name()};
                    font-size: 11px;
                    spacing: 4px;
                }}
                QCheckBox::indicator {{
                    width: 12px; height: 12px;
                    border: 1px solid {color.name()};
                    border-radius: 2px;
                    background: transparent;
                }}
                QCheckBox::indicator:checked {{
                    background: {color.name()};
                }}
            """)
            cb.toggled.connect(lambda checked, ln=layer_name: self._toggle_layer(ln, checked))
            layer_bar.addWidget(cb)
            self._layer_checks[layer_name] = cb

        layer_bar.addStretch()
        layout.addWidget(layer_frame)

        # ── Graphics view ──
        self._view = _PCBGraphicsView()
        layout.addWidget(self._view, 1)

    def load_board(self, board: Board):
        self._board = board
        self._view.render_board(board, self._visible_layers)

    def _toggle_layer(self, layer: str, visible: bool):
        if visible:
            self._visible_layers.add(layer)
        else:
            self._visible_layers.discard(layer)
        if self._board:
            self._view.render_board(self._board, self._visible_layers)

    def _retranslate(self):
        self._layers_label.setText(tr("label_layers"))


class _PCBGraphicsView(QGraphicsView):
    """Internal graphics view for PCB rendering with KiCad-quality styling."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)

        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QBrush(_BG_COLOR))
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self._zoom = 1.0

    # ──────────────────────────────────────────────────────────────
    # Silkscreen component-shape drawing helpers
    # ──────────────────────────────────────────────────────────────

    def _silk_resistor(self, comp, scale):
        """Rectangular body between two end pads."""
        pads = comp.pads
        if len(pads) < 2:
            return
        pen = QPen(_SILK_COLOR, 1.4)
        p0x, p0y = pads[0].x_mm * scale, pads[0].y_mm * scale
        p1x, p1y = pads[1].x_mm * scale, pads[1].y_mm * scale
        cx, cy = (p0x + p1x) / 2, (p0y + p1y) / 2
        dx, dy = p1x - p0x, p1y - p0y
        length = math.hypot(dx, dy)
        bw = length * 0.55
        bh = max(pads[0].width_mm, pads[0].height_mm) * scale * 0.9
        angle = math.degrees(math.atan2(dy, dx))
        path = QPainterPath()
        path.addRect(QRectF(-bw / 2, -bh / 2, bw, bh))
        # Transform
        from PySide6.QtGui import QTransform
        t = QTransform()
        t.translate(cx, cy)
        t.rotate(angle)
        mapped = t.map(path)
        self._scene.addPath(mapped, pen)
        # Ref label centered inside body
        self._add_ref_label(comp, cx, cy - bh / 2 - 10, scale)

    def _silk_cap_ceramic(self, comp, scale):
        """Small rectangle between pads."""
        pads = comp.pads
        if len(pads) < 2:
            return
        pen = QPen(_SILK_COLOR, 1.4)
        p0x, p0y = pads[0].x_mm * scale, pads[0].y_mm * scale
        p1x, p1y = pads[1].x_mm * scale, pads[1].y_mm * scale
        cx, cy = (p0x + p1x) / 2, (p0y + p1y) / 2
        length = math.hypot(p1x - p0x, p1y - p0y)
        bw = length * 0.45
        bh = max(pads[0].width_mm, pads[0].height_mm) * scale * 0.85
        self._scene.addRect(QRectF(cx - bw / 2, cy - bh / 2, bw, bh), pen)
        self._add_ref_label(comp, cx, cy - bh / 2 - 10, scale)

    def _silk_cap_electrolytic(self, comp, scale):
        """Circle with + polarity marker."""
        pads = comp.pads
        if len(pads) < 2:
            return
        pen = QPen(_SILK_COLOR, 1.4)
        p0x, p0y = pads[0].x_mm * scale, pads[0].y_mm * scale
        p1x, p1y = pads[1].x_mm * scale, pads[1].y_mm * scale
        cx, cy = (p0x + p1x) / 2, (p0y + p1y) / 2
        r = math.hypot(p1x - p0x, p1y - p0y) * 0.42
        r = max(r, 8)
        self._scene.addEllipse(cx - r, cy - r, r * 2, r * 2, pen)
        # + marker near pin 1
        plus_pen = QPen(_SILK_COLOR, 1.6)
        pm = 3.5
        self._scene.addLine(p0x - pm, p0y, p0x + pm, p0y, plus_pen)
        self._scene.addLine(p0x, p0y - pm, p0x, p0y + pm, plus_pen)
        self._add_ref_label(comp, cx, cy - r - 10, scale)

    def _silk_ic(self, comp, scale):
        """Rectangle with pin-1 notch (half-circle indent)."""
        pads = comp.pads
        if not pads:
            return
        pen = QPen(_SILK_COLOR, 1.5)
        min_x = min(p.x_mm for p in pads) * scale
        max_x = max(p.x_mm for p in pads) * scale
        min_y = min(p.y_mm for p in pads) * scale
        max_y = max(p.y_mm for p in pads) * scale
        pw = max(p.width_mm for p in pads) * scale
        margin = pw * 0.5 + 4
        bx = min_x - margin
        by = min_y - margin
        bw = (max_x - min_x) + 2 * margin
        bh = (max_y - min_y) + 2 * margin
        # Body rectangle
        self._scene.addRect(QRectF(bx, by, bw, bh), pen)
        # Pin 1 notch (half circle on left edge)
        notch_r = min(bw, bh) * 0.08
        notch_r = max(notch_r, 3)
        path = QPainterPath()
        path.arcMoveTo(QRectF(bx - notch_r, by + bh / 2 - notch_r,
                               notch_r * 2, notch_r * 2), 90)
        path.arcTo(QRectF(bx - notch_r, by + bh / 2 - notch_r,
                           notch_r * 2, notch_r * 2), 90, -180)
        self._scene.addPath(path, pen)
        # Pin 1 dot
        p1 = pads[0]
        p1x, p1y = p1.x_mm * scale, p1.y_mm * scale
        dot_r = 2.0
        self._scene.addEllipse(p1x - dot_r, p1y - dot_r, dot_r * 2, dot_r * 2,
                                QPen(Qt.PenStyle.NoPen), QBrush(_SILK_COLOR))
        # Ref label
        cx = (min_x + max_x) / 2
        self._add_ref_label(comp, cx, by - 10, scale)

    def _silk_connector(self, comp, scale):
        """Rectangle with individual pin slot lines."""
        pads = comp.pads
        if not pads:
            return
        pen = QPen(_SILK_COLOR, 1.5)
        min_x = min(p.x_mm for p in pads) * scale
        max_x = max(p.x_mm for p in pads) * scale
        min_y = min(p.y_mm for p in pads) * scale
        max_y = max(p.y_mm for p in pads) * scale
        pw = max(p.width_mm for p in pads) * scale
        margin = pw * 0.6 + 4
        bx = min_x - margin
        by = min_y - margin
        bw = (max_x - min_x) + 2 * margin
        bh = (max_y - min_y) + 2 * margin
        self._scene.addRect(QRectF(bx, by, bw, bh), pen)
        # Pin slot squares around each pad
        slot_pen = QPen(_SILK_COLOR, 0.8)
        for pad in pads:
            px, py = pad.x_mm * scale, pad.y_mm * scale
            sr = pw * 0.45
            self._scene.addRect(QRectF(px - sr, py - sr, sr * 2, sr * 2), slot_pen)
        cx = (min_x + max_x) / 2
        self._add_ref_label(comp, cx, by - 10, scale)

    def _silk_led(self, comp, scale):
        """Circle with flat edge for polarity."""
        pads = comp.pads
        if len(pads) < 2:
            return
        pen = QPen(_SILK_COLOR, 1.4)
        p0x, p0y = pads[0].x_mm * scale, pads[0].y_mm * scale
        p1x, p1y = pads[1].x_mm * scale, pads[1].y_mm * scale
        cx, cy = (p0x + p1x) / 2, (p0y + p1y) / 2
        r = math.hypot(p1x - p0x, p1y - p0y) * 0.35
        r = max(r, 7)
        # Full circle
        self._scene.addEllipse(cx - r, cy - r, r * 2, r * 2, pen)
        # Flat edge (cathode side — near pad 2)
        flat_pen = QPen(_SILK_COLOR, 2.0)
        dx = p1x - cx
        dy = p1y - cy
        d = math.hypot(dx, dy) or 1
        nx, ny = dx / d, dy / d
        fx, fy = cx + nx * r * 0.7, cy + ny * r * 0.7
        px_dir, py_dir = -ny, nx  # perpendicular
        self._scene.addLine(fx - px_dir * r * 0.6, fy - py_dir * r * 0.6,
                            fx + px_dir * r * 0.6, fy + py_dir * r * 0.6, flat_pen)
        self._add_ref_label(comp, cx, cy - r - 10, scale)

    def _silk_diode(self, comp, scale):
        """Triangle + bar symbol."""
        pads = comp.pads
        if len(pads) < 2:
            return
        pen = QPen(_SILK_COLOR, 1.4)
        p0x, p0y = pads[0].x_mm * scale, pads[0].y_mm * scale
        p1x, p1y = pads[1].x_mm * scale, pads[1].y_mm * scale
        cx, cy = (p0x + p1x) / 2, (p0y + p1y) / 2
        dx, dy = p1x - p0x, p1y - p0y
        length = math.hypot(dx, dy) or 1
        ux, uy = dx / length, dy / length
        px, py = -uy, ux  # perpendicular
        tri_h = length * 0.3
        tri_w = length * 0.2
        # Triangle pointing from anode to cathode
        t1x, t1y = cx - ux * tri_h, cy - uy * tri_h
        t2x, t2y = cx + ux * tri_h, cy + uy * tri_h
        path = QPainterPath()
        path.moveTo(t1x + px * tri_w, t1y + py * tri_w)
        path.lineTo(t1x - px * tri_w, t1y - py * tri_w)
        path.lineTo(t2x, t2y)
        path.closeSubpath()
        self._scene.addPath(path, pen)
        # Bar at cathode
        bar_pen = QPen(_SILK_COLOR, 2.0)
        self._scene.addLine(t2x + px * tri_w, t2y + py * tri_w,
                            t2x - px * tri_w, t2y - py * tri_w, bar_pen)
        self._add_ref_label(comp, cx, cy - tri_w - 10, scale)

    def _silk_transistor(self, comp, scale):
        """Semi-circle body (TO-92 / SOT-23 style)."""
        pads = comp.pads
        if not pads:
            return
        pen = QPen(_SILK_COLOR, 1.4)
        cx = sum(p.x_mm for p in pads) / len(pads) * scale
        cy = sum(p.y_mm for p in pads) / len(pads) * scale
        spread = 0.0
        for p in pads:
            d = math.hypot(p.x_mm * scale - cx, p.y_mm * scale - cy)
            spread = max(spread, d)
        r = max(spread * 0.7, 8)
        # Draw arc (semi-circle with flat bottom)
        path = QPainterPath()
        path.arcMoveTo(QRectF(cx - r, cy - r, r * 2, r * 2), 0)
        path.arcTo(QRectF(cx - r, cy - r, r * 2, r * 2), 0, 180)
        path.lineTo(cx + r, cy)
        self._scene.addPath(path, pen)
        # Flat base line
        self._scene.addLine(cx - r, cy, cx + r, cy, pen)
        self._add_ref_label(comp, cx, cy - r - 10, scale)

    def _silk_crystal(self, comp, scale):
        """Rounded rectangle (HC49 style)."""
        pads = comp.pads
        if len(pads) < 2:
            return
        pen = QPen(_SILK_COLOR, 1.4)
        p0x, p0y = pads[0].x_mm * scale, pads[0].y_mm * scale
        p1x, p1y = pads[1].x_mm * scale, pads[1].y_mm * scale
        cx, cy = (p0x + p1x) / 2, (p0y + p1y) / 2
        length = math.hypot(p1x - p0x, p1y - p0y)
        bw = length * 0.55
        bh = max(pads[0].width_mm, pads[0].height_mm) * scale * 1.2
        bh = max(bh, 10)
        self._scene.addRoundedRect(QRectF(cx - bw / 2, cy - bh / 2, bw, bh),
                                    bw * 0.3, bh * 0.3, pen)
        self._add_ref_label(comp, cx, cy - bh / 2 - 10, scale)

    def _silk_inductor(self, comp, scale):
        """Coil / bump symbol between two pads."""
        pads = comp.pads
        if len(pads) < 2:
            return
        pen = QPen(_SILK_COLOR, 1.4)
        p0x, p0y = pads[0].x_mm * scale, pads[0].y_mm * scale
        p1x, p1y = pads[1].x_mm * scale, pads[1].y_mm * scale
        dx, dy = p1x - p0x, p1y - p0y
        length = math.hypot(dx, dy)
        # Draw 4 bumps (arcs) between pads
        n_bumps = 4
        path = QPainterPath()
        path.moveTo(p0x, p0y)
        for i in range(n_bumps):
            frac0 = i / n_bumps
            frac1 = (i + 1) / n_bumps
            sx = p0x + dx * frac0
            sy = p0y + dy * frac0
            ex = p0x + dx * frac1
            ey = p0y + dy * frac1
            # Control point perpendicular to line
            mx = (sx + ex) / 2 - (-dy / length) * length * 0.12
            my = (sy + ey) / 2 - (dx / length) * length * 0.12
            path.quadTo(mx, my, ex, ey)
        self._scene.addPath(path, pen)
        cx, cy = (p0x + p1x) / 2, (p0y + p1y) / 2
        self._add_ref_label(comp, cx, cy - 14, scale)

    def _silk_switch(self, comp, scale):
        """Square body with circle button."""
        pads = comp.pads
        if not pads:
            return
        pen = QPen(_SILK_COLOR, 1.4)
        cx = sum(p.x_mm for p in pads) / len(pads) * scale
        cy = sum(p.y_mm for p in pads) / len(pads) * scale
        spread = 0.0
        for p in pads:
            d = max(abs(p.x_mm * scale - cx), abs(p.y_mm * scale - cy))
            spread = max(spread, d)
        s = max(spread + 6, 10)
        self._scene.addRect(QRectF(cx - s, cy - s, s * 2, s * 2), pen)
        # Circle button in center
        br = s * 0.45
        self._scene.addEllipse(cx - br, cy - br, br * 2, br * 2, pen)
        self._add_ref_label(comp, cx, cy - s - 10, scale)

    def _silk_fuse(self, comp, scale):
        """Elongated capsule shape."""
        pads = comp.pads
        if len(pads) < 2:
            return
        pen = QPen(_SILK_COLOR, 1.4)
        p0x, p0y = pads[0].x_mm * scale, pads[0].y_mm * scale
        p1x, p1y = pads[1].x_mm * scale, pads[1].y_mm * scale
        cx, cy = (p0x + p1x) / 2, (p0y + p1y) / 2
        length = math.hypot(p1x - p0x, p1y - p0y)
        bw = length * 0.6
        bh = max(pads[0].width_mm, pads[0].height_mm) * scale * 0.7
        bh = max(bh, 6)
        rr = bh / 2  # fully rounded ends
        self._scene.addRoundedRect(QRectF(cx - bw / 2, cy - bh / 2, bw, bh),
                                    rr, rr, pen)
        self._add_ref_label(comp, cx, cy - bh / 2 - 10, scale)

    def _silk_generic(self, comp, scale):
        """Fallback: bounding box rectangle from pads."""
        pads = comp.pads
        if not pads:
            return
        pen = QPen(_SILK_COLOR, 1.2)
        min_x = min(p.x_mm for p in pads) * scale
        max_x = max(p.x_mm for p in pads) * scale
        min_y = min(p.y_mm for p in pads) * scale
        max_y = max(p.y_mm for p in pads) * scale
        pw = max(p.width_mm for p in pads) * scale
        margin = pw * 0.5 + 3
        body_rect = QRectF(min_x - margin, min_y - margin,
                           (max_x - min_x) + 2 * margin,
                           (max_y - min_y) + 2 * margin)
        self._scene.addRect(body_rect, pen)
        cx = (min_x + max_x) / 2
        self._add_ref_label(comp, cx, min_y - margin - 10, scale)

    def _add_ref_label(self, comp, cx, top_y, scale):
        """Add a ref designator label in cyan above the component."""
        ref_font = QFont("Consolas", 6, QFont.Weight.Bold)
        label = self._scene.addText(comp.ref, ref_font)
        label.setDefaultTextColor(_SILK_COLOR)
        lbr = label.boundingRect()
        label.setPos(cx - lbr.width() / 2, top_y - lbr.height())

    # ──────────────────────────────────────────────────────────────
    # Main rendering
    # ──────────────────────────────────────────────────────────────

    def render_board(self, board: Board, visible_layers: set[str]):
        self._scene.clear()
        scale = 6.0  # scene units per mm

        o = board.outline
        bx, by = o.x_mm * scale, o.y_mm * scale
        bw, bh = o.width_mm * scale, o.height_mm * scale

        # ── Board shadow ──
        shadow_offset = 5
        self._scene.addRect(
            QRectF(bx + shadow_offset, by + shadow_offset, bw, bh),
            QPen(Qt.PenStyle.NoPen),
            QBrush(QColor(0, 0, 0, 60)),
        )

        # ── Board fill (dark PCB substrate) ──
        self._scene.addRect(
            QRectF(bx, by, bw, bh),
            QPen(Qt.PenStyle.NoPen),
            QBrush(_BOARD_FILL),
        )

        # ── Grid ──
        grid_mm = 2.54
        grid_step = grid_mm * scale
        grid_pen_minor = QPen(_GRID_COLOR, 0.2)
        grid_pen_major = QPen(_GRID_MAJOR, 0.4)

        x = bx
        col = 0
        while x <= bx + bw:
            pen = grid_pen_major if col % 4 == 0 else grid_pen_minor
            self._scene.addLine(x, by, x, by + bh, pen)
            x += grid_step
            col += 1

        y = by
        row = 0
        while y <= by + bh:
            pen = grid_pen_major if row % 4 == 0 else grid_pen_minor
            self._scene.addLine(bx, y, bx + bw, y, pen)
            y += grid_step
            row += 1

        # ── Board outline (bright yellow) ──
        if "Edge.Cuts" in visible_layers:
            outline_pen = QPen(_BOARD_EDGE, 2.0)
            outline_pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
            self._scene.addRect(QRectF(bx, by, bw, bh), outline_pen)

        # ── Traces (solid copper, no dashed ratsnest) ──
        for trace in board.traces:
            if trace.layer not in visible_layers:
                continue
            color = QColor(_LAYER_COLORS.get(trace.layer, _LAYER_COLORS["F.Cu"]))
            alpha = _LAYER_ALPHA.get(trace.layer, 210)
            color.setAlpha(alpha)
            tw = max(trace.width_mm * scale, 3.0)
            pen = QPen(color, tw)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            sx = trace.start_x * scale
            sy = trace.start_y * scale
            ex = trace.end_x * scale
            ey = trace.end_y * scale
            self._scene.addLine(sx, sy, ex, ey, pen)

            # Junction dots at endpoints
            jr = tw * 0.55
            dot_brush = QBrush(color.lighter(115))
            no_pen = QPen(Qt.PenStyle.NoPen)
            self._scene.addEllipse(sx - jr, sy - jr, jr * 2, jr * 2, no_pen, dot_brush)
            self._scene.addEllipse(ex - jr, ey - jr, jr * 2, jr * 2, no_pen, dot_brush)

        # ── Vias ──
        for via in board.vias:
            r = via.diameter_mm / 2 * scale
            dr = via.drill_mm / 2 * scale
            vx, vy = via.x_mm * scale, via.y_mm * scale

            # Via ring
            via_grad = QRadialGradient(vx, vy, r)
            via_grad.setColorAt(0, _VIA_RING.lighter(120))
            via_grad.setColorAt(1, _VIA_RING)
            self._scene.addEllipse(
                vx - r, vy - r, r * 2, r * 2,
                QPen(_VIA_RING.darker(130), 0.5), QBrush(via_grad),
            )
            # Drill hole
            self._scene.addEllipse(
                vx - dr, vy - dr, dr * 2, dr * 2,
                QPen(Qt.PenStyle.NoPen), QBrush(_VIA_DRILL),
            )

        # ── Component pads ──
        for comp in board.components:
            if comp.layer not in visible_layers:
                continue

            for pad in comp.pads:
                w = pad.width_mm * scale
                h = pad.height_mm * scale
                px = pad.x_mm * scale
                py = pad.y_mm * scale

                # THT pad → magenta annular ring; SMD → layer copper color
                if pad.drill_mm > 0:
                    pad_color = QColor(_PAD_THT)
                    drill = pad.drill_mm * scale
                else:
                    pad_color = QColor(_PAD_SMD_FCU if comp.layer == "F.Cu" else _PAD_SMD_BCU)
                    drill = 0

                pad_item = _PadItem(px, py, w, h, pad.shape, drill, pad_color,
                                    comp.ref, pad.number, pad.net_name)
                pad_item.setPos(px, py)
                self._scene.addItem(pad_item)

            # ── Component-specific silkscreen ──
            if "F.SilkS" in visible_layers and comp.pads:
                comp_type = _classify_component(comp.ref, comp.value or "")
                dispatch = {
                    "resistor": self._silk_resistor,
                    "cap_ceramic": self._silk_cap_ceramic,
                    "cap_electrolytic": self._silk_cap_electrolytic,
                    "ic": self._silk_ic,
                    "connector": self._silk_connector,
                    "led": self._silk_led,
                    "diode": self._silk_diode,
                    "transistor": self._silk_transistor,
                    "mosfet": self._silk_transistor,
                    "crystal": self._silk_crystal,
                    "inductor": self._silk_inductor,
                    "switch": self._silk_switch,
                    "fuse": self._silk_fuse,
                    "relay": self._silk_generic,
                    "buzzer": self._silk_generic,
                    "potentiometer": self._silk_generic,
                }
                draw_fn = dispatch.get(comp_type, self._silk_generic)
                draw_fn(comp, scale)

        # ── Dimension annotations ──
        dim_pen = QPen(_TEXT_DIM, 0.5)
        dim_pen.setStyle(Qt.PenStyle.DashDotLine)
        dim_font = QFont("Consolas", 5)

        # Width
        self._scene.addLine(bx, by - 12, bx + bw, by - 12, dim_pen)
        w_label = self._scene.addText(f"{o.width_mm:.1f}mm", dim_font)
        w_label.setDefaultTextColor(_TEXT_DIM)
        w_label.setPos(bx + bw / 2 - 15, by - 24)

        # Height
        self._scene.addLine(bx - 12, by, bx - 12, by + bh, dim_pen)
        h_label = self._scene.addText(f"{o.height_mm:.1f}mm", dim_font)
        h_label.setDefaultTextColor(_TEXT_DIM)
        h_label.setPos(bx - 38, by + bh / 2 - 6)

        # ── Fit ──
        padding = 40
        rect = self._scene.itemsBoundingRect().adjusted(-padding, -padding, padding, padding)
        self._scene.setSceneRect(rect)
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

    def wheelEvent(self, event: QWheelEvent):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self._zoom *= factor
        self._zoom = max(0.1, min(10.0, self._zoom))
        self.scale(factor, factor)
