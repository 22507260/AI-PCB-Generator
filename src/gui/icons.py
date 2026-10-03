"""Theme-aware line icons for the engineering toolbar."""

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF

from src.gui.theme import tc


def workspace_icon(name):
    pixmap = QPixmap(24, 24)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(
        QPen(
            QColor(tc().text),
            1.6,
            Qt.PenStyle.SolidLine,
            Qt.PenCapStyle.RoundCap,
            Qt.PenJoinStyle.RoundJoin,
        )
    )

    def line(x, y, u, v):
        p.drawLine(QPointF(x, y), QPointF(u, v))

    def poly(points):
        p.drawPolyline(QPolygonF([QPointF(x, y) for x, y in points]))

    if name == "new":
        poly([(6, 21), (6, 3), (14, 3), (19, 8), (19, 21), (6, 21)])
        poly([(14, 3), (14, 8), (19, 8)])
    elif name == "open":
        poly([(3, 19), (3, 6), (10, 6), (12, 9), (21, 9), (21, 19), (3, 19)])
        line(3, 12, 21, 12)
    elif name == "save":
        poly([(4, 4), (18, 4), (21, 7), (21, 21), (4, 21), (4, 4)])
        p.drawRect(8, 4, 8, 6)
        p.drawRect(8, 14, 9, 7)
    elif name == "export":
        poly([(10, 4), (4, 4), (4, 20), (18, 20), (18, 15)])
        poly([(13, 3), (21, 3), (21, 11)])
        line(10, 14, 21, 3)
    elif name == "manufacture":
        p.drawRect(6, 6, 12, 12)
        for a in (9, 15):
            line(a, 2, a, 6)
            line(a, 18, a, 22)
            line(2, a, 6, a)
            line(18, a, 22, a)
        p.drawRect(9, 9, 6, 6)
    elif name == "settings":
        for x, y in ((5, 8), (12, 16), (19, 10)):
            line(x, 3, x, y - 2)
            line(x, y + 2, x, 21)
            p.drawEllipse(QPointF(x, y), 2, 2)
    elif name == "wire":
        poly([(5, 17), (12, 17), (12, 7), (19, 7)])
        p.drawEllipse(QPointF(4, 17), 2, 2)
        p.drawEllipse(QPointF(20, 7), 2, 2)
    p.end()
    return QIcon(pixmap)
