"""Schematic editor — interactive drag-and-drop editor with wire routing."""

from __future__ import annotations

import json
import math
import heapq
from collections import defaultdict
from typing import Optional

from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QGraphicsItem,
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFormLayout,
)
from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QByteArray
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QWheelEvent,
    QPainterPath, QLinearGradient, QUndoStack, QUndoCommand,
)

from src.gui.i18n import tr
from src.gui.theme import tc, ThemeManager

from src.ai.schemas import (
    CircuitSpec, ComponentSpec, NetSpec, PinSpec, PinRef,
    ComponentCategory,
)
from src.gui.component_palette import MIME_TYPE, _PIN_TEMPLATES

# ── Palette ──
def _pal():
    c = tc()
    return {
        "bg":         QColor(c.scene_bg),
        "wire":       QColor("#3fb950"),
        "wire_pwr":   QColor("#f0883e"),
        "wire_gnd":   QColor("#58a6ff"),
        "text":       QColor(c.scene_text),
        "text_dim":   QColor(c.text_dim),
        "pin_dot":    QColor("#58a6ff"),
        "selected":   QColor("#ffa657"),
        "junction":   QColor("#3fb950"),
    }
_PAL = _pal()

_CAT_COLORS = {
    "resistor": QColor("#e6a23c"), "capacitor": QColor("#409eff"),
    "inductor": QColor("#67c23a"), "diode": QColor("#f56c6c"),
    "led": QColor("#ff6b9d"), "transistor": QColor("#e6a23c"),
    "mosfet": QColor("#d4a843"), "ic": QColor("#a78bfa"),
    "regulator": QColor("#34d399"), "opamp": QColor("#60a5fa"),
    "microcontroller": QColor("#a78bfa"), "connector": QColor("#9ca3af"),
    "crystal": QColor("#fbbf24"), "relay": QColor("#fb923c"),
    "transformer": QColor("#67c23a"), "fuse": QColor("#fbbf24"),
    "switch": QColor("#9ca3af"), "sensor": QColor("#38bdf8"),
    "other": QColor("#6b7280"),
}


# =====================================================================
# Schematic symbol drawing helpers
# =====================================================================

def _draw_resistor_symbol(p: QPainter, cx: float, cy: float, w: float, h: float, color: QColor):
    p.setPen(QPen(color, 1.8))
    p.setBrush(Qt.BrushStyle.NoBrush)
    segs = 6
    sw = w / segs
    path = QPainterPath(QPointF(cx - w / 2, cy))
    for i in range(segs):
        x0 = cx - w / 2 + i * sw
        dy = -h * 0.35 if i % 2 == 0 else h * 0.35
        path.lineTo(x0 + sw / 2, cy + dy)
        path.lineTo(x0 + sw, cy)
    p.drawPath(path)


def _draw_capacitor_symbol(p: QPainter, cx: float, cy: float, w: float, h: float, color: QColor):
    gap = w * 0.12
    ph = h * 0.6
    p.setPen(QPen(color, 2.2))
    p.drawLine(QPointF(cx - gap, cy - ph / 2), QPointF(cx - gap, cy + ph / 2))
    p.drawLine(QPointF(cx + gap, cy - ph / 2), QPointF(cx + gap, cy + ph / 2))


def _draw_diode_symbol(p: QPainter, cx: float, cy: float, w: float, h: float, color: QColor):
    tw = w * 0.35
    th = h * 0.5
    p.setPen(QPen(color, 1.8))
    p.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 50)))
    path = QPainterPath()
    path.moveTo(cx - tw, cy - th / 2)
    path.lineTo(cx - tw, cy + th / 2)
    path.lineTo(cx + tw, cy)
    path.closeSubpath()
    p.drawPath(path)
    p.drawLine(QPointF(cx + tw, cy - th / 2), QPointF(cx + tw, cy + th / 2))


def _draw_ic_symbol(p: QPainter, cx: float, cy: float, w: float, h: float, color: QColor):
    r = QRectF(cx - w * 0.4, cy - h * 0.4, w * 0.8, h * 0.8)
    p.setPen(QPen(color, 1.5))
    p.setBrush(QBrush(QColor(color.red(), color.green(), color.blue(), 20)))
    p.drawRect(r)
    nr = min(w, h) * 0.08
    p.setBrush(QBrush(_PAL["bg"]))
    p.drawEllipse(QPointF(cx, r.top()), nr, nr)


_SYM = {
    "resistor": _draw_resistor_symbol,
    "capacitor": _draw_capacitor_symbol,
    "diode": _draw_diode_symbol,
    "led": _draw_diode_symbol,
    "ic": _draw_ic_symbol,
    "regulator": _draw_ic_symbol,
    "opamp": _draw_ic_symbol,
    "microcontroller": _draw_ic_symbol,
}


class ComponentItem(QGraphicsItem):
    PIN_SP = 20.0
    WIRE_LEN = 30.0

    def __init__(self, comp: ComponentSpec, parent=None):
        super().__init__(parent)
        self.comp = comp
        self._color = _CAT_COLORS.get(comp.category.value, _CAT_COLORS["other"])
        n = max(len(comp.pins), 2)
        self._left = comp.pins[: n // 2 + n % 2]
        self._right = comp.pins[n // 2 + n % 2:]
        side = max(len(self._left), len(self._right), 1)
        self._w = 110.0
        self._hdr = 28.0
        self._body = side * self.PIN_SP + 10
        self._h = self._hdr + self._body
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.setToolTip(f"{comp.ref}: {comp.value}\n{comp.description}")
        self._drag_start_pos: QPointF | None = None

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            # Snap to grid (20px)
            grid = 20.0
            x = round(value.x() / grid) * grid
            y = round(value.y() / grid) * grid
            return QPointF(x, y)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            # Tell the view to re-route wires
            view = self.scene()
            if view:
                for v in view.views():
                    if isinstance(v, SchematicView) and v._interactive:
                        v._schedule_reroute()
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        self._drag_start_pos = self.pos()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self._drag_start_pos and self._drag_start_pos != self.pos():
            for v in self.scene().views():
                if isinstance(v, SchematicView) and v._interactive:
                    v._push_move_cmd(self, self._drag_start_pos, self.pos())
        self._drag_start_pos = None

    def mouseDoubleClickEvent(self, event):
        """Open inline editor for value & ref."""
        for v in self.scene().views():
            if isinstance(v, SchematicView) and v._interactive:
                v._edit_component(self)
        event.accept()

    def width(self):
        return self._w + 2 * self.WIRE_LEN + 36

    def height(self):
        return self._h + 12

    def boundingRect(self) -> QRectF:
        m = self.WIRE_LEN + 18
        return QRectF(-m, -6, self._w + 2 * m, self._h + 12)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = self._color
        sel = self.isSelected()
        bc = _PAL["selected"] if sel else c

        # Body
        body = QRectF(0, 0, self._w, self._h)
        g = QLinearGradient(0, 0, 0, self._h)
        g.setColorAt(0, QColor(c.red(), c.green(), c.blue(), 25))
        g.setColorAt(1, QColor(c.red(), c.green(), c.blue(), 8))
        painter.setPen(QPen(bc, 1.6))
        painter.setBrush(QBrush(g))
        painter.drawRoundedRect(body, 5, 5)

        # Header
        hp = QPainterPath()
        hp.addRoundedRect(QRectF(0, 0, self._w, self._hdr), 5, 5)
        hp.addRect(QRectF(0, self._hdr - 5, self._w, 5))
        hg = QLinearGradient(0, 0, 0, self._hdr)
        hg.setColorAt(0, QColor(c.red(), c.green(), c.blue(), 55))
        hg.setColorAt(1, QColor(c.red(), c.green(), c.blue(), 20))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(hg))
        painter.drawPath(hp)

        # Separator
        painter.setPen(QPen(QColor(c.red(), c.green(), c.blue(), 60), 0.5))
        painter.drawLine(QPointF(3, self._hdr), QPointF(self._w - 3, self._hdr))

        # Symbol
        fn = _SYM.get(self.comp.category.value)
        if fn:
            fn(painter, self._w / 2, self._hdr + self._body / 2,
               self._w * 0.55, self._body * 0.5, c)

        # Ref
        painter.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        painter.setPen(_PAL["text"])
        painter.drawText(QRectF(6, 1, self._w - 12, 15),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         self.comp.ref)

        # Value
        painter.setFont(QFont("Consolas", 7))
        painter.setPen(_PAL["text_dim"])
        painter.drawText(QRectF(6, 14, self._w - 12, 13),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         self.comp.value)

        # Pins
        self._draw_pins(painter, self._left, True)
        self._draw_pins(painter, self._right, False)

    def _draw_pins(self, painter: QPainter, pins, left: bool):
        painter.setFont(QFont("Consolas", 7))
        for i, pin in enumerate(pins):
            py = self._hdr + 14 + i * self.PIN_SP
            if left:
                xe, xt = 0.0, -self.WIRE_LEN
                lr = QRectF(4, py - 7, 46, 14)
                la = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
                nr = QRectF(xt - 16, py - 7, 14, 14)
                na = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            else:
                xe, xt = self._w, self._w + self.WIRE_LEN
                lr = QRectF(self._w - 50, py - 7, 46, 14)
                la = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                nr = QRectF(xt + 2, py - 7, 14, 14)
                na = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            painter.setPen(QPen(_PAL["pin_dot"], 1.3))
            painter.drawLine(QPointF(xt, py), QPointF(xe, py))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(_PAL["pin_dot"]))
            painter.drawEllipse(QPointF(xt, py), 3.0, 3.0)
            painter.setPen(_PAL["text"])
            painter.drawText(lr, la, pin.name if pin.name else pin.number)
            painter.setPen(_PAL["text_dim"])
            painter.drawText(nr, na, pin.number)

    def get_pin_pos(self, pin_id: str) -> QPointF:
        """Get pin position by number or name (case-insensitive)."""
        pin_lower = pin_id.lower()
        # 1. Try exact number match
        for i, p in enumerate(self._left):
            if p.number == pin_id:
                return self.mapToScene(QPointF(-self.WIRE_LEN,
                                               self._hdr + 14 + i * self.PIN_SP))
        for i, p in enumerate(self._right):
            if p.number == pin_id:
                return self.mapToScene(QPointF(self._w + self.WIRE_LEN,
                                               self._hdr + 14 + i * self.PIN_SP))
        # 2. Try name match (case-insensitive)
        for i, p in enumerate(self._left):
            if p.name and p.name.lower() == pin_lower:
                return self.mapToScene(QPointF(-self.WIRE_LEN,
                                               self._hdr + 14 + i * self.PIN_SP))
        for i, p in enumerate(self._right):
            if p.name and p.name.lower() == pin_lower:
                return self.mapToScene(QPointF(self._w + self.WIRE_LEN,
                                               self._hdr + 14 + i * self.PIN_SP))
        # 3. Fallback: first left pin position (not center)
        if self._left:
            return self.mapToScene(QPointF(-self.WIRE_LEN,
                                           self._hdr + 14))
        if self._right:
            return self.mapToScene(QPointF(self._w + self.WIRE_LEN,
                                           self._hdr + 14))
        return self.mapToScene(QPointF(self._w / 2, self._h / 2))

    def pin_at_scene_pos(self, scene_pos: QPointF, radius: float = 10.0
                         ) -> PinSpec | None:
        """Return the PinSpec closest to *scene_pos* if within *radius*."""
        best_pin: PinSpec | None = None
        best_d = radius
        for i, p in enumerate(self._left):
            pp = self.mapToScene(QPointF(-self.WIRE_LEN,
                                         self._hdr + 14 + i * self.PIN_SP))
            d = math.hypot(pp.x() - scene_pos.x(), pp.y() - scene_pos.y())
            if d < best_d:
                best_d = d
                best_pin = p
        for i, p in enumerate(self._right):
            pp = self.mapToScene(QPointF(self._w + self.WIRE_LEN,
                                         self._hdr + 14 + i * self.PIN_SP))
            d = math.hypot(pp.x() - scene_pos.x(), pp.y() - scene_pos.y())
            if d < best_d:
                best_d = d
                best_pin = p
        return best_pin


# =====================================================================
# Grid-based layout with collision avoidance
# =====================================================================

def _build_adj(spec: CircuitSpec) -> dict[str, set[str]]:
    adj: dict[str, set[str]] = defaultdict(set)
    for net in spec.nets:
        refs = {c.ref for c in net.connections}
        for r in refs:
            adj[r] |= refs - {r}
    return adj


def _grid_layout(spec: CircuitSpec) -> dict[str, tuple[float, float]]:
    """Place components on a non-overlapping grid, grouped by category."""
    if not spec.components:
        return {}

    adj = _build_adj(spec)

    # Classify components
    connectors = []
    ics = []
    passives = []
    for c in spec.components:
        cat = c.category.value
        if cat == "connector":
            connectors.append(c)
        elif cat in ("ic", "microcontroller", "opamp", "regulator"):
            ics.append(c)
        else:
            passives.append(c)

    # Cell sizes for grid placement (generous spacing to avoid overlap)
    cell_w = 280.0
    cell_h = 240.0

    pos: dict[str, tuple[float, float]] = {}

    # Row 0: connectors across the top
    for i, c in enumerate(connectors):
        pos[c.ref] = (i * cell_w, 0)

    # Row 1: ICs centered below connectors
    ic_row_y = cell_h
    total_width = max(len(connectors), 1) * cell_w
    ic_start_x = (total_width - len(ics) * cell_w) / 2 if ics else 0
    for i, c in enumerate(ics):
        pos[c.ref] = (ic_start_x + i * cell_w, ic_row_y)

    # Remaining rows: passives, placed near their connected ICs/connectors
    # First: passives that connect to placed components
    placed_refs = set(pos.keys())
    unplaced = list(passives)
    passive_slots: dict[str, list] = defaultdict(list)  # parent_ref -> list of passive comps

    for c in unplaced:
        neighbors = adj.get(c.ref, set())
        parent = None
        for n in neighbors:
            if n in placed_refs:
                parent = n
                break
        if parent:
            passive_slots[parent].append(c)
        else:
            passive_slots["_orphan"].append(c)

    # Place passives in rows below their parent, spreading them out
    passive_row_y = ic_row_y + cell_h
    for parent_ref, comps in passive_slots.items():
        if parent_ref == "_orphan":
            continue
        px, py = pos.get(parent_ref, (0, 0))
        n = len(comps)
        start_x = px - ((n - 1) / 2) * cell_w * 0.7
        for i, c in enumerate(comps):
            cx = start_x + i * cell_w * 0.7
            pos[c.ref] = (cx, passive_row_y)

    # Orphans go in last row
    orphans = passive_slots.get("_orphan", [])
    if orphans:
        orphan_row_y = passive_row_y + cell_h
        for i, c in enumerate(orphans):
            pos[c.ref] = (i * cell_w * 0.7, orphan_row_y)

    # ── Collision resolution: push apart any overlapping items ──
    refs = list(pos.keys())
    for iteration in range(10):  # max iterations
        moved = False
        for i in range(len(refs)):
            for j in range(i + 1, len(refs)):
                x1, y1 = pos[refs[i]]
                x2, y2 = pos[refs[j]]
                dx = abs(x2 - x1)
                dy = abs(y2 - y1)
                min_dx = cell_w * 0.65
                min_dy = cell_h * 0.55
                if dx < min_dx and dy < min_dy:
                    # Push apart horizontally
                    push_x = (min_dx - dx) / 2 + 10
                    if x1 <= x2:
                        pos[refs[i]] = (x1 - push_x, y1)
                        pos[refs[j]] = (x2 + push_x, y2)
                    else:
                        pos[refs[i]] = (x1 + push_x, y1)
                        pos[refs[j]] = (x2 - push_x, y2)
                    moved = True
        if not moved:
            break

    return pos


# =====================================================================
# Grid-based maze router (Lee algorithm with bend penalty)
# =====================================================================

_GRID_CELL = 8  # px per routing grid cell (finer = more routing room)

_BLOCKED = -1
_FREE = 0
# Cost weights
_STRAIGHT_COST = 1
_BEND_COST = 5        # discourage unnecessary bends
_ADJACENT_COST = 3    # discourage routing next to obstacles/existing wires


class _RoutingGrid:
    """2D grid for maze routing.  Each cell is 0 (free) or -1 (blocked)."""

    def __init__(self, x_min: float, y_min: float, x_max: float, y_max: float):
        self.x_min = x_min
        self.y_min = y_min
        self.cols = max(1, int((x_max - x_min) / _GRID_CELL) + 2)
        self.rows = max(1, int((y_max - y_min) / _GRID_CELL) + 2)
        self._cells = [[_FREE] * self.cols for _ in range(self.rows)]

    def block_rect(self, x1: float, y1: float, x2: float, y2: float):
        """Mark rectangular region as obstacle."""
        c0 = max(0, int((x1 - self.x_min) / _GRID_CELL) - 1)
        c1 = min(self.cols - 1, int((x2 - self.x_min) / _GRID_CELL) + 1)
        r0 = max(0, int((y1 - self.y_min) / _GRID_CELL) - 1)
        r1 = min(self.rows - 1, int((y2 - self.y_min) / _GRID_CELL) + 1)
        for r in range(r0, r1 + 1):
            for c in range(c0, c1 + 1):
                self._cells[r][c] = _BLOCKED

    def is_free(self, r: int, c: int) -> bool:
        if 0 <= r < self.rows and 0 <= c < self.cols:
            return self._cells[r][c] != _BLOCKED
        return False

    def mark_wire(self, r: int, c: int):
        """Mark cell as blocked by a routed wire — prevents future routes from crossing."""
        if 0 <= r < self.rows and 0 <= c < self.cols:
            self._cells[r][c] = _BLOCKED

    def to_grid(self, x: float, y: float) -> tuple[int, int]:
        """Scene coords → (row, col)."""
        c = int((x - self.x_min) / _GRID_CELL)
        r = int((y - self.y_min) / _GRID_CELL)
        return (max(0, min(r, self.rows - 1)),
                max(0, min(c, self.cols - 1)))

    def to_scene(self, r: int, c: int) -> QPointF:
        """Grid (row, col) → scene coords (cell center)."""
        return QPointF(self.x_min + c * _GRID_CELL + _GRID_CELL / 2,
                       self.y_min + r * _GRID_CELL + _GRID_CELL / 2)


# Direction vectors: (dr, dc)
_DIRS = [(0, 1), (0, -1), (1, 0), (-1, 0)]


def _lee_route(grid: _RoutingGrid, start: tuple[int, int],
               end: tuple[int, int]) -> Optional[list[tuple[int, int]]]:
    """Route from start to end on the grid using Dijkstra with bend penalty.

    Returns list of (row, col) cells forming the path, or None if no path.
    """
    if start == end:
        return [start]

    # Make start/end temporarily free (they may be on component edge)
    sr, sc = start
    er, ec = end

    # Dijkstra priority queue: (cost, row, col, prev_dir)
    # prev_dir: 0=horiz, 1=vert, -1=start
    INF = float('inf')
    # dist[r][c][dir] — minimum cost to reach (r,c) arriving from direction dir
    dist: dict[tuple[int, int, int], float] = {}
    prev: dict[tuple[int, int, int], tuple[int, int, int] | None] = {}

    heap: list[tuple[float, int, int, int]] = []
    for d in range(2):
        dist[(sr, sc, d)] = 0
        prev[(sr, sc, d)] = None
        heapq.heappush(heap, (0, sr, sc, d))

    found = False
    end_state = (er, ec, 0)

    while heap:
        cost, r, c, prev_d = heapq.heappop(heap)

        if r == er and c == ec:
            end_state = (r, c, prev_d)
            found = True
            break

        if cost > dist.get((r, c, prev_d), INF):
            continue

        for dr, dc in _DIRS:
            nr, nc = r + dr, c + dc
            if nr < 0 or nr >= grid.rows or nc < 0 or nc >= grid.cols:
                continue
            if not grid.is_free(nr, nc) and (nr, nc) != end:
                continue

            cur_d = 0 if dc != 0 else 1  # horizontal or vertical
            move_cost = _STRAIGHT_COST
            if prev_d >= 0 and cur_d != prev_d:
                move_cost += _BEND_COST
            # Penalize routing adjacent to any obstacle/wire (keeps spacing)
            for dr2, dc2 in _DIRS:
                ar, ac = nr + dr2, nc + dc2
                if 0 <= ar < grid.rows and 0 <= ac < grid.cols:
                    if not grid.is_free(ar, ac):
                        move_cost += _ADJACENT_COST
                        break

            new_cost = cost + move_cost
            key = (nr, nc, cur_d)
            if new_cost < dist.get(key, INF):
                dist[key] = new_cost
                prev[key] = (r, c, prev_d)
                heapq.heappush(heap, (new_cost, nr, nc, cur_d))

    if not found:
        return None

    # Backtrace path
    path: list[tuple[int, int]] = []
    state: tuple[int, int, int] | None = end_state
    while state is not None:
        path.append((state[0], state[1]))
        state = prev.get(state)
    path.reverse()
    return path


def _smooth_path(path: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Reduce grid path to corner/bend points only (minimal waypoints)."""
    if len(path) <= 2:
        return path
    result = [path[0]]
    for i in range(1, len(path) - 1):
        pr, pc = path[i - 1]
        cr, cc = path[i]
        nr, nc = path[i + 1]
        dr1, dc1 = cr - pr, cc - pc
        dr2, dc2 = nr - cr, nc - cc
        if (dr1, dc1) != (dr2, dc2):  # direction changed — it's a corner
            result.append(path[i])
    result.append(path[-1])
    return result


def _pin_distance(a: QPointF, b: QPointF) -> float:
    return math.sqrt((a.x() - b.x()) ** 2 + (a.y() - b.y()) ** 2)


def _mst_edges(pts: list[QPointF]) -> list[tuple[int, int]]:
    """Compute minimum spanning tree edges (Prim's) for pin positions.

    Returns list of (i, j) index pairs into pts.
    """
    n = len(pts)
    if n <= 1:
        return []
    if n == 2:
        return [(0, 1)]

    in_tree = [False] * n
    min_cost = [float('inf')] * n
    min_edge = [-1] * n
    min_cost[0] = 0.0
    edges: list[tuple[int, int]] = []

    for _ in range(n):
        # Pick minimum cost node not in tree
        u = -1
        for v in range(n):
            if not in_tree[v] and (u < 0 or min_cost[v] < min_cost[u]):
                u = v
        in_tree[u] = True
        if min_edge[u] >= 0:
            edges.append((min_edge[u], u))
        for v in range(n):
            if not in_tree[v]:
                d = _pin_distance(pts[u], pts[v])
                if d < min_cost[v]:
                    min_cost[v] = d
                    min_edge[v] = u
    return edges


def _build_routing_grid(comp_items: dict[str, 'ComponentItem'],
                        scene: QGraphicsScene) -> _RoutingGrid:
    """Create routing grid and mark component bodies as obstacles."""
    rect = scene.itemsBoundingRect().adjusted(-150, -150, 150, 150)
    grid = _RoutingGrid(rect.left(), rect.top(), rect.right(), rect.bottom())

    for ref, item in comp_items.items():
        br = item.boundingRect()
        pos = item.pos()
        # Block the component body area (with small margin)
        x1 = pos.x() + br.left() + 5
        y1 = pos.y() + br.top() + 5
        x2 = pos.x() + br.right() - 5
        y2 = pos.y() + br.bottom() - 5
        grid.block_rect(x1, y1, x2, y2)

    return grid


def _route_nets(spec: CircuitSpec, comp_items: dict[str, 'ComponentItem'],
                scene: QGraphicsScene):
    """Route all nets using maze router and draw wires on the scene."""
    if not spec.nets:
        return

    grid = _build_routing_grid(comp_items, scene)

    _GND = {"GND", "VSS", "V-", "0V", "AGND", "DGND"}
    _PWR = {"VCC", "VDD", "V+", "5V", "3V3", "3.3V", "12V", "VIN"} | _GND

    # Collect net info: (net, pts, color, is_power)
    net_infos: list[tuple[NetSpec, list[QPointF], QColor, bool]] = []
    for net in spec.nets:
        if len(net.connections) < 2:
            continue

        n_upper = net.name.upper()
        is_gnd = n_upper in _GND
        is_pwr = n_upper in _PWR
        color = (_PAL["wire_gnd"] if is_gnd else
                 _PAL["wire_pwr"] if is_pwr else _PAL["wire"])

        pts: list[QPointF] = []
        for conn in net.connections:
            it = comp_items.get(conn.ref)
            if it:
                pos = it.get_pin_pos(conn.pin)
                if not any(abs(pos.x() - p.x()) < 1 and abs(pos.y() - p.y()) < 1 for p in pts):
                    pts.append(pos)

        if len(pts) >= 2:
            net_infos.append((net, pts, color, is_pwr))

    # Sort: short-distance nets first (easier to route), power/GND last
    def _net_sort_key(info):
        _, pts, _, is_pwr = info
        total_d = sum(_pin_distance(pts[i], pts[i+1])
                      for i in range(len(pts) - 1))
        return (1 if is_pwr else 0, total_d)

    net_infos.sort(key=_net_sort_key)

    # Route each net
    for net, pts, color, is_pwr in net_infos:
        pen = QPen(color, 1.8)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

        # Multi-pin nets: use MST to determine which pairs to route
        mst = _mst_edges(pts)

        routed_any = False
        for i, j in mst:
            p1, p2 = pts[i], pts[j]
            gr_start = grid.to_grid(p1.x(), p1.y())
            gr_end = grid.to_grid(p2.x(), p2.y())

            raw_path = _lee_route(grid, gr_start, gr_end)
            if raw_path:
                # Mark routed cells
                for r, c in raw_path:
                    grid.mark_wire(r, c)

                waypoints = _smooth_path(raw_path)

                # Build painter path: pin → first waypoint (snap), corners, last → pin
                wire_path = QPainterPath(p1)
                # From pin to first waypoint
                first_wp = grid.to_scene(*waypoints[0])
                wire_path.lineTo(QPointF(first_wp.x(), p1.y()))
                if abs(first_wp.y() - p1.y()) > 1:
                    wire_path.lineTo(first_wp)

                for wi in range(1, len(waypoints)):
                    wire_path.lineTo(grid.to_scene(*waypoints[wi]))

                # From last waypoint to pin
                last_wp = grid.to_scene(*waypoints[-1])
                wire_path.lineTo(QPointF(p2.x(), last_wp.y()))
                wire_path.lineTo(p2)

                scene.addPath(wire_path, pen)
                routed_any = True
            else:
                # Fallback: L-route via two candidate corners, pick the one
                # that crosses fewer blocked cells.
                corners = [
                    QPointF(p2.x(), p1.y()),  # horizontal first
                    QPointF(p1.x(), p2.y()),  # vertical first
                ]
                best_corner = corners[0]
                best_cost = float('inf')
                for cp in corners:
                    cost = 0
                    for seg in [(p1, cp), (cp, p2)]:
                        sa, sb = seg
                        sx0, sy0 = sa.x(), sa.y()
                        sx1, sy1 = sb.x(), sb.y()
                        steps = max(1, int(math.hypot(sx1 - sx0, sy1 - sy0) / _GRID_CELL))
                        for s in range(steps + 1):
                            t = s / steps
                            gr = grid.to_grid(sx0 + (sx1 - sx0) * t,
                                              sy0 + (sy1 - sy0) * t)
                            if not grid.is_free(*gr):
                                cost += 100
                    if cost < best_cost:
                        best_cost = cost
                        best_corner = cp
                fallback = QPainterPath(p1)
                fallback.lineTo(best_corner)
                fallback.lineTo(p2)
                scene.addPath(fallback, pen)
                # Mark fallback cells as blocked for future routes
                for seg in [(p1, best_corner), (best_corner, p2)]:
                    sa, sb = seg
                    sx0, sy0 = sa.x(), sa.y()
                    sx1, sy1 = sb.x(), sb.y()
                    steps = max(1, int(math.hypot(sx1 - sx0, sy1 - sy0) / _GRID_CELL))
                    for s in range(steps + 1):
                        t = s / steps
                        gr = grid.to_grid(sx0 + (sx1 - sx0) * t,
                                          sy0 + (sy1 - sy0) * t)
                        grid.mark_wire(*gr)
                routed_any = True

        # Junction dots at each pin
        for pt in pts:
            scene.addEllipse(
                pt.x() - 3.5, pt.y() - 3.5, 7, 7,
                QPen(Qt.PenStyle.NoPen), QBrush(color))

        # Net name label
        if pts:
            lbl = scene.addText(net.name, QFont("Consolas", 7, QFont.Weight.Bold))
            lbl.setDefaultTextColor(color)
            lbl.setPos(pts[0].x() + 6, pts[0].y() - 18)


# =====================================================================
# Undo / Redo Commands
# =====================================================================

class _AddComponentCmd(QUndoCommand):
    def __init__(self, view: 'SchematicView', comp: ComponentSpec,
                 pos: QPointF, text: str = "Add Component"):
        super().__init__(text)
        self._view = view
        self._comp = comp
        self._pos = pos

    def redo(self):
        self._view._spec.components.append(self._comp)
        item = ComponentItem(self._comp)
        item.setPos(self._pos)
        self._view._scene.addItem(item)
        self._view._comp_items[self._comp.ref] = item
        self._view._reroute_wires()
        self._view.circuit_modified.emit(self._view._spec)

    def undo(self):
        item = self._view._comp_items.pop(self._comp.ref, None)
        if item:
            self._view._scene.removeItem(item)
        self._view._spec.components = [
            c for c in self._view._spec.components if c.ref != self._comp.ref
        ]
        # Remove nets referencing this component
        self._view._spec.nets = [
            n for n in self._view._spec.nets
            if not all(c.ref == self._comp.ref for c in n.connections)
        ]
        for net in self._view._spec.nets:
            net.connections = [c for c in net.connections if c.ref != self._comp.ref]
        self._view._spec.nets = [n for n in self._view._spec.nets if len(n.connections) >= 2]
        self._view._reroute_wires()
        self._view.circuit_modified.emit(self._view._spec)


class _MoveComponentCmd(QUndoCommand):
    def __init__(self, view: 'SchematicView', item: ComponentItem,
                 old_pos: QPointF, new_pos: QPointF):
        super().__init__("Move Component")
        self._view = view
        self._item = item
        self._old = old_pos
        self._new = new_pos
        self._first = True

    def redo(self):
        if self._first:
            self._first = False
            return  # item is already at new pos
        self._item.setPos(self._new)
        self._view._reroute_wires()

    def undo(self):
        self._item.setPos(self._old)
        self._view._reroute_wires()


class _DeleteComponentCmd(QUndoCommand):
    def __init__(self, view: 'SchematicView', item: ComponentItem):
        super().__init__("Delete Component")
        self._view = view
        self._comp = item.comp
        self._pos = item.pos()
        self._removed_nets: list[NetSpec] = []

    def redo(self):
        item = self._view._comp_items.pop(self._comp.ref, None)
        if item:
            self._view._scene.removeItem(item)
        self._view._spec.components = [
            c for c in self._view._spec.components if c.ref != self._comp.ref
        ]
        # Save and remove affected nets
        self._removed_nets = []
        for net in list(self._view._spec.nets):
            had = any(c.ref == self._comp.ref for c in net.connections)
            if had:
                self._removed_nets.append(net.model_copy(deep=True))
                net.connections = [c for c in net.connections if c.ref != self._comp.ref]
        self._view._spec.nets = [n for n in self._view._spec.nets if len(n.connections) >= 2]
        self._view._reroute_wires()
        self._view.circuit_modified.emit(self._view._spec)

    def undo(self):
        self._view._spec.components.append(self._comp)
        item = ComponentItem(self._comp)
        item.setPos(self._pos)
        self._view._scene.addItem(item)
        self._view._comp_items[self._comp.ref] = item
        # Restore removed nets
        for net in self._removed_nets:
            # Check if net with same name exists
            existing = None
            for n in self._view._spec.nets:
                if n.name == net.name:
                    existing = n
                    break
            if existing:
                existing.connections = net.connections
            else:
                self._view._spec.nets.append(net)
        self._view._reroute_wires()
        self._view.circuit_modified.emit(self._view._spec)


class _EditComponentCmd(QUndoCommand):
    def __init__(self, view: 'SchematicView', item: ComponentItem,
                 old_ref: str, old_val: str, new_ref: str, new_val: str):
        super().__init__("Edit Component")
        self._view = view
        self._item = item
        self._old_ref = old_ref
        self._old_val = old_val
        self._new_ref = new_ref
        self._new_val = new_val

    def redo(self):
        self._apply(self._old_ref, self._new_ref, self._new_val)

    def undo(self):
        self._apply(self._new_ref, self._old_ref, self._old_val)

    def _apply(self, from_ref: str, to_ref: str, value: str):
        self._item.comp.ref = to_ref
        self._item.comp.value = value
        # Update comp_items dict
        self._view._comp_items.pop(from_ref, None)
        self._view._comp_items[to_ref] = self._item
        # Update net references
        for net in self._view._spec.nets:
            for conn in net.connections:
                if conn.ref == from_ref:
                    conn.ref = to_ref
        self._item.setToolTip(f"{to_ref}: {value}\n{self._item.comp.description}")
        self._item.update()
        self._view._reroute_wires()
        self._view.circuit_modified.emit(self._view._spec)


class _AddWireCmd(QUndoCommand):
    def __init__(self, view: 'SchematicView', net_name: str,
                 conn_a: PinRef, conn_b: PinRef):
        super().__init__("Add Wire")
        self._view = view
        self._net_name = net_name
        self._a = conn_a
        self._b = conn_b

    def redo(self):
        # Find or create the net
        net = None
        for n in self._view._spec.nets:
            if n.name == self._net_name:
                net = n
                break
        if net is None:
            net = NetSpec(name=self._net_name, connections=[self._a, self._b])
            self._view._spec.nets.append(net)
        else:
            for c in [self._a, self._b]:
                if not any(x.ref == c.ref and x.pin == c.pin for x in net.connections):
                    net.connections.append(c)
        self._view._reroute_wires()
        self._view.circuit_modified.emit(self._view._spec)

    def undo(self):
        for net in self._view._spec.nets:
            if net.name == self._net_name:
                net.connections = [
                    c for c in net.connections
                    if not (c.ref == self._a.ref and c.pin == self._a.pin)
                    and not (c.ref == self._b.ref and c.pin == self._b.pin)
                ]
                break
        self._view._spec.nets = [n for n in self._view._spec.nets if len(n.connections) >= 2]
        self._view._reroute_wires()
        self._view.circuit_modified.emit(self._view._spec)


# =====================================================================
# Component Edit Dialog
# =====================================================================

class _CompEditDialog(QDialog):
    """Small dialog for editing component ref and value."""

    def __init__(self, comp: ComponentSpec, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("edit_component_title"))
        self.setStyleSheet(
            "QDialog { background: #161b22; }"
            "QLabel { color: #e6edf3; }"
            "QLineEdit { background: #0d1117; border: 1px solid #30363d; "
            "border-radius: 4px; padding: 4px; color: #e6edf3; }"
            "QPushButton { background: #238636; color: white; border: none; "
            "border-radius: 4px; padding: 5px 16px; }"
            "QPushButton:hover { background: #2ea043; }"
            "QPushButton#cancel { background: #21262d; }"
        )

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.ref_edit = QLineEdit(comp.ref)
        self.val_edit = QLineEdit(comp.value)
        form.addRow(tr("edit_ref_label"), self.ref_edit)
        form.addRow(tr("edit_value_label"), self.val_edit)
        layout.addLayout(form)

        btns = QHBoxLayout()
        ok = QPushButton(tr("button_save"))
        ok.clicked.connect(self.accept)
        cancel = QPushButton(tr("button_cancel"))
        cancel.setObjectName("cancel")
        cancel.clicked.connect(self.reject)
        btns.addStretch()
        btns.addWidget(cancel)
        btns.addWidget(ok)
        layout.addLayout(btns)


# =====================================================================
# SchematicView — Interactive Editor
# =====================================================================

class SchematicView(QGraphicsView):
    """Schematic editor with drag-and-drop, wire drawing, undo/redo."""

    circuit_modified = Signal(object)  # emits CircuitSpec

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QBrush(_PAL["bg"]))
        self.setMinimumSize(400, 300)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setAcceptDrops(True)

        self._comp_items: dict[str, ComponentItem] = {}
        self._zoom = 1.0
        self._spec: CircuitSpec | None = None
        self._interactive = True

        # Undo / Redo
        self._undo_stack = QUndoStack(self)

        # Wire drawing state
        self._wire_mode = False
        self._wire_start_ref: str | None = None
        self._wire_start_pin: PinSpec | None = None
        self._wire_start_pos: QPointF | None = None
        self._wire_rubber: QGraphicsItem | None = None

        # Reroute debounce
        self._reroute_pending = False
        self._ref_counter: dict[str, int] = {}  # ref_prefix → next number

        # Theme
        ThemeManager.instance().theme_changed.connect(self._apply_theme)

    @property
    def undo_stack(self) -> QUndoStack:
        return self._undo_stack

    def _apply_theme(self):
        global _PAL
        _PAL = _pal()
        self.setBackgroundBrush(QBrush(_PAL["bg"]))
        self.viewport().update()

    # ==================================================================
    # Load circuit (from AI or file)
    # ==================================================================

    def load_circuit(self, spec: CircuitSpec):
        self._undo_stack.clear()
        self._scene.clear()
        self._comp_items.clear()
        self._spec = spec.model_copy(deep=True)
        self._update_ref_counter()

        if not spec.components:
            return

        layout = _grid_layout(spec)

        for comp in self._spec.components:
            item = ComponentItem(comp)
            x, y = layout.get(comp.ref, (0, 0))
            item.setPos(x, y)
            self._scene.addItem(item)
            self._comp_items[comp.ref] = item

        _route_nets(self._spec, self._comp_items, self._scene)

        rect = self._scene.itemsBoundingRect().adjusted(-100, -100, 100, 100)
        self._scene.setSceneRect(rect)
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

    def _update_ref_counter(self):
        """Rebuild ref counter from current spec."""
        self._ref_counter.clear()
        if not self._spec:
            return
        for comp in self._spec.components:
            prefix = ""
            num_str = ""
            for ch in comp.ref:
                if ch.isdigit():
                    num_str += ch
                else:
                    if num_str:
                        break
                    prefix += ch
            n = int(num_str) if num_str else 0
            self._ref_counter[prefix] = max(self._ref_counter.get(prefix, 0), n)

    def _next_ref(self, prefix: str) -> str:
        n = self._ref_counter.get(prefix, 0) + 1
        self._ref_counter[prefix] = n
        return f"{prefix}{n}"

    # ==================================================================
    # Wire Drawing Mode
    # ==================================================================

    def set_wire_mode(self, on: bool):
        self._wire_mode = on
        if on:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self._cancel_wire()

    def _cancel_wire(self):
        if self._wire_rubber:
            self._scene.removeItem(self._wire_rubber)
            self._wire_rubber = None
        self._wire_start_ref = None
        self._wire_start_pin = None
        self._wire_start_pos = None

    def _find_pin_at(self, scene_pos: QPointF) -> tuple[ComponentItem | None, PinSpec | None]:
        """Find the component + pin nearest to scene_pos."""
        for ref, item in self._comp_items.items():
            pin = item.pin_at_scene_pos(scene_pos, radius=12.0)
            if pin is not None:
                return item, pin
        return None, None

    # ==================================================================
    # Mouse Events
    # ==================================================================

    def mousePressEvent(self, event):
        if self._wire_mode and event.button() == Qt.MouseButton.LeftButton:
            sp = self.mapToScene(event.pos())
            item, pin = self._find_pin_at(sp)
            if item and pin:
                if self._wire_start_pin is None:
                    # Start wire
                    self._wire_start_ref = item.comp.ref
                    self._wire_start_pin = pin
                    self._wire_start_pos = item.get_pin_pos(pin.number)
                else:
                    # End wire
                    if item.comp.ref != self._wire_start_ref or pin.number != self._wire_start_pin.number:
                        self._finish_wire(item, pin)
                    self._cancel_wire()
            else:
                self._cancel_wire()
            event.accept()
            return
        # Right-click cancels wire mode
        if self._wire_mode and event.button() == Qt.MouseButton.RightButton:
            self._cancel_wire()
            self.set_wire_mode(False)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._wire_mode and self._wire_start_pos:
            sp = self.mapToScene(event.pos())
            if self._wire_rubber:
                self._scene.removeItem(self._wire_rubber)
            pen = QPen(_PAL["wire"], 1.5, Qt.PenStyle.DashLine)
            path = QPainterPath(self._wire_start_pos)
            # L-route preview
            path.lineTo(QPointF(sp.x(), self._wire_start_pos.y()))
            path.lineTo(sp)
            self._wire_rubber = self._scene.addPath(path, pen)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def _finish_wire(self, end_item: ComponentItem, end_pin: PinSpec):
        """Create a net/connection between two pins."""
        if not self._spec:
            return
        a_ref = self._wire_start_ref
        a_pin = self._wire_start_pin.number
        b_ref = end_item.comp.ref
        b_pin = end_pin.number

        conn_a = PinRef(ref=a_ref, pin=a_pin)
        conn_b = PinRef(ref=b_ref, pin=b_pin)

        # Find existing net for either pin
        net_name = None
        for net in self._spec.nets:
            for c in net.connections:
                if (c.ref == a_ref and c.pin == a_pin) or \
                   (c.ref == b_ref and c.pin == b_pin):
                    net_name = net.name
                    break
            if net_name:
                break

        if not net_name:
            # Generate new net name
            existing = {n.name for n in self._spec.nets}
            idx = 1
            while f"NET{idx}" in existing:
                idx += 1
            net_name = f"NET{idx}"

        self._undo_stack.push(_AddWireCmd(self, net_name, conn_a, conn_b))

    # ==================================================================
    # Keyboard Events
    # ==================================================================

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete or event.key() == Qt.Key.Key_Backspace:
            self.delete_selected()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            if self._wire_mode:
                self._cancel_wire()
                self.set_wire_mode(False)
            event.accept()
            return
        super().keyPressEvent(event)

    def _delete_selected(self):
        """Delete all selected components."""
        for item in list(self._scene.selectedItems()):
            if isinstance(item, ComponentItem):
                self._undo_stack.push(_DeleteComponentCmd(self, item))

    def delete_selected(self):
        """Public API for deleting selected components."""
        self._delete_selected()

    # ==================================================================
    # Drag & Drop (from ComponentPalette)
    # ==================================================================

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(MIME_TYPE):
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(MIME_TYPE):
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if not event.mimeData().hasFormat(MIME_TYPE):
            super().dropEvent(event)
            return
        if not self._spec:
            self._spec = CircuitSpec(name="Manual Design")

        raw = bytes(event.mimeData().data(MIME_TYPE)).decode("utf-8")
        data = json.loads(raw)
        drop_pos = self.mapToScene(event.pos())

        # Build ComponentSpec from palette data
        ref = self._next_ref(data.get("ref_prefix", "X"))
        pins_data = data.get("pins", [])
        pins = [PinSpec(number=p["number"], name=p.get("name", ""),
                        electrical_type=p.get("electrical_type", "passive"))
                for p in pins_data]
        comp = ComponentSpec(
            ref=ref,
            value=data.get("value", ""),
            category=ComponentCategory(data.get("category", "other")),
            package=data.get("package", ""),
            description=data.get("description", ""),
            pins=pins,
        )

        self._undo_stack.push(_AddComponentCmd(self, comp, drop_pos))
        event.acceptProposedAction()

    # ==================================================================
    # Component Editing
    # ==================================================================

    def _edit_component(self, item: ComponentItem):
        """Show edit dialog for component ref/value."""
        dlg = _CompEditDialog(item.comp, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_ref = dlg.ref_edit.text().strip()
            new_val = dlg.val_edit.text().strip()
            if new_ref and new_val and (new_ref != item.comp.ref or new_val != item.comp.value):
                self._undo_stack.push(
                    _EditComponentCmd(self, item,
                                      item.comp.ref, item.comp.value,
                                      new_ref, new_val)
                )

    # ==================================================================
    # Wire Re-routing
    # ==================================================================

    def _schedule_reroute(self):
        """Debounced reroute — called during drag."""
        if not self._reroute_pending:
            self._reroute_pending = True
            from PySide6.QtCore import QTimer
            QTimer.singleShot(50, self._do_reroute)

    def _do_reroute(self):
        self._reroute_pending = False
        self._reroute_wires()

    def _reroute_wires(self):
        """Remove all wire/junction/label items and re-route."""
        for item in list(self._scene.items()):
            if not isinstance(item, ComponentItem):
                self._scene.removeItem(item)
        if self._spec:
            _route_nets(self._spec, self._comp_items, self._scene)

    def _push_move_cmd(self, item: ComponentItem, old_pos: QPointF, new_pos: QPointF):
        """Push a move command onto the undo stack (called from ComponentItem)."""
        self._undo_stack.push(_MoveComponentCmd(self, item, old_pos, new_pos))

    # ==================================================================
    # Helpers
    # ==================================================================

    def highlight_component(self, ref: str):
        """Select and center on a specific component (used by AI Co-Pilot)."""
        item = self._comp_items.get(ref)
        if item:
            self._scene.clearSelection()
            item.setSelected(True)
            self.centerOn(item)

    def get_spec(self) -> CircuitSpec | None:
        return self._spec

    def wheelEvent(self, event: QWheelEvent):
        f = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self._zoom = max(0.1, min(10.0, self._zoom * f))
        self.scale(f, f)
