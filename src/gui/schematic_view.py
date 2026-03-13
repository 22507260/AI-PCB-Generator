"""Schematic viewer — grid-based layout with orthogonal wire routing."""

from __future__ import annotations

import math
import heapq
from collections import defaultdict
from typing import Optional

from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsItem
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QWheelEvent,
    QPainterPath, QLinearGradient,
)

from src.ai.schemas import CircuitSpec, ComponentSpec, NetSpec

# ── Palette ──
_PAL = {
    "bg":         QColor("#0d1117"),
    "wire":       QColor("#3fb950"),
    "wire_pwr":   QColor("#f0883e"),
    "wire_gnd":   QColor("#58a6ff"),
    "text":       QColor("#e6edf3"),
    "text_dim":   QColor("#7a848e"),
    "pin_dot":    QColor("#58a6ff"),
    "selected":   QColor("#ffa657"),
    "junction":   QColor("#3fb950"),
}

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
        self.setToolTip(f"{comp.ref}: {comp.value}\n{comp.description}")

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

_GRID_CELL = 10  # px per routing grid cell

_BLOCKED = -1
_FREE = 0
# Cost weights
_STRAIGHT_COST = 1
_BEND_COST = 4       # discourage unnecessary bends
_NEAR_WIRE_COST = 2  # discourage running next to existing wires


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
        """Mark cell as occupied by a routed wire (not blocked, but has cost)."""
        if 0 <= r < self.rows and 0 <= c < self.cols:
            if self._cells[r][c] == _FREE:
                self._cells[r][c] = 1  # wire present

    def has_wire(self, r: int, c: int) -> bool:
        if 0 <= r < self.rows and 0 <= c < self.cols:
            return self._cells[r][c] > 0
        return False

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
            # Penalize running next to existing wires
            if grid.has_wire(nr, nc):
                move_cost += _NEAR_WIRE_COST

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
    rect = scene.itemsBoundingRect().adjusted(-80, -80, 80, 80)
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
                # Fallback: simple L-route if maze fails
                mx = (p1.x() + p2.x()) / 2
                fallback = QPainterPath(p1)
                fallback.lineTo(QPointF(mx, p1.y()))
                fallback.lineTo(QPointF(mx, p2.y()))
                fallback.lineTo(p2)
                scene.addPath(fallback, pen)
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
# SchematicView
# =====================================================================

class SchematicView(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QBrush(_PAL["bg"]))
        self.setMinimumSize(400, 300)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self._comp_items: dict[str, ComponentItem] = {}
        self._zoom = 1.0

    def load_circuit(self, spec: CircuitSpec):
        self._scene.clear()
        self._comp_items.clear()
        if not spec.components:
            return

        layout = _grid_layout(spec)

        # Place component items
        for comp in spec.components:
            item = ComponentItem(comp)
            x, y = layout.get(comp.ref, (0, 0))
            item.setPos(x, y)
            self._scene.addItem(item)
            self._comp_items[comp.ref] = item

        # ── Route wires (maze router) ──
        _route_nets(spec, self._comp_items, self._scene)

        # ── Fit view ──
        rect = self._scene.itemsBoundingRect().adjusted(-100, -100, 100, 100)
        self._scene.setSceneRect(rect)
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

    def wheelEvent(self, event: QWheelEvent):
        f = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self._zoom = max(0.1, min(10.0, self._zoom * f))
        self.scale(f, f)
