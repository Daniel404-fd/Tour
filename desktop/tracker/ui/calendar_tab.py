"""Календарь в духе Google Календаря: день / неделя / месяц, свои календари, повторы,
создание выделением, перетаскивание и растягивание событий, сроки задач."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from PySide6.QtCore import QDate, QPointF, QRectF, QSize, Qt, QTime, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout,
    QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu, QMessageBox, QPlainTextEdit, QPushButton,
    QRadioButton, QScrollArea, QSizePolicy, QSpinBox, QTimeEdit, QVBoxLayout, QWidget,
)

from .. import cal, logic
from ..cal import EVENT_COLORS, CalendarInfo, Event, Occurrence
from ..db import Database
from . import widgets as w
from .theme import theme

HOUR_H = 48            # высота часа в сетке по умолчанию, px
ZOOM_STEPS = [24, 32, 40, 48, 60, 76, 96, 120, 150]   # масштабы сетки (высота часа)
GUTTER = 62            # колонка с часами
SNAP_MIN = 15
MONTHS = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь",
          "Октябрь", "Ноябрь", "Декабрь"]
WD = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
VIEWS = [("day", "День"), ("week", "Неделя"), ("month", "Месяц")]


def _hm(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def _small_font(base: QFont, pt: float, bold: bool = False) -> QFont:
    f = QFont(base)
    f.setPointSizeF(pt)
    f.setBold(bold)
    return f


class Item:
    """То, что рисуется в календаре: вхождение события или срок задачи."""

    def __init__(self, occ: Occurrence | None = None, task: logic.Task | None = None,
                 color: str = "#455A64"):
        self.occ, self.task, self.color = occ, task, color

    @property
    def title(self) -> str:
        if self.task:
            return self.task.title
        return self.occ.event.title or "(без названия)"

    @property
    def all_day(self) -> bool:
        return self.task is not None or self.occ.event.all_day


# ====================================================================== сетка часов

class TimeGrid(QWidget):
    """Сетка 24 часа × N дней с событиями. Создание — протянуть мышью по пустому месту;
    перенос — перетащить событие; длительность — потянуть за нижний край."""

    itemClicked = Signal(object)                      # Item
    createRequested = Signal(object, object, bool)    # start, end, all_day
    changeRequested = Signal(object, object, object)  # Occurrence, new start, new end

    def __init__(self):
        super().__init__()
        self.days: list[date] = []
        self.items: list[Item] = []
        self.hour_h = HOUR_H
        self.setMinimumHeight(24 * self.hour_h + 1)
        self.setMouseTracking(True)
        self.drag: dict | None = None
        self.hits: list[tuple[QRectF, Item]] = []

    def set_data(self, days: list[date], items: list[Item]) -> None:
        self.days = days
        self.items = [i for i in items if not i.all_day]
        self.update()

    # ---- геометрия ----
    def col_w(self) -> float:
        return (self.width() - GUTTER) / max(1, len(self.days))

    def pos_to(self, pos: QPointF) -> tuple[int, datetime]:
        di = int((pos.x() - GUTTER) // self.col_w())
        di = max(0, min(len(self.days) - 1, di))
        minutes = max(0, min(24 * 60 - SNAP_MIN, pos.y() / self.hour_h * 60))
        minutes = int(minutes // SNAP_MIN) * SNAP_MIN      # 15-минутная ячейка под курсором
        return di, datetime.combine(self.days[di], time.min) + timedelta(minutes=minutes)

    def _y(self, dt: datetime, day: date) -> float:
        h = (dt - datetime.combine(day, time.min)).total_seconds() / 3600
        return max(0.0, min(24.0, h)) * self.hour_h

    def _blocks(self):
        """(rect, item, day) для всех видимых частей событий с учётом пересечений."""
        out = []
        cw = self.col_w()
        for di, day in enumerate(self.days):
            ds = datetime.combine(day, time.min)
            de = ds + timedelta(days=1)
            todays = [i for i in self.items if i.occ.end > ds and i.occ.start < de
                      or (i.occ.start == i.occ.end and ds <= i.occ.start < de)]
            spans = [(self._y(i.occ.start, day) / self.hour_h, self._y(i.occ.end, day) / self.hour_h) for i in todays]
            for item, (col, n) in zip(todays, cal.layout_columns(spans)):
                y1 = self._y(item.occ.start, day)
                y2 = max(y1 + 20, self._y(item.occ.end, day))
                sub = (cw - 6) / n
                x = GUTTER + di * cw + 2 + col * sub
                # как в Google: пересекающиеся блоки шире своей доли и слегка налезают друг на друга
                width = sub - 2 if n == 1 else min(cw - 6 - col * sub, sub * 1.7)
                out.append((QRectF(x, y1 + 1, width, y2 - y1 - 2), item, day))
        return out

    # ---- отрисовка ----
    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cw = self.col_w()
        today = date.today()
        for di, day in enumerate(self.days):
            if day == today:
                p.fillRect(QRectF(GUTTER + di * cw, 0, cw, self.height()), theme.color("today_bg"))
        small = _small_font(self.font(), 8.5)
        p.setFont(small)
        for h in range(24):
            y = h * self.hour_h
            p.setPen(QPen(theme.color("border"), 1))
            p.drawLine(QPointF(GUTTER - 6, y + 0.5), QPointF(self.width(), y + 0.5))
            p.setPen(QPen(theme.color("border"), 1, Qt.DotLine))
            # чем крупнее масштаб, тем мельче деления: 30 мин, а с 96 px — каждые 15 мин
            parts = 4 if self.hour_h >= 96 else 2 if self.hour_h >= 32 else 1
            for k in range(1, parts):
                yy = y + self.hour_h * k / parts + 0.5
                p.drawLine(QPointF(GUTTER, yy), QPointF(self.width(), yy))
            if h:
                p.setPen(theme.color("text2"))
                p.drawText(QRectF(0, y - 8, GUTTER - 10, 16), Qt.AlignRight | Qt.AlignVCenter, f"{h:02d}:00")
        p.setPen(QPen(theme.color("border"), 1))
        for di in range(len(self.days) + 1):
            x = GUTTER + di * cw
            p.drawLine(QPointF(x + 0.5, 0), QPointF(x + 0.5, self.height()))

        self.hits = []
        dragging_occ = self.drag["item"].occ.key if self.drag and self.drag.get("moved") and self.drag.get("item") else None
        for rect, item, day in self._blocks():
            ghost = dragging_occ == item.occ.key
            self._draw_block(p, rect, item, alpha=0.35 if ghost else 1.0)
            self.hits.append((rect, item))

        # предпросмотр переноса / растягивания / создания
        if self.drag and self.drag.get("moved"):
            d = self.drag
            if d["mode"] in ("move", "resize"):
                s, e = d["new"]
                for di, day in enumerate(self.days):
                    ds = datetime.combine(day, time.min)
                    if e > ds and s < ds + timedelta(days=1):
                        y1, y2 = self._y(s, day), max(self._y(s, day) + 20, self._y(e, day))
                        r = QRectF(GUTTER + di * cw + 2, y1 + 1, cw - 6, y2 - y1 - 2)
                        self._draw_block(p, r, d["item"], times=(s, e))
            elif d["mode"] == "create":
                s, e = d["new"]
                di = self.days.index(s.date()) if s.date() in self.days else 0
                y1, y2 = self._y(s, s.date()), self._y(e, s.date()) if e.date() == s.date() else 24 * self.hour_h
                r = QRectF(GUTTER + di * cw + 2, y1 + 1, cw - 6, max(20, y2 - y1 - 2))
                c = theme.color("teal")
                c.setAlphaF(0.85)
                p.setPen(Qt.NoPen)
                p.setBrush(c)
                p.drawRoundedRect(r, 6, 6)
                p.setPen(QColor("#FFFFFF"))
                p.setFont(_small_font(self.font(), 9, True))
                p.drawText(r.adjusted(6, 3, -4, -2), Qt.AlignLeft | Qt.AlignTop,
                           f"(без названия)\n{_hm(s)}–{_hm(e)}")

        # линия «сейчас»
        now = datetime.now()
        if now.date() in self.days:
            di = self.days.index(now.date())
            y = self._y(now, now.date())
            p.setPen(QPen(theme.color("now"), 2))
            p.drawLine(QPointF(GUTTER + di * cw, y), QPointF(GUTTER + (di + 1) * cw, y))
            p.setBrush(theme.color("now"))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QPointF(GUTTER + di * cw, y), 5, 5)
        p.end()

    def _draw_block(self, p: QPainter, r: QRectF, item: Item, alpha: float = 1.0,
                    times: tuple | None = None) -> None:
        c = QColor(item.color)
        c.setAlphaF(alpha)
        p.setPen(QPen(theme.color("surface"), 1))
        p.setBrush(c)
        p.drawRoundedRect(r, 6, 6)
        s, e = times or (item.occ.start, item.occ.end)
        p.setPen(QColor(255, 255, 255, int(255 * max(alpha, 0.6))))
        inner = r.adjusted(6, 2, -4, -2)
        title_f = _small_font(self.font(), 9, True)
        small = _small_font(self.font(), 8.5)
        fm = QFontMetrics(title_f)
        if r.height() >= 36:
            p.setFont(title_f)
            p.drawText(QRectF(inner.left(), inner.top(), inner.width(), fm.height()),
                       Qt.AlignLeft | Qt.AlignVCenter, fm.elidedText(item.title, Qt.ElideRight, int(inner.width())))
            p.setFont(small)
            sub = f"{_hm(s)}–{_hm(e)}"
            if item.occ.event.location:
                sub += f", {item.occ.event.location}"
            p.drawText(QRectF(inner.left(), inner.top() + fm.height(), inner.width(), inner.height() - fm.height()),
                       Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, sub)
        else:
            p.setFont(small)
            text = f"{item.title}, {_hm(s)}"
            p.drawText(inner, Qt.AlignLeft | Qt.AlignVCenter,
                       QFontMetrics(small).elidedText(text, Qt.ElideRight, int(inner.width())))

    # ---- масштаб ----
    def set_hour_height(self, h: int) -> None:
        self.hour_h = h
        self.setMinimumHeight(24 * h + 1)
        self.setMaximumHeight(24 * h + 1)
        self.update()

    zoomRequested = Signal(int, float)   # шаг (+1/−1), y курсора — чтобы масштабировать «вокруг» него

    def wheelEvent(self, e) -> None:
        if e.modifiers() & Qt.ControlModifier:
            step = 1 if e.angleDelta().y() > 0 else -1
            self.zoomRequested.emit(step, e.position().y())
            e.accept()
        else:
            super().wheelEvent(e)

    # ---- мышь ----
    def _hit(self, pos: QPointF) -> tuple[QRectF, Item] | None:
        for rect, item in reversed(self.hits):
            if rect.contains(pos):
                return rect, item
        return None

    def mouseMoveEvent(self, e) -> None:
        pos = e.position()
        if not self.drag:
            h = self._hit(pos)
            if h and pos.y() > h[0].bottom() - 6:
                self.setCursor(Qt.SizeVerCursor)
            elif h:
                self.setCursor(Qt.PointingHandCursor)
            else:
                self.setCursor(Qt.ArrowCursor)
            return
        d = self.drag
        if not d["moved"] and (pos - d["press"]).manhattanLength() < 5:
            return
        d["moved"] = True
        di, dt = self.pos_to(pos)
        if d["mode"] == "create":
            a, b = sorted([d["anchor"], dt])
            d["new"] = (a, b + timedelta(minutes=SNAP_MIN))
        elif d["mode"] == "move":
            delta = dt - d["anchor"]
            o = d["item"].occ
            d["new"] = (o.start + delta, o.end + delta)
        elif d["mode"] == "resize":
            o = d["item"].occ
            end = max(o.start + timedelta(minutes=SNAP_MIN), dt + timedelta(minutes=SNAP_MIN))
            d["new"] = (o.start, end)
        self.update()

    def mousePressEvent(self, e) -> None:
        if e.button() != Qt.LeftButton or not self.days:
            return
        pos = e.position()
        h = self._hit(pos)
        _, dt = self.pos_to(pos)
        if h:
            rect, item = h
            mode = "resize" if pos.y() > rect.bottom() - 6 else "move"
            self.drag = {"mode": mode, "item": item, "press": pos, "anchor": dt, "moved": False,
                         "new": (item.occ.start, item.occ.end)}
        elif pos.x() > GUTTER:
            self.drag = {"mode": "create", "press": pos, "anchor": dt, "moved": False,
                         "new": (dt, dt + timedelta(hours=1))}

    def mouseReleaseEvent(self, e) -> None:
        d, self.drag = self.drag, None
        self.update()
        if not d:
            return
        if d["mode"] == "create":
            s, en = d["new"] if d["moved"] else (d["anchor"], d["anchor"] + timedelta(hours=1))
            self.createRequested.emit(s, en, False)
        elif not d["moved"]:
            self.itemClicked.emit(d["item"])
        else:
            s, en = d["new"]
            if (s, en) != (d["item"].occ.start, d["item"].occ.end):
                self.changeRequested.emit(d["item"].occ, s, en)


# ====================================================================== шапка и «весь день»

class DayHeader(QWidget):
    dayClicked = Signal(object)

    def __init__(self):
        super().__init__()
        self.days: list[date] = []
        self.setFixedHeight(54)
        self.setCursor(Qt.PointingHandCursor)

    def set_days(self, days: list[date]) -> None:
        self.days = days
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cw = (self.width() - GUTTER) / max(1, len(self.days))
        today = date.today()
        for i, d in enumerate(self.days):
            x = GUTTER + i * cw
            is_today = d == today
            p.setFont(_small_font(self.font(), 8.5, is_today))
            p.setPen(theme.color("teal" if is_today and not theme.dark else "link") if is_today
                     else theme.color("text2"))
            p.drawText(QRectF(x, 4, cw, 16), Qt.AlignHCenter, WD[d.weekday()].upper())
            circle = QRectF(x + cw / 2 - 15, 21, 30, 30)
            if is_today:
                p.setPen(Qt.NoPen)
                p.setBrush(theme.color("teal"))
                p.drawEllipse(circle)
                p.setPen(QColor("#FFFFFF"))
            else:
                p.setPen(theme.color("text"))
            p.setFont(_small_font(self.font(), 13, is_today))
            p.drawText(circle, Qt.AlignCenter, str(d.day))
        p.end()

    def mouseReleaseEvent(self, e) -> None:
        if not self.days:
            return
        cw = (self.width() - GUTTER) / len(self.days)
        i = int((e.position().x() - GUTTER) // cw)
        if 0 <= i < len(self.days):
            self.dayClicked.emit(self.days[i])


class AllDayBar(QWidget):
    """Полоса «весь день»: события на целый день и сроки задач."""

    itemClicked = Signal(object)
    createRequested = Signal(object, object, bool)
    MAX_ROWS = 4
    ROW = 22

    def __init__(self):
        super().__init__()
        self.days: list[date] = []
        self.per_day: list[list[Item]] = []
        self.hits: list[tuple[QRectF, Item]] = []

    def set_data(self, days: list[date], items: list[Item]) -> None:
        self.days = days
        self.per_day = []
        for d in days:
            ds = datetime.combine(d, time.min)
            de = ds + timedelta(days=1)
            day_items = [i for i in items if i.all_day and (
                (i.task and i.task.deadline == d) or (i.occ and i.occ.end > ds and i.occ.start < de))]
            self.per_day.append(day_items)
        rows = max([len(x) for x in self.per_day] + [1])
        self.setFixedHeight(max(34, 8 + min(rows, self.MAX_ROWS) * self.ROW))
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cw = (self.width() - GUTTER) / max(1, len(self.days))
        p.setPen(theme.color("text2"))
        p.setFont(_small_font(self.font(), 7.5))
        p.drawText(QRectF(2, 3, GUTTER - 10, 28), Qt.AlignRight | Qt.AlignTop | Qt.TextWordWrap, "весь\nдень")
        p.setPen(QPen(theme.color("border"), 1))
        p.drawLine(QPointF(0, self.height() - 0.5), QPointF(self.width(), self.height() - 0.5))
        self.hits = []
        font = _small_font(self.font(), 8.5, True)
        fm = QFontMetrics(font)
        for i, items in enumerate(self.per_day):
            x = GUTTER + i * cw
            for r_i, item in enumerate(items[: self.MAX_ROWS]):
                if r_i == self.MAX_ROWS - 1 and len(items) > self.MAX_ROWS:
                    p.setPen(theme.color("text2"))
                    p.setFont(_small_font(self.font(), 8.5))
                    p.drawText(QRectF(x + 6, 4 + r_i * self.ROW, cw - 8, self.ROW - 2), Qt.AlignVCenter,
                               f"ещё {len(items) - self.MAX_ROWS + 1}")
                    break
                r = QRectF(x + 2, 4 + r_i * self.ROW, cw - 5, self.ROW - 3)
                _draw_chip(p, r, item, font, fm)
                self.hits.append((r, item))
        p.end()

    def mouseReleaseEvent(self, e) -> None:
        pos = e.position()
        for r, item in self.hits:
            if r.contains(pos):
                self.itemClicked.emit(item)
                return

    def mouseDoubleClickEvent(self, e) -> None:
        if not self.days or e.position().x() < GUTTER:
            return
        cw = (self.width() - GUTTER) / len(self.days)
        d = self.days[min(len(self.days) - 1, int((e.position().x() - GUTTER) // cw))]
        s = datetime.combine(d, time.min)
        self.createRequested.emit(s, s + timedelta(days=1), True)


def _draw_chip(p: QPainter, r: QRectF, item: Item, font: QFont, fm: QFontMetrics,
               timed_label: bool = False) -> None:
    """Плашка события на целый день — заливка цветом; срок задачи — контур с «☐»;
    событие со временем в сетке месяца — цветная точка + время."""
    p.setFont(font)
    if item.task:
        p.setPen(QPen(theme.color("border_strong"), 1))
        p.setBrush(theme.color("surface"))
        p.drawRoundedRect(r, 5, 5)
        p.setPen(theme.color("text"))
        p.drawText(r.adjusted(6, 0, -4, 0), Qt.AlignVCenter,
                   fm.elidedText("☐ " + item.title, Qt.ElideRight, int(r.width() - 10)))
    elif timed_label and not item.occ.event.all_day:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(item.color))
        p.drawEllipse(QPointF(r.left() + 7, r.center().y()), 4, 4)
        p.setPen(theme.color("text"))
        text = f"{_hm(item.occ.start)} {item.title}"
        p.drawText(r.adjusted(15, 0, -2, 0), Qt.AlignVCenter,
                   fm.elidedText(text, Qt.ElideRight, int(r.width() - 17)))
    else:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(item.color))
        p.drawRoundedRect(r, 5, 5)
        p.setPen(QColor("#FFFFFF"))
        p.drawText(r.adjusted(6, 0, -4, 0), Qt.AlignVCenter,
                   fm.elidedText(item.title, Qt.ElideRight, int(r.width() - 10)))


# ====================================================================== месяц

class MonthView(QWidget):
    itemClicked = Signal(object)
    dayClicked = Signal(object)
    createRequested = Signal(object, object, bool)
    changeRequested = Signal(object, object, object)

    HEAD = 26
    ROW = 21

    def __init__(self):
        super().__init__()
        self.grid: list[list[date]] = []
        self.month = 1
        self.items: list[Item] = []
        self.hits: list[tuple[QRectF, object]] = []
        self.drag: dict | None = None
        self.setMouseTracking(True)

    def set_data(self, grid: list[list[date]], month: int, items: list[Item]) -> None:
        self.grid, self.month, self.items = grid, month, items
        self.update()

    def _cell(self, r: int, c: int) -> QRectF:
        cw = self.width() / 7
        ch = (self.height() - self.HEAD) / len(self.grid)
        return QRectF(c * cw, self.HEAD + r * ch, cw, ch)

    def _day_at(self, pos: QPointF) -> date | None:
        if pos.y() < self.HEAD or not self.grid:
            return None
        c = int(pos.x() // (self.width() / 7))
        r = int((pos.y() - self.HEAD) // ((self.height() - self.HEAD) / len(self.grid)))
        if 0 <= r < len(self.grid) and 0 <= c < 7:
            return self.grid[r][c]
        return None

    def _items_on(self, d: date) -> list[Item]:
        ds = datetime.combine(d, time.min)
        de = ds + timedelta(days=1)
        res = [i for i in self.items if (i.task and i.task.deadline == d) or (
            i.occ and (i.occ.end > ds and i.occ.start < de or (i.occ.start == i.occ.end and ds <= i.occ.start < de)))]
        return sorted(res, key=lambda i: (not i.all_day, i.occ.start if i.occ else ds, i.title))

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        today = date.today()
        cw = self.width() / 7
        p.setFont(_small_font(self.font(), 8.5, True))
        p.setPen(theme.color("text2"))
        for c in range(7):
            p.drawText(QRectF(c * cw, 0, cw, self.HEAD), Qt.AlignCenter, WD[c].upper())
        self.hits = []
        chip_font = _small_font(self.font(), 8.5)
        fm = QFontMetrics(chip_font)
        moving = self.drag["item"].occ.key if self.drag and self.drag.get("moved") else None
        target = self.drag.get("target") if self.drag and self.drag.get("moved") else None
        for r, week in enumerate(self.grid):
            for c, d in enumerate(week):
                cell = self._cell(r, c)
                if d == target:
                    p.fillRect(cell, theme.color("selection"))
                elif d == today:
                    p.fillRect(cell, theme.color("today_bg"))
                p.setPen(QPen(theme.color("border"), 1))
                p.setBrush(Qt.NoBrush)
                p.drawRect(cell.adjusted(0.5, 0.5, 0, 0))
                num = QRectF(cell.left() + cell.width() / 2 - 12, cell.top() + 3, 24, 22)
                if d == today:
                    p.setPen(Qt.NoPen)
                    p.setBrush(theme.color("teal"))
                    p.drawEllipse(num.adjusted(1, 0, -1, 0))
                    p.setPen(QColor("#FFFFFF"))
                else:
                    p.setPen(theme.color("text") if d.month == self.month else theme.color("text3"))
                p.setFont(_small_font(self.font(), 9, d == today))
                label = str(d.day) if d.day != 1 or d == today else f"1 {MONTHS[d.month - 1][:3].lower()}"
                if d.day == 1 and d != today:
                    num = QRectF(cell.left(), cell.top() + 3, cell.width(), 22)
                p.drawText(num, Qt.AlignCenter, label)
                self.hits.append((num, ("day", d)))
                items = self._items_on(d)
                rows = max(1, int((cell.height() - 30) // self.ROW))
                for k, item in enumerate(items):
                    y = cell.top() + 28 + k * self.ROW
                    if k == rows - 1 and len(items) > rows:
                        more = QRectF(cell.left() + 6, y, cell.width() - 10, self.ROW - 3)
                        p.setPen(theme.color("text2"))
                        p.setFont(chip_font)
                        p.drawText(more, Qt.AlignVCenter, f"ещё {len(items) - rows + 1}")
                        self.hits.append((more, ("day", d)))
                        break
                    rr = QRectF(cell.left() + 3, y, cell.width() - 6, self.ROW - 3)
                    if item.occ and moving == item.occ.key:
                        p.setOpacity(0.35)
                    _draw_chip(p, rr, item, chip_font, fm, timed_label=True)
                    p.setOpacity(1)
                    self.hits.append((rr, item))
        p.end()

    def _hit(self, pos):
        for rect, obj in reversed(self.hits):
            if rect.contains(pos):
                return obj
        return None

    def mousePressEvent(self, e) -> None:
        if e.button() != Qt.LeftButton:
            return
        obj = self._hit(e.position())
        if isinstance(obj, Item) and obj.occ:
            self.drag = {"item": obj, "press": e.position(), "moved": False,
                         "origin": self._day_at(e.position())}

    def mouseMoveEvent(self, e) -> None:
        if not self.drag:
            obj = self._hit(e.position())
            self.setCursor(Qt.PointingHandCursor if obj is not None else Qt.ArrowCursor)
            return
        if not self.drag["moved"] and (e.position() - self.drag["press"]).manhattanLength() < 6:
            return
        self.drag["moved"] = True
        self.drag["target"] = self._day_at(e.position())
        self.update()

    def mouseReleaseEvent(self, e) -> None:
        d, self.drag = self.drag, None
        self.update()
        if d and d["moved"]:
            target = self._day_at(e.position())
            if target and d["origin"] and target != d["origin"]:
                o = d["item"].occ
                delta = timedelta(days=(target - d["origin"]).days)
                self.changeRequested.emit(o, o.start + delta, o.end + delta)
            return
        obj = self._hit(e.position())
        if isinstance(obj, Item):
            self.itemClicked.emit(obj)
        elif isinstance(obj, tuple):
            self.dayClicked.emit(obj[1])

    def mouseDoubleClickEvent(self, e) -> None:
        if self._hit(e.position()) is not None:
            return
        d = self._day_at(e.position())
        if d:
            s = datetime.combine(d, time.min)
            self.createRequested.emit(s, s + timedelta(days=1), True)


# ====================================================================== мини-календарь

class MiniMonth(QWidget):
    dateClicked = Signal(object)

    def __init__(self):
        super().__init__()
        self.shown = date.today().replace(day=1)
        self.selected: set[date] = set()
        self.setFixedHeight(214)
        self.setCursor(Qt.PointingHandCursor)

    def set_selection(self, days: list[date], anchor: date) -> None:
        self.selected = set(days)
        if not (self.shown.year == anchor.year and self.shown.month == anchor.month):
            self.shown = anchor.replace(day=1)
        self.update()

    def _geom(self):
        cw = self.width() / 7
        return cw, 26, 24, 26  # ширина клетки, высота заголовка, высота строки, отступ сетки

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        cw, head, rh, top = self._geom()
        p.setFont(_small_font(self.font(), 9.5, True))
        p.setPen(theme.color("text"))
        p.drawText(QRectF(4, 0, self.width() - 60, head), Qt.AlignVCenter,
                   f"{MONTHS[self.shown.month - 1]} {self.shown.year}")
        p.setPen(theme.color("text2"))
        p.drawText(QRectF(self.width() - 52, 0, 24, head), Qt.AlignCenter, "‹")
        p.drawText(QRectF(self.width() - 26, 0, 24, head), Qt.AlignCenter, "›")
        p.setFont(_small_font(self.font(), 7.5))
        for c in range(7):
            p.drawText(QRectF(c * cw, head, cw, 18), Qt.AlignCenter, WD[c])
        today = date.today()
        p.setFont(_small_font(self.font(), 8.5))
        for r, week in enumerate(cal.month_grid(self.shown.year, self.shown.month)):
            for c, d in enumerate(week):
                rect = QRectF(c * cw, head + 18 + r * rh, cw, rh)
                circle = QRectF(rect.center().x() - 11, rect.center().y() - 11, 22, 22)
                if d in self.selected:
                    p.setPen(Qt.NoPen)
                    p.setBrush(theme.color("teal_soft"))
                    p.drawRect(rect.adjusted(0, 1, 0, -1))
                if d == today:
                    p.setPen(Qt.NoPen)
                    p.setBrush(theme.color("teal"))
                    p.drawEllipse(circle)
                    p.setPen(QColor("#FFFFFF"))
                else:
                    p.setPen(theme.color("text") if d.month == self.shown.month else theme.color("text3"))
                p.drawText(rect, Qt.AlignCenter, str(d.day))
        p.end()

    def mouseReleaseEvent(self, e) -> None:
        cw, head, rh, top = self._geom()
        x, y = e.position().x(), e.position().y()
        if y < head:
            if x > self.width() - 52:
                step = 1 if x > self.width() - 26 else -1
                m = self.shown.month - 1 + step
                self.shown = date(self.shown.year + m // 12, m % 12 + 1, 1)
                self.update()
            return
        r = int((y - head - 18) // rh)
        c = int(x // cw)
        grid = cal.month_grid(self.shown.year, self.shown.month)
        if 0 <= r < 6 and 0 <= c < 7:
            self.dateClicked.emit(grid[r][c])


# ====================================================================== диалоги

class EventDialog(QDialog):
    """Создание и изменение события, как карточка события в Google."""

    DELETE = 2

    def __init__(self, parent, calendars: list[CalendarInfo], event: Event, is_new: bool):
        super().__init__(parent)
        self.setWindowTitle("Новое событие" if is_new else "Событие")
        self.setMinimumWidth(600)
        self.event = event
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 16)
        lay.setSpacing(10)

        self.title = QLineEdit(event.title)
        self.title.setPlaceholderText("Добавьте название")
        f = self.title.font(); f.setPointSize(14); self.title.setFont(f)
        self.title.setStyleSheet("font-size: 14pt; padding: 6px 8px;")
        lay.addWidget(self.title)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(10)
        self.all_day = QCheckBox("Весь день")
        self.all_day.setChecked(event.all_day)
        self.d1, self.t1, self.d2, self.t2 = QDateEdit(), QTimeEdit(), QDateEdit(), QTimeEdit()
        for d in (self.d1, self.d2):
            d.setCalendarPopup(True)
            d.setDisplayFormat("ddd, d MMMM yyyy")
            d.setMinimumWidth(190)
        for t in (self.t1, self.t2):
            t.setDisplayFormat("HH:mm")
        s, e = event.start, event.end
        if event.all_day:
            e = e - timedelta(days=1)
        self.d1.setDate(QDate(s.year, s.month, s.day)); self.t1.setTime(QTime(s.hour, s.minute))
        self.d2.setDate(QDate(e.year, e.month, e.day)); self.t2.setTime(QTime(e.hour, e.minute))
        row1 = QHBoxLayout(); row1.addWidget(self.d1); row1.addWidget(self.t1); row1.addStretch()
        row2 = QHBoxLayout(); row2.addWidget(self.d2); row2.addWidget(self.t2); row2.addStretch()
        form.addRow("Начало", row1)
        form.addRow("Окончание", row2)
        form.addRow("", self.all_day)
        self.all_day.toggled.connect(self._toggle_all_day)
        self.t1.timeChanged.connect(self._keep_duration)
        self.d1.dateChanged.connect(self._keep_duration)
        self._prev_start = self._start()

        # повтор
        self.freq = QComboBox()
        self.freq.setMinimumWidth(170)
        for k, v in cal.FREQ_NAMES.items():
            self.freq.addItem(v, k)
        self.freq.setCurrentIndex(max(0, self.freq.findData(event.freq)))
        self.interval = QSpinBox(); self.interval.setRange(1, 99); self.interval.setValue(event.interval)
        self.interval.setPrefix("раз в "); self.interval.setFixedWidth(110)
        self.until_on = QCheckBox("до")
        self.until = QDateEdit(); self.until.setCalendarPopup(True); self.until.setDisplayFormat("dd.MM.yyyy")
        u = event.until or (event.start.date() + timedelta(days=90))
        self.until.setDate(QDate(u.year, u.month, u.day))
        self.until_on.setChecked(event.until is not None)
        self.until.setEnabled(event.until is not None)
        self.until_on.toggled.connect(self.until.setEnabled)
        rep = QHBoxLayout()
        rep.addWidget(self.freq); rep.addWidget(self.interval); rep.addWidget(self.until_on)
        rep.addWidget(self.until); rep.addStretch()
        form.addRow("Повтор", rep)
        self.wd_row = QHBoxLayout()
        self.wd_buttons = []
        for i, n in enumerate(WD):
            b = QPushButton(n)
            b.setCheckable(True)
            b.setProperty("kind", "chip")
            b.setChecked(i in (event.weekdays or [event.start.weekday()]))
            b.setFixedWidth(44)
            self.wd_buttons.append(b)
            self.wd_row.addWidget(b)
        self.wd_row.addStretch()
        self.wd_label = QLabel("По дням")
        form.addRow(self.wd_label, self.wd_row)
        self.freq.currentIndexChanged.connect(self._update_repeat)

        self.calendar = QComboBox()
        for c in calendars:
            self.calendar.addItem(w.dot_icon(c.color), c.name, c.id)
        self.calendar.setCurrentIndex(max(0, self.calendar.findData(event.calendar_id)))
        self.color = QComboBox()
        self.color.addItem("Цвет календаря", None)
        for hex_, name in EVENT_COLORS:
            self.color.addItem(w.dot_icon(hex_), name, hex_)
        self.color.setCurrentIndex(max(0, self.color.findData(event.color)))
        crow = QHBoxLayout(); crow.addWidget(self.calendar, 1); crow.addWidget(self.color, 1)
        form.addRow("Календарь", crow)

        self.reminder = QComboBox()
        for v, n in cal.REMINDER_CHOICES:
            self.reminder.addItem(n, v)
        self.reminder.setCurrentIndex(max(0, self.reminder.findData(event.reminder)))
        form.addRow("Напоминание", self.reminder)
        self.location = QLineEdit(event.location)
        self.location.setPlaceholderText("Где — необязательно")
        form.addRow("Место", self.location)
        self.desc = QPlainTextEdit(event.description)
        self.desc.setPlaceholderText("Описание")
        self.desc.setFixedHeight(80)
        form.addRow("Описание", self.desc)
        lay.addLayout(form)
        self.error = w.label("", "danger")
        self.error.hide()
        lay.addWidget(self.error)

        bottom = QHBoxLayout()
        if not is_new:
            dele = w.button("Удалить", "danger", "trash")
            dele.clicked.connect(lambda: self.done(self.DELETE))
            bottom.addWidget(dele)
        bottom.addStretch()
        box = QDialogButtonBox()
        ok = box.addButton("Сохранить", QDialogButtonBox.AcceptRole)
        ok.setProperty("kind", "primary"); ok.setDefault(True)
        box.addButton("Отмена", QDialogButtonBox.RejectRole)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        bottom.addWidget(box)
        lay.addLayout(bottom)
        self._toggle_all_day(event.all_day)
        self._update_repeat()
        self.title.setFocus()

    def _start(self) -> datetime:
        d, t = self.d1.date(), self.t1.time()
        return datetime(d.year(), d.month(), d.day(), t.hour(), t.minute())

    def _end(self) -> datetime:
        d, t = self.d2.date(), self.t2.time()
        return datetime(d.year(), d.month(), d.day(), t.hour(), t.minute())

    def _keep_duration(self) -> None:
        """Сдвинули начало — окончание сдвигается следом, как в Google."""
        new = self._start()
        delta = new - self._prev_start
        self._prev_start = new
        if delta:
            e = self._end() + delta
            self.d2.blockSignals(True); self.t2.blockSignals(True)
            self.d2.setDate(QDate(e.year, e.month, e.day)); self.t2.setTime(QTime(e.hour, e.minute))
            self.d2.blockSignals(False); self.t2.blockSignals(False)

    def _toggle_all_day(self, on: bool) -> None:
        self.t1.setVisible(not on)
        self.t2.setVisible(not on)

    def _update_repeat(self) -> None:
        f = self.freq.currentData()
        self.interval.setVisible(bool(f))
        self.until_on.setVisible(bool(f))
        self.until.setVisible(bool(f))
        weekly = f == cal.FREQ_WEEKLY
        self.wd_label.setVisible(weekly)
        for b in self.wd_buttons:
            b.setVisible(weekly)
        self.interval.setSuffix({cal.FREQ_DAILY: " дн.", cal.FREQ_WEEKLY: " нед.",
                                 cal.FREQ_MONTHLY: " мес.", cal.FREQ_YEARLY: " г."}.get(f, ""))

    def accept(self) -> None:
        s, e = self._start(), self._end()
        if self.all_day.isChecked():
            s = datetime.combine(s.date(), time.min)
            e = datetime.combine(e.date(), time.min) + timedelta(days=1)
            if e <= s:
                return self._fail("Дата окончания раньше даты начала.")
        elif e < s:
            return self._fail("Окончание раньше начала.")
        ev = self.event
        ev.title = self.title.text().strip()
        ev.start, ev.end, ev.all_day = s, e, self.all_day.isChecked()
        ev.freq = self.freq.currentData()
        ev.interval = self.interval.value()
        ev.weekdays = [i for i, b in enumerate(self.wd_buttons) if b.isChecked()] if ev.freq == cal.FREQ_WEEKLY else []
        if ev.freq == cal.FREQ_WEEKLY and not ev.weekdays:
            ev.weekdays = [s.weekday()]
        qd = self.until.date()
        ev.until = date(qd.year(), qd.month(), qd.day()) if ev.freq and self.until_on.isChecked() else None
        ev.calendar_id = self.calendar.currentData()
        ev.color = self.color.currentData()
        ev.reminder = self.reminder.currentData()
        ev.location = self.location.text().strip()
        ev.description = self.desc.toPlainText().strip()
        super().accept()

    def _fail(self, text: str) -> None:
        self.error.setText(text)
        self.error.show()


class ScopeDialog(QDialog):
    """Для повторяющегося события: изменить только это, это и следующие, или все."""

    THIS, FOLLOWING, ALL = "this", "following", "all"

    def __init__(self, parent, action: str):
        super().__init__(parent)
        self.setWindowTitle("Повторяющееся событие")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 16)
        lay.setSpacing(8)
        lay.addWidget(w.label(f"{action} повторяющееся событие", "section"))
        self.opts = []
        for key, text in ((self.THIS, "Только это событие"), (self.FOLLOWING, "Это и последующие события"),
                          (self.ALL, "Все события")):
            rb = QRadioButton(text)
            rb.setProperty("key", key)
            self.opts.append(rb)
            lay.addWidget(rb)
        self.opts[0].setChecked(True)
        box = QDialogButtonBox()
        ok = box.addButton("ОК", QDialogButtonBox.AcceptRole)
        ok.setProperty("kind", "primary"); ok.setDefault(True)
        box.addButton("Отмена", QDialogButtonBox.RejectRole)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    def scope(self) -> str:
        return next(rb.property("key") for rb in self.opts if rb.isChecked())


class CalendarEditDialog(QDialog):
    def __init__(self, parent, info: CalendarInfo | None = None):
        super().__init__(parent)
        self.setWindowTitle("Календарь" if info else "Новый календарь")
        self.setMinimumWidth(380)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 16)
        lay.addWidget(w.label("Название", "secondary"))
        self.name = QLineEdit(info.name if info else "")
        self.name.setPlaceholderText("Например, «Работа», «Спорт», «Дни рождения»")
        lay.addWidget(self.name)
        lay.addWidget(w.label("Цвет", "secondary"))
        row = QHBoxLayout()
        self.group = QButtonGroup(self)
        cur = info.color if info else EVENT_COLORS[1][0]
        for hex_, nm in EVENT_COLORS:
            b = QPushButton()
            b.setCheckable(True)
            b.setFixedSize(28, 28)
            b.setToolTip(nm)
            b.setAccessibleName(nm)
            b.setProperty("hex", hex_)
            b.setStyleSheet(f"QPushButton {{ background: {hex_}; border-radius: 14px; border: 2px solid {hex_}; }}"
                            f"QPushButton:checked {{ border: 3px solid {theme['text']}; }}")
            b.setChecked(hex_ == cur)
            self.group.addButton(b)
            row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)
        box = QDialogButtonBox()
        ok = box.addButton("Сохранить", QDialogButtonBox.AcceptRole)
        ok.setProperty("kind", "primary"); ok.setDefault(True)
        box.addButton("Отмена", QDialogButtonBox.RejectRole)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    def accept(self) -> None:
        if self.name.text().strip():
            super().accept()
        else:
            self.name.setFocus()

    def values(self) -> tuple[str, str]:
        b = self.group.checkedButton()
        return self.name.text().strip(), b.property("hex") if b else EVENT_COLORS[0][0]


# ====================================================================== страница

class CalendarPage(w.Page):
    def __init__(self, db: Database, navigate):
        super().__init__("Календарь", scroll=False)
        self.db, self.navigate = db, navigate
        self.view = db.get_pref("cal_view", "week")
        self.anchor = date.today()
        self._scrolled = False

        today_btn = w.button("Сегодня")
        today_btn.clicked.connect(self.go_today)
        prev_b = w.button("", "ghost", "chevron-left", "Назад")
        prev_b.clicked.connect(lambda: self.shift(-1))
        next_b = w.button("", "ghost", "chevron-right", "Вперёд")
        next_b.clicked.connect(lambda: self.shift(1))
        for b in (prev_b, next_b):
            b.setFixedSize(34, 32)
        seg = QHBoxLayout()
        seg.setSpacing(0)
        self.view_group = QButtonGroup(self)
        for i, (key, name) in enumerate(VIEWS):
            b = QPushButton(name)
            b.setCheckable(True)
            b.setProperty("kind", "seg")
            b.setProperty("pos", "first" if i == 0 else ("last" if i == len(VIEWS) - 1 else "mid"))
            b.setProperty("key", key)
            b.setChecked(key == self.view)
            b.setToolTip(f"{name} ({'DWM'[i]})")
            b.setAutoDefault(False)
            self.view_group.addButton(b)
            seg.addWidget(b)
        self.view_group.buttonClicked.connect(lambda b: self.set_view(b.property("key")))
        seg_w = QWidget(); seg_w.setLayout(seg)
        create = w.button("Создать", "primary", "plus", "Новое событие (Ctrl+N)")
        create.clicked.connect(self.new_item)
        # масштаб сетки дня/недели: кнопки, Ctrl+колесо, Ctrl+= / Ctrl+- / Ctrl+0
        self.zoom_out = w.button("", "ghost", "minus", "Мельче (Ctrl+−, Ctrl+колесо)")
        self.zoom_in = w.button("", "ghost", "plus", "Крупнее (Ctrl+=, Ctrl+колесо)")
        self.zoom_out.setAccessibleName("Уменьшить масштаб")
        self.zoom_in.setAccessibleName("Увеличить масштаб")
        self.zoom_label = QPushButton("100%")
        self.zoom_label.setProperty("kind", "ghost")
        self.zoom_label.setToolTip("Обычный масштаб (Ctrl+0)")
        self.zoom_label.setFixedWidth(58)
        for b in (self.zoom_out, self.zoom_in):
            b.setFixedSize(32, 32)
        self.zoom_out.clicked.connect(lambda: self.zoom(-1))
        self.zoom_in.clicked.connect(lambda: self.zoom(1))
        self.zoom_label.clicked.connect(lambda: self.set_zoom(HOUR_H))
        zoom_row = QHBoxLayout(); zoom_row.setSpacing(0); zoom_row.setContentsMargins(0, 0, 0, 0)
        for b in (self.zoom_out, self.zoom_label, self.zoom_in):
            zoom_row.addWidget(b)
        self.zoom_box = QWidget(); self.zoom_box.setLayout(zoom_row)
        for x in (self.zoom_box, today_btn, prev_b, next_b, seg_w, create):
            self.header.add_action(x)

        body = QHBoxLayout()
        body.setSpacing(16)
        # ---- левая колонка ----
        left = QVBoxLayout()
        left.setSpacing(10)
        self.mini = MiniMonth()
        self.mini.dateClicked.connect(self.go_date)
        left.addWidget(self.mini)
        head = QHBoxLayout()
        head.addWidget(w.label("Мои календари", "section"))
        head.addStretch()
        add_cal = w.button("", "ghost", "plus", "Новый календарь")
        add_cal.setFixedSize(30, 28)
        add_cal.clicked.connect(self.add_calendar)
        head.addWidget(add_cal)
        left.addLayout(head)
        self.cal_box = QVBoxLayout()
        self.cal_box.setSpacing(4)
        left.addLayout(self.cal_box)
        left.addSpacing(6)
        self.show_tasks = QCheckBox("Сроки задач")
        self.show_tasks.setChecked(db.get_pref("cal_show_tasks", "1") == "1")
        self.show_tasks.toggled.connect(lambda on: (self.db.set_pref("cal_show_tasks", "1" if on else "0"),
                                                    self.refresh()))
        left.addWidget(self.show_tasks)
        left.addStretch()
        lw = QWidget(); lw.setLayout(left); lw.setFixedWidth(230)
        left.setContentsMargins(0, 0, 0, 0)
        body.addWidget(lw)

        # ---- правая часть: неделя/день или месяц ----
        self.panel = QFrame()
        self.panel.setObjectName("card")
        pl = QVBoxLayout(self.panel)
        pl.setContentsMargins(0, 6, 0, 0)
        pl.setSpacing(0)
        self.day_header = DayHeader()
        self.all_day_bar = AllDayBar()
        self.grid = TimeGrid()
        self.grid_scroll = QScrollArea()
        self.grid_scroll.setWidgetResizable(True)
        self.grid_scroll.setFrameShape(QFrame.NoFrame)
        self.grid_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.grid_scroll.setWidget(self.grid)
        self.month_view = MonthView()
        for wdg in (self.day_header, self.all_day_bar):
            wdg.setContentsMargins(0, 0, 10, 0)
        self.week_box = QWidget()
        wb = QVBoxLayout(self.week_box)
        wb.setContentsMargins(0, 0, 0, 0)
        wb.setSpacing(0)
        hdr = QHBoxLayout(); hdr.setContentsMargins(0, 0, 10, 0); hdr.addWidget(self.day_header)
        adb = QHBoxLayout(); adb.setContentsMargins(0, 0, 10, 0); adb.addWidget(self.all_day_bar)
        wb.addLayout(hdr)
        wb.addLayout(adb)
        wb.addWidget(self.grid_scroll, 1)
        pl.addWidget(self.week_box, 1)
        pl.addWidget(self.month_view, 1)
        body.addWidget(self.panel, 1)
        self.content.addLayout(body, 1)

        for v in (self.grid, self.all_day_bar, self.month_view):
            v.itemClicked.connect(self.open_item)
            v.createRequested.connect(self.create_at)
        self.grid.changeRequested.connect(self.change_occurrence)
        self.grid.zoomRequested.connect(self.zoom)
        for seq, step in (("Ctrl+=", 1), ("Ctrl++", 1), ("Ctrl+-", -1)):
            QShortcut(QKeySequence(seq), self, activated=lambda step=step: self.zoom(step))
        QShortcut(QKeySequence("Ctrl+0"), self, activated=lambda: self.set_zoom(HOUR_H))
        try:
            saved = int(db.get_pref("cal_zoom", str(HOUR_H)))
        except ValueError:
            saved = HOUR_H
        self.set_zoom(min(ZOOM_STEPS, key=lambda z: abs(z - saved)), save=False)
        self.month_view.changeRequested.connect(self.change_occurrence)
        self.day_header.dayClicked.connect(lambda d: self.go_date(d, "day"))
        self.month_view.dayClicked.connect(lambda d: self.go_date(d, "day"))

        self.tick = QTimer(self)
        self.tick.timeout.connect(self.grid.update)   # линия «сейчас»
        self.tick.start(60_000)

    # ---- навигация ----
    def days(self) -> list[date]:
        if self.view == "day":
            return [self.anchor]
        if self.view == "week":
            s = cal.week_start(self.anchor)
            return [s + timedelta(days=i) for i in range(7)]
        return [d for week in cal.month_grid(self.anchor.year, self.anchor.month) for d in week]

    def set_view(self, view: str) -> None:
        self.view = view
        self.db.set_pref("cal_view", view)
        for b in self.view_group.buttons():
            b.setChecked(b.property("key") == view)
        self.refresh()

    def shift(self, n: int) -> None:
        if self.view == "day":
            self.anchor += timedelta(days=n)
        elif self.view == "week":
            self.anchor += timedelta(weeks=n)
        else:
            m = self.anchor.month - 1 + n
            self.anchor = date(self.anchor.year + m // 12, m % 12 + 1, 1)
        self.refresh()

    def go_today(self) -> None:
        self.anchor = date.today()
        self.refresh()
        self._scroll_to_now()

    def go_date(self, d: date, view: str | None = None) -> None:
        self.anchor = d
        if view:
            self.set_view(view)
        else:
            self.refresh()

    def focus_item(self, day: date | None = None, view: str | None = None) -> None:
        if day:
            self.go_date(day, view or "day")

    def keyPressEvent(self, e) -> None:
        keys = {Qt.Key_D: "day", Qt.Key_W: "week", Qt.Key_M: "month"}
        if e.key() in keys and not e.modifiers():
            self.set_view(keys[e.key()])
        elif e.key() in (Qt.Key_Left, Qt.Key_J, Qt.Key_P):
            self.shift(-1)
        elif e.key() in (Qt.Key_Right, Qt.Key_K, Qt.Key_N) and not e.modifiers():
            self.shift(1)
        elif e.key() == Qt.Key_T:
            self.go_today()
        else:
            super().keyPressEvent(e)

    # ---- масштаб ----
    def zoom(self, step: int, anchor_y: float | None = None) -> None:
        cur = self.grid.hour_h
        i = min(range(len(ZOOM_STEPS)), key=lambda k: abs(ZOOM_STEPS[k] - cur))
        i = max(0, min(len(ZOOM_STEPS) - 1, i + step))
        self.set_zoom(ZOOM_STEPS[i], anchor_y=anchor_y)

    def set_zoom(self, h: int, save: bool = True, anchor_y: float | None = None) -> None:
        bar = self.grid_scroll.verticalScrollBar()
        old = self.grid.hour_h
        view_h = self.grid_scroll.viewport().height()
        # точка, которая должна остаться на месте: под курсором или центр экрана
        y = anchor_y if anchor_y is not None else bar.value() + view_h / 2
        offset = y - bar.value()
        hours = y / old
        self.grid.set_hour_height(h)
        self.grid_scroll.widget().adjustSize()
        bar.setRange(0, max(0, 24 * h + 1 - view_h))
        bar.setValue(int(hours * h - offset))
        self.zoom_label.setText(f"{round(h * 100 / HOUR_H)}%")
        self.zoom_out.setEnabled(h > ZOOM_STEPS[0])
        self.zoom_in.setEnabled(h < ZOOM_STEPS[-1])
        if save:
            self.db.set_pref("cal_zoom", str(h))

    def _scroll_to_now(self) -> None:
        h = max(0, datetime.now().hour - 2) if self.anchor == date.today() else 7
        QTimer.singleShot(0, lambda: self.grid_scroll.verticalScrollBar().setValue(int(h * self.grid.hour_h)))

    # ---- данные ----
    def _calendars(self) -> dict[int, CalendarInfo]:
        return {c.id: c for c in self.db.list_calendars()}

    def _items(self, days: list[date]) -> list[Item]:
        cals = self._calendars()
        visible = {cid for cid, c in cals.items() if c.visible}
        events = [e for e in self.db.list_events() if e.calendar_id in visible or e.calendar_id is None]
        start = datetime.combine(days[0], time.min)
        end = datetime.combine(days[-1], time.min) + timedelta(days=1)
        items = []
        for o in cal.occurrences(events, start, end):
            c = o.event.color or (cals[o.event.calendar_id].color if o.event.calendar_id in cals
                                  else EVENT_COLORS[0][0])
            items.append(Item(occ=o, color=c))
        if self.show_tasks.isChecked():
            for t in self.db.list_tasks():
                if t.deadline and not t.done and not t.archived and days[0] <= t.deadline <= days[-1]:
                    items.append(Item(task=t))
        return items

    def refresh(self) -> None:
        days = self.days()
        items = self._items(days)
        a = self.anchor
        if self.view == "day":
            title = f"{w.WEEKDAYS_FULL[a.weekday()]}, {w.human_date(a, date.today())}"
        elif self.view == "week":
            s, e = days[0], days[-1]
            if s.month == e.month:
                title = f"{s.day}–{e.day} {w.MONTHS_GEN[e.month - 1]} {e.year}"
            else:
                title = f"{s.day} {w.MONTHS_GEN[s.month - 1][:3]} – {e.day} {w.MONTHS_GEN[e.month - 1][:3]} {e.year}"
        else:
            title = f"{MONTHS[a.month - 1]} {a.year}"
        self.header.title.setText(title)
        timed = [i for i in items if not i.all_day]
        n = len({i.occ.key for i in items if i.occ})
        self.header.set_subtitle(f"{n} {logic.plural(n, 'событие', 'события', 'событий')}" if n else
                                 "Протяните мышью по сетке, чтобы создать событие")
        self.mini.set_selection(days if self.view != "month" else [], a)
        month = self.view == "month"
        self.week_box.setVisible(not month)
        self.zoom_box.setVisible(not month)
        self.month_view.setVisible(month)
        if month:
            self.month_view.set_data(cal.month_grid(a.year, a.month), a.month, items)
        else:
            self.day_header.set_days(days)
            self.all_day_bar.set_data(days, items)
            self.grid.set_data(days, timed)
            if not self._scrolled:
                self._scrolled = True
                self._scroll_to_now()
        self._rebuild_calendars()
        self.setFocus()

    def _rebuild_calendars(self) -> None:
        w.clear_layout(self.cal_box)
        for c in self.db.list_calendars():
            row = QHBoxLayout()
            cb = QCheckBox(c.name)
            cb.setChecked(c.visible)
            cb.setStyleSheet(f"QCheckBox::indicator {{ border-color: {c.color}; }}"
                             f"QCheckBox::indicator:checked {{ background: {c.color}; border-color: {c.color}; }}")
            cb.toggled.connect(lambda on, c=c: self._set_visible(c, on))
            row.addWidget(cb, 1)
            mb = w.menu_button(f"Действия с календарём «{c.name}»")
            mb.setFixedSize(26, 26)
            m = QMenu(mb)
            m.addAction("Изменить…", lambda c=c: self.edit_calendar(c))
            m.addAction("Удалить…", lambda c=c: self.delete_calendar(c))
            mb.setMenu(m)
            row.addWidget(mb)
            holder = QWidget(); holder.setLayout(row); row.setContentsMargins(0, 0, 0, 0)
            self.cal_box.addWidget(holder)

    def _set_visible(self, c: CalendarInfo, on: bool) -> None:
        c.visible = on
        self.db.update_calendar(c)
        self.refresh()

    def add_calendar(self) -> None:
        dlg = CalendarEditDialog(self)
        if dlg.exec() == QDialog.Accepted:
            self.db.add_calendar(*dlg.values())
            self.refresh()

    def edit_calendar(self, c: CalendarInfo) -> None:
        dlg = CalendarEditDialog(self, c)
        if dlg.exec() == QDialog.Accepted:
            c.name, c.color = dlg.values()
            self.db.update_calendar(c)
            self.refresh()

    def delete_calendar(self, c: CalendarInfo) -> None:
        if len(self.db.list_calendars()) <= 1:
            QMessageBox.information(self, "Календарь", "Нужен хотя бы один календарь.")
            return
        n = sum(1 for e in self.db.list_events() if e.calendar_id == c.id)
        box = QMessageBox(QMessageBox.Warning, "Удалить календарь", f"Удалить календарь «{c.name}»?", parent=self)
        box.setInformativeText(f"Вместе с ним удалятся его события: {n}. Это нельзя отменить."
                               if n else "В нём нет событий.")
        yes = box.addButton("Удалить", QMessageBox.DestructiveRole)
        box.addButton("Отмена", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is yes:
            self.db.delete_calendar(c.id)
            self.refresh()

    # ---- события ----
    def new_item(self) -> None:
        now = datetime.now()
        base = datetime.combine(self.anchor, time(now.hour)) + timedelta(hours=1)
        self.create_at(base, base + timedelta(hours=1), False)

    def create_at(self, start: datetime, end: datetime, all_day: bool) -> None:
        cals = self.db.list_calendars()
        default = next((c.id for c in cals if c.visible), cals[0].id)
        ev = Event(0, "", start, end, all_day=all_day, calendar_id=default)
        dlg = EventDialog(self, cals, ev, is_new=True)
        if dlg.exec() == QDialog.Accepted:
            self.db.add_event(dlg.event)
            self.refresh()

    def open_item(self, item: Item) -> None:
        if item.task:
            self.navigate("tasks", task_id=item.task.id)
            return
        occ = item.occ
        series = self.db.get_event(occ.event.id)
        if series is None:
            return
        # в диалоге показываем выбранное вхождение
        draft = Event(**{**series.__dict__, "start": occ.start, "end": occ.end,
                         "weekdays": list(series.weekdays), "exdates": list(series.exdates)})
        dlg = EventDialog(self, self.db.list_calendars(), draft, is_new=False)
        res = dlg.exec()
        if res == EventDialog.DELETE:
            self.delete_occurrence(series, occ)
        elif res == QDialog.Accepted:
            self.apply_edit(series, occ, dlg.event)
        self.refresh()

    def change_occurrence(self, occ: Occurrence, start: datetime, end: datetime) -> None:
        """Перетаскивание / растягивание мышью."""
        series = self.db.get_event(occ.event.id)
        if series is None:
            return
        edited = Event(**{**series.__dict__, "start": start, "end": end,
                          "weekdays": list(series.weekdays), "exdates": list(series.exdates)})
        self.apply_edit(series, occ, edited, moved=True)
        self.refresh()

    def apply_edit(self, series: Event, occ: Occurrence, edited: Event, moved: bool = False) -> None:
        if not series.recurring:
            edited.id = series.id
            edited.exdates = []
            self.db.update_event(edited)
            return
        dlg = ScopeDialog(self, "Перенести" if moved else "Изменить")
        if dlg.exec() != QDialog.Accepted:
            return
        scope = dlg.scope()
        if scope == ScopeDialog.THIS:
            single = Event(**{**edited.__dict__, "id": 0, "freq": cal.FREQ_NONE, "until": None,
                              "exdates": [], "weekdays": []})
            series.exdates = sorted(set(series.exdates) | {occ.start.date()})
            self.db.update_event(series)
            self.db.add_event(single)
        elif scope == ScopeDialog.FOLLOWING and occ.start.date() > series.start.date():
            tail = Event(**{**edited.__dict__, "id": 0,
                            "exdates": [d for d in series.exdates if d > occ.start.date()]})
            if moved and tail.freq == cal.FREQ_WEEKLY and series.weekdays:
                shift = (edited.start.date() - occ.start.date()).days
                tail.weekdays = sorted({(d + shift) % 7 for d in series.weekdays})
            series.until = occ.start.date() - timedelta(days=1)
            self.db.update_event(series)
            self.db.add_event(tail)
        else:   # все события (или «следующие» с первого вхождения — то же самое)
            delta_start = edited.start - occ.start
            delta_end = edited.end - occ.end
            if moved:
                series.start += delta_start
                series.end += delta_end
                if series.freq == cal.FREQ_WEEKLY and series.weekdays:
                    shift = (edited.start.date() - occ.start.date()).days
                    series.weekdays = sorted({(d + shift) % 7 for d in series.weekdays})
                self.db.update_event(series)
            else:
                duration = edited.end - edited.start
                edited.id = series.id
                edited.start = series.start + delta_start   # дата первого вхождения сохраняется
                edited.end = edited.start + duration
                edited.exdates = series.exdates
                self.db.update_event(edited)

    def delete_occurrence(self, series: Event, occ: Occurrence) -> None:
        if not series.recurring:
            self.db.delete_event(series.id)
            return
        dlg = ScopeDialog(self, "Удалить")
        if dlg.exec() != QDialog.Accepted:
            return
        scope = dlg.scope()
        if scope == ScopeDialog.THIS:
            series.exdates = sorted(set(series.exdates) | {occ.start.date()})
            self.db.update_event(series)
        elif scope == ScopeDialog.FOLLOWING and occ.start.date() > series.start.date():
            series.until = occ.start.date() - timedelta(days=1)
            self.db.update_event(series)
        else:
            self.db.delete_event(series.id)
