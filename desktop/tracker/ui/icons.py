"""Векторные иконки одного стиля: контур 1.8 px на сетке 24×24, скруглённые концы.

Рисуются QPainter'ом в нужном цвете, поэтому сами подстраиваются под светлую/тёмную тему.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def _path(name: str) -> tuple[QPainterPath, QPainterPath | None]:
    """Возвращает (контур, заливка) в координатах 24×24."""
    p = QPainterPath()
    fill = None
    if name == "home":
        p.moveTo(3.5, 11); p.lineTo(12, 4); p.lineTo(20.5, 11)
        p.moveTo(6, 9.5); p.lineTo(6, 20); p.lineTo(18, 20); p.lineTo(18, 9.5)
        p.moveTo(10, 20); p.lineTo(10, 14.5); p.lineTo(14, 14.5); p.lineTo(14, 20)
    elif name == "habits":  # сетка дней с отмеченными клетками
        fill = QPainterPath()
        for r in range(3):
            for c in range(3):
                rect = QRectF(4 + c * 5.8, 4 + r * 5.8, 4.4, 4.4)
                if (r, c) in {(0, 0), (0, 1), (1, 1), (2, 0), (2, 1), (2, 2), (1, 2)}:
                    fill.addRoundedRect(rect, 1.2, 1.2)
                else:
                    p.addRoundedRect(rect, 1.2, 1.2)
    elif name == "tasks":
        for i, y in enumerate((6, 12, 18)):
            p.addRoundedRect(QRectF(3.5, y - 2.2, 4.4, 4.4), 1.2, 1.2)
            p.moveTo(11, y); p.lineTo(20.5, y)
        p.moveTo(4.4, 6); p.lineTo(5.4, 7); p.lineTo(7.2, 4.8)
    elif name == "goals":  # флажок на вершине
        p.moveTo(6, 21); p.lineTo(6, 3.5)
        p.moveTo(6, 4.5); p.lineTo(18.5, 4.5); p.lineTo(15.5, 8.5); p.lineTo(18.5, 12.5); p.lineTo(6, 12.5)
    elif name == "notes":
        p.moveTo(14.5, 3.5); p.lineTo(6.5, 3.5); p.quadTo(5, 3.5, 5, 5)
        p.lineTo(5, 19); p.quadTo(5, 20.5, 6.5, 20.5); p.lineTo(17.5, 20.5); p.quadTo(19, 20.5, 19, 19)
        p.lineTo(19, 8); p.lineTo(14.5, 3.5); p.lineTo(14.5, 8); p.lineTo(19, 8)
        p.moveTo(8.5, 12.5); p.lineTo(15.5, 12.5); p.moveTo(8.5, 16); p.lineTo(13.5, 16)
    elif name == "stats":
        p.moveTo(4, 20.5); p.lineTo(20.5, 20.5)
        for x, top in ((6.5, 13), (11, 7), (15.5, 10.5)):
            p.addRoundedRect(QRectF(x, top, 3, 20.5 - top - 2), 1, 1)
    elif name == "plus":
        p.moveTo(12, 5); p.lineTo(12, 19); p.moveTo(5, 12); p.lineTo(19, 12)
    elif name == "more":
        fill = QPainterPath()
        for x in (6, 12, 18):
            fill.addEllipse(QPointF(x, 12), 1.7, 1.7)
    elif name == "pin":
        p.moveTo(9, 4); p.lineTo(15, 4); p.moveTo(10, 4); p.lineTo(10, 10); p.lineTo(7, 14)
        p.lineTo(17, 14); p.lineTo(14, 10); p.lineTo(14, 4); p.moveTo(12, 14); p.lineTo(12, 20.5)
    elif name == "trash":
        p.moveTo(4.5, 6.5); p.lineTo(19.5, 6.5); p.moveTo(9.5, 6.5); p.lineTo(9.5, 4); p.lineTo(14.5, 4)
        p.lineTo(14.5, 6.5); p.moveTo(6.5, 6.5); p.lineTo(7.5, 20); p.lineTo(16.5, 20); p.lineTo(17.5, 6.5)
    elif name == "search":
        p.addEllipse(QPointF(10.5, 10.5), 6, 6); p.moveTo(15, 15); p.lineTo(20, 20)
    elif name == "check":
        p.moveTo(5.5, 12.5); p.lineTo(10, 17); p.lineTo(18.5, 7.5)
    elif name == "tag":
        p.moveTo(3.5, 4.5); p.lineTo(3.5, 11.5); p.lineTo(12.5, 20.5); p.lineTo(20.5, 12.5)
        p.lineTo(11.5, 3.5); p.lineTo(4.5, 3.5)
        fill = QPainterPath(); fill.addEllipse(QPointF(8, 8), 1.6, 1.6)
    elif name == "archive":
        p.addRoundedRect(QRectF(3.5, 4, 17, 4.5), 1, 1)
        p.moveTo(5, 8.5); p.lineTo(5, 19.5); p.lineTo(19, 19.5); p.lineTo(19, 8.5)
        p.moveTo(10, 12); p.lineTo(14, 12)
    elif name == "settings":  # шестерёнка
        import math
        p.addEllipse(QPointF(12, 12), 3, 3)
        for i in range(8):
            a = math.radians(i * 45)
            p.moveTo(12 + 6.2 * math.cos(a), 12 + 6.2 * math.sin(a))
            p.lineTo(12 + 8.8 * math.cos(a), 12 + 8.8 * math.sin(a))
        p.addEllipse(QPointF(12, 12), 6.2, 6.2)
    elif name == "calendar":
        p.addRoundedRect(QRectF(3.5, 5, 17, 15.5), 2.5, 2.5)
        p.moveTo(3.5, 9.5); p.lineTo(20.5, 9.5)
        p.moveTo(8, 3); p.lineTo(8, 6.5); p.moveTo(16, 3); p.lineTo(16, 6.5)
        fill = QPainterPath()
        for x, y in ((8, 13.5), (12, 13.5), (16, 13.5), (8, 17), (12, 17)):
            fill.addRoundedRect(QRectF(x - 1.3, y - 1.3, 2.6, 2.6), 0.6, 0.6)
    elif name == "chevron-left":
        p.moveTo(14.5, 6); p.lineTo(8.5, 12); p.lineTo(14.5, 18)
    elif name == "chevron-down":
        p.moveTo(7, 10); p.lineTo(12, 15); p.lineTo(17, 10)
    elif name == "chevron-right":
        p.moveTo(9.5, 6); p.lineTo(15.5, 12); p.lineTo(9.5, 18)
    elif name == "folder":
        p.moveTo(3.5, 7); p.quadTo(3.5, 5, 5.5, 5); p.lineTo(9.5, 5); p.lineTo(11.5, 7.5)
        p.lineTo(18.5, 7.5); p.quadTo(20.5, 7.5, 20.5, 9.5); p.lineTo(20.5, 17.5)
        p.quadTo(20.5, 19.5, 18.5, 19.5); p.lineTo(5.5, 19.5); p.quadTo(3.5, 19.5, 3.5, 17.5)
        p.lineTo(3.5, 7)
    elif name == "coin":
        p.addEllipse(QPointF(12, 12), 8, 8)
        p.moveTo(10, 16.5); p.lineTo(10, 7.5); p.lineTo(13.2, 7.5); p.quadTo(15.6, 7.5, 15.6, 10)
        p.quadTo(15.6, 12.5, 13.2, 12.5); p.lineTo(8.5, 12.5); p.moveTo(8.5, 14.5); p.lineTo(13, 14.5)
    elif name == "lock":
        p.addRoundedRect(QRectF(5, 10.5, 14, 10), 1.5, 1.5)
        p.moveTo(8, 10.5); p.lineTo(8, 7.5); p.arcTo(QRectF(8, 3.5, 8, 8), 180, -180); p.lineTo(16, 10.5)
    elif name == "edit":
        p.moveTo(4, 20); p.lineTo(4.8, 16); p.lineTo(15.5, 5.3); p.lineTo(18.7, 8.5)
        p.lineTo(8, 19.2); p.lineTo(4, 20)
    return p, fill


def pixmap(name: str, color: QColor | str, size: int = 20, ratio: float = 2.0) -> QPixmap:
    color = QColor(color)
    pm = QPixmap(int(size * ratio), int(size * ratio))
    pm.setDevicePixelRatio(ratio)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(size / 24.0, size / 24.0)
    stroke, fill = _path(name)
    pen = QPen(color, 1.8)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(stroke)
    if fill is not None:
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawPath(fill)
    painter.end()
    return pm


def icon(name: str, color: QColor | str, selected: QColor | str | None = None,
         size: int = 20) -> QIcon:
    ic = QIcon()
    ic.addPixmap(pixmap(name, color, size), QIcon.Normal)
    if selected is not None:
        ic.addPixmap(pixmap(name, selected, size), QIcon.Selected)
    return ic
