"""PCB layout viewer — renders the generated board with modern EDA styling."""

from __future__ import annotations

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

# ── Modern layer colors ──
_LAYER_COLORS = {
    "F.Cu":      QColor("#e8503a"),
    "B.Cu":      QColor("#4169e1"),
    "In1.Cu":    QColor("#c8c832"),
    "In2.Cu":    QColor("#32c832"),
    "Edge.Cuts": QColor("#d4af37"),
    "F.SilkS":   QColor("#e8e8e8"),
}

_LAYER_ALPHA = {
    "F.Cu": 220,
    "B.Cu": 200,
}

_BG_COLOR = QColor("#0c1015")
_BOARD_FILL = QColor("#1a2332")
_BOARD_EDGE = QColor("#d4af37")
_VIA_RING = QColor("#c8c832")
_VIA_DRILL = QColor("#0c1015")
_PAD_HOVER = QColor("#ffffff")
_TEXT_COLOR = QColor("#e0e0e0")
_TEXT_DIM = QColor("#6a7a8a")
_GRID_COLOR = QColor("#141e2a")
_GRID_MAJOR = QColor("#1a2636")
_ORIGIN_COLOR = QColor("#3a4a5a")
_COURTYARD = QColor(100, 200, 100, 40)
_MASK_COLOR = QColor(100, 60, 120, 30)


class _PadItem(QGraphicsItem):
    """Interactive pad with hover effect and tooltip."""

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
        return QRectF(-self._w/2 - 2, -self._h/2 - 2, self._w + 4, self._h + 4)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = self._color if not self._hovered else self._color.lighter(140)

        # Outer glow when hovered
        if self._hovered:
            glow = QRadialGradient(0, 0, max(self._w, self._h))
            glow.setColorAt(0, QColor(color.red(), color.green(), color.blue(), 60))
            glow.setColorAt(1, QColor(color.red(), color.green(), color.blue(), 0))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(glow))
            painter.drawEllipse(QPointF(0, 0), self._w, self._h)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))

        if self._shape == "circle":
            painter.drawEllipse(QRectF(-self._w/2, -self._h/2, self._w, self._h))
        elif self._shape == "roundrect":
            painter.drawRoundedRect(QRectF(-self._w/2, -self._h/2, self._w, self._h),
                                     self._w * 0.2, self._h * 0.2)
        else:
            painter.drawRect(QRectF(-self._w/2, -self._h/2, self._w, self._h))

        # Drill hole
        if self._drill > 0:
            painter.setBrush(QBrush(_VIA_DRILL))
            painter.drawEllipse(QPointF(0, 0), self._drill/2, self._drill/2)

        # Pad number
        if self._hovered:
            font = QFont("Consolas", 5)
            painter.setFont(font)
            painter.setPen(_TEXT_COLOR)
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
    """Internal graphics view for PCB rendering with modern styling."""

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

    def render_board(self, board: Board, visible_layers: set[str]):
        self._scene.clear()
        scale = 6.0  # scene units per mm (increased for clarity)

        o = board.outline
        bx, by = o.x_mm * scale, o.y_mm * scale
        bw, bh = o.width_mm * scale, o.height_mm * scale

        # ── Board shadow ──
        shadow_offset = 6
        self._scene.addRect(
            QRectF(bx + shadow_offset, by + shadow_offset, bw, bh),
            QPen(Qt.PenStyle.NoPen),
            QBrush(QColor(0, 0, 0, 80)),
        )

        # ── Board fill ──
        board_grad = QLinearGradient(bx, by, bx, by + bh)
        board_grad.setColorAt(0, QColor("#1c2d3f"))
        board_grad.setColorAt(0.5, QColor("#1a2836"))
        board_grad.setColorAt(1, QColor("#162230"))
        self._scene.addRect(
            QRectF(bx, by, bw, bh),
            QPen(Qt.PenStyle.NoPen),
            QBrush(board_grad),
        )

        # ── Grid ──
        grid_mm = 2.54
        grid_step = grid_mm * scale
        grid_pen_minor = QPen(_GRID_COLOR, 0.3)
        grid_pen_major = QPen(_GRID_MAJOR, 0.5)

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

        # ── Board outline ──
        if "Edge.Cuts" in visible_layers:
            outline_pen = QPen(_BOARD_EDGE, 2.0)
            outline_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            self._scene.addRect(QRectF(bx, by, bw, bh), outline_pen)

            # Corner markers
            corner_len = min(bw, bh) * 0.06
            marker_pen = QPen(_BOARD_EDGE, 1.2)
            for cx, cy, dx, dy in [
                (bx, by, 1, 1), (bx + bw, by, -1, 1),
                (bx, by + bh, 1, -1), (bx + bw, by + bh, -1, -1),
            ]:
                self._scene.addLine(cx, cy, cx + dx * corner_len, cy, marker_pen)
                self._scene.addLine(cx, cy, cx, cy + dy * corner_len, marker_pen)

        # ── Origin cross ──
        origin_pen = QPen(_ORIGIN_COLOR, 0.8)
        origin_pen.setStyle(Qt.PenStyle.DashLine)
        cx, cy = bx + bw / 2, by + bh / 2
        self._scene.addLine(cx - 15, cy, cx + 15, cy, origin_pen)
        self._scene.addLine(cx, cy - 15, cx, cy + 15, origin_pen)

        # ── Traces ──
        for trace in board.traces:
            if trace.layer not in visible_layers:
                continue
            color = QColor(_LAYER_COLORS.get(trace.layer, _LAYER_COLORS["F.Cu"]))
            alpha = _LAYER_ALPHA.get(trace.layer, 200)
            color.setAlpha(alpha)
            tw = max(trace.width_mm * scale, 2.0)
            if getattr(trace, 'is_ratsnest', False):
                pen = QPen(QColor(color.red(), color.green(), color.blue(), 160), max(tw * 0.6, 1.2))
                pen.setStyle(Qt.PenStyle.DashLine)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            else:
                pen = QPen(color, tw)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            sx = trace.start_x * scale
            sy = trace.start_y * scale
            ex = trace.end_x * scale
            ey = trace.end_y * scale
            self._scene.addLine(sx, sy, ex, ey, pen)

            # Solder joint dots at trace endpoints
            if not getattr(trace, 'is_ratsnest', False):
                jr = tw * 0.6
                dot_pen = QPen(Qt.PenStyle.NoPen)
                dot_brush = QBrush(color.lighter(110))
                self._scene.addEllipse(sx - jr, sy - jr, jr * 2, jr * 2, dot_pen, dot_brush)
                self._scene.addEllipse(ex - jr, ey - jr, jr * 2, jr * 2, dot_pen, dot_brush)

            # Net label at midpoint
            mx = (trace.start_x + trace.end_x) / 2 * scale
            my = (trace.start_y + trace.end_y) / 2 * scale
            length = ((trace.end_x - trace.start_x)**2 + (trace.end_y - trace.start_y)**2)**0.5
            if length * scale > 30 and trace.net_name:
                    nl = self._scene.addText(trace.net_name, QFont("Consolas", 4))
                    nl.setDefaultTextColor(QColor(color.red(), color.green(), color.blue(), 140))
                    nlr = nl.boundingRect()
                    nl.setPos(mx - nlr.width() / 2, my - nlr.height() / 2)

        # ── Vias ──
        for via in board.vias:
            r = via.diameter_mm / 2 * scale
            dr = via.drill_mm / 2 * scale
            vx, vy = via.x_mm * scale, via.y_mm * scale

            # Via ring with gradient
            via_grad = QRadialGradient(vx, vy, r)
            via_grad.setColorAt(0, _VIA_RING.lighter(120))
            via_grad.setColorAt(1, _VIA_RING)
            self._scene.addEllipse(
                vx - r, vy - r, r * 2, r * 2,
                QPen(_VIA_RING.darker(130), 0.5), QBrush(via_grad),
            )
            # Drill
            self._scene.addEllipse(
                vx - dr, vy - dr, dr * 2, dr * 2,
                QPen(Qt.PenStyle.NoPen), QBrush(_VIA_DRILL),
            )

        # ── Component pads and labels ──
        for comp in board.components:
            if comp.layer not in visible_layers:
                continue

            color = QColor(_LAYER_COLORS.get(comp.layer, _LAYER_COLORS["F.Cu"]))

            for pad in comp.pads:
                w = pad.width_mm * scale
                h = pad.height_mm * scale
                px = pad.x_mm * scale
                py = pad.y_mm * scale
                drill = pad.drill_mm * scale if pad.drill_mm > 0 else 0

                pad_item = _PadItem(px, py, w, h, pad.shape, drill, color,
                                    comp.ref, pad.number)
                pad_item.setPos(px, py)
                self._scene.addItem(pad_item)

            # ── Silkscreen ── component outline + label
            if "F.SilkS" in visible_layers:
                if comp.pads:
                    min_x = min(p.x_mm for p in comp.pads) * scale
                    max_x = max(p.x_mm for p in comp.pads) * scale
                    min_y = min(p.y_mm for p in comp.pads) * scale
                    max_y = max(p.y_mm for p in comp.pads) * scale
                    pw = max(p.width_mm for p in comp.pads) * scale
                    margin = pw * 0.6 + 3

                    body_rect = QRectF(min_x - margin, min_y - margin,
                                       (max_x - min_x) + 2 * margin,
                                       (max_y - min_y) + 2 * margin)
                    # Solid silkscreen outline
                    silk_pen = QPen(QColor(200, 200, 200, 180), 1.2)
                    self._scene.addRect(body_rect, silk_pen)

                    # Courtyard (wider, dashed)
                    court_rect = body_rect.adjusted(-3, -3, 3, 3)
                    court_pen = QPen(_COURTYARD, 0.6)
                    court_pen.setStyle(Qt.PenStyle.DashLine)
                    self._scene.addRect(court_rect, court_pen)

                    # Pin 1 indicator
                    p1 = comp.pads[0]
                    p1x, p1y = p1.x_mm * scale, p1.y_mm * scale
                    dot_r = 2.5
                    self._scene.addEllipse(
                        p1x - pw / 2 - dot_r - 4, p1y - dot_r,
                        dot_r * 2, dot_r * 2,
                        QPen(Qt.PenStyle.NoPen), QBrush(QColor(255, 255, 255, 200)),
                    )

                # Ref label (larger, centered)
                ref_font = QFont("Consolas", 7, QFont.Weight.Bold)
                label = self._scene.addText(comp.ref, ref_font)
                label.setDefaultTextColor(QColor(220, 220, 200))
                lbr = label.boundingRect()
                label.setPos(comp.x_mm * scale - lbr.width() / 2,
                             comp.y_mm * scale - lbr.height() - 4)

                # Value label (smaller, below ref)
                val_font = QFont("Consolas", 5)
                vlabel = self._scene.addText(comp.value or "", val_font)
                vlabel.setDefaultTextColor(QColor(180, 180, 160, 160))
                vbr = vlabel.boundingRect()
                vlabel.setPos(comp.x_mm * scale - vbr.width() / 2,
                              comp.y_mm * scale + 2)

        # ── Dimension annotations ──
        dim_pen = QPen(_TEXT_DIM, 0.5)
        dim_pen.setStyle(Qt.PenStyle.DashDotLine)
        dim_font = QFont("Consolas", 5)

        # Width dimension
        self._scene.addLine(bx, by - 12, bx + bw, by - 12, dim_pen)
        w_label = self._scene.addText(f"{o.width_mm:.1f}mm", dim_font)
        w_label.setDefaultTextColor(_TEXT_DIM)
        w_label.setPos(bx + bw / 2 - 15, by - 24)

        # Height dimension
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
