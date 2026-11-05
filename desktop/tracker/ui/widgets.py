"""Общие элементы интерфейса: карточки, заголовки страниц, полоса дней, мини-график."""
from __future__ import annotations

import html
from datetime import date

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLayout, QPushButton, QSizePolicy, QToolButton, QVBoxLayout,
    QWidget,
)

from . import icons
from .theme import theme, topic_color

MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
              "сентября", "октября", "ноября", "декабря"]
WEEKDAYS_FULL = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота",
                 "Воскресенье"]
WEEKDAYS_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def human_date(d: date, today: date | None = None) -> str:
    """«1 ноября», с годом — если он не текущий."""
    today = today or date.today()
    s = f"{d.day} {MONTHS_GEN[d.month - 1]}"
    return s if d.year == today.year else f"{s} {d.year}"


def label(text: str = "", role: str | None = None, wrap: bool = False) -> QLabel:
    lbl = QLabel(text)
    if role:
        lbl.setProperty("role", role)
    lbl.setWordWrap(wrap)
    lbl.setTextInteractionFlags(Qt.NoTextInteraction)
    return lbl


def button(text: str, kind: str | None = None, icon_name: str | None = None,
           tooltip: str | None = None) -> QPushButton:
    btn = QPushButton(text)
    if kind:
        btn.setProperty("kind", kind)
    if icon_name:
        color = {"primary": theme["teal_text"], "ghost": theme["link"]}.get(kind, theme["text2"])
        btn.setIcon(icons.icon(icon_name, color, size=16))
        btn.setIconSize(QSize(16, 16))
    if tooltip:
        btn.setToolTip(tooltip)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setAutoDefault(False)   # Enter в диалоге нажимает только кнопку по умолчанию
    return btn


def menu_button(tooltip: str) -> QToolButton:
    """Кнопка «…» с меню редких действий."""
    btn = QToolButton()
    btn.setProperty("kind", "ghost")
    btn.setIcon(icons.icon("more", theme["text2"], size=18))
    btn.setIconSize(QSize(18, 18))
    btn.setToolTip(tooltip)
    btn.setAccessibleName(tooltip)
    btn.setPopupMode(QToolButton.InstantPopup)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setFixedSize(32, 32)
    return btn


def clear_layout(layout: QLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.hide()
            w.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())


class Card(QFrame):
    """Белая карточка с необязательным заголовком и действием справа."""

    def __init__(self, title: str | None = None, action: QWidget | None = None,
                 margins: int = 16):
        super().__init__()
        self.setObjectName("card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(margins, margins - 2, margins, margins)
        self.body.setSpacing(10)
        if title or action:
            head = QHBoxLayout()
            head.setSpacing(8)
            if title:
                head.addWidget(label(title, "section"))
            head.addStretch()
            if action:
                head.addWidget(action)
            self.body.addLayout(head)


class PageHeader(QWidget):
    """Заголовок страницы: название, подзаголовок, действия справа (сверху, а не внизу окна)."""

    def __init__(self, title: str, subtitle: str = ""):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        text = QVBoxLayout()
        text.setSpacing(2)
        self.title = label(title, "title")
        self.subtitle = label(subtitle, "subtitle")
        self.subtitle.setVisible(bool(subtitle))
        text.addWidget(self.title)
        text.addWidget(self.subtitle)
        lay.addLayout(text)
        lay.addStretch()
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        lay.addLayout(self.actions)

    def set_subtitle(self, text: str) -> None:
        self.subtitle.setText(text)
        self.subtitle.setVisible(bool(text))

    def add_action(self, widget: QWidget) -> None:
        self.actions.addWidget(widget)


def topic_html(name: str, color: str) -> str:
    """Цветная точка + название: цвет никогда не единственный носитель смысла."""
    c = topic_color(color).name()
    return f"<span style='color:{c}; font-size:11pt'>●</span>&nbsp;{html.escape(name)}"


class HeatStrip(QWidget):
    """Фирменный элемент: полоса из клеток, по одной на день; заполненная — день выполнен."""

    def __init__(self, days: list[date], marks: set[date], today: date, cell: int = 12,
                 gap: int = 3):
        super().__init__()
        self.days, self.marks, self.today = days, marks, today
        self.cell, self.gap = cell, gap
        self.setMouseTracking(True)
        done = sum(1 for d in days if d in marks)
        self.setAccessibleName(f"Выполнено {done} из {len(days)} дней")
        self.setToolTip(self.accessibleName())
        w = len(days) * (cell + gap) - gap
        self.setFixedSize(w + 4, cell + 4)

    def _index_at(self, x: float) -> int | None:
        i = int(x // (self.cell + self.gap))
        return i if 0 <= i < len(self.days) else None

    def mouseMoveEvent(self, event) -> None:
        i = self._index_at(event.position().x())
        if i is not None:
            d = self.days[i]
            state = "выполнено" if d in self.marks else "не отмечено"
            self.setToolTip(f"{d.strftime('%d.%m.%Y')} — {state}")
        super().mouseMoveEvent(event)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        done, empty = theme.color("accent"), theme.color("empty")
        for i, d in enumerate(self.days):
            x = 1.5 + i * (self.cell + self.gap)
            r = QRectF(x, 1.5, self.cell, self.cell)
            p.setPen(Qt.NoPen)
            p.setBrush(done if d in self.marks else empty)   # «кирпичик» прогресса
            p.drawRoundedRect(r, 2.5, 2.5)
            if d == self.today:  # сегодняшний день обведён — заметно и без цвета
                p.setPen(QPen(theme.color("text"), 1.2))
                p.setBrush(Qt.NoBrush)
                p.drawRoundedRect(r.adjusted(-1, -1, 1, 1), 3, 3)
        p.end()


class MiniBars(QWidget):
    """Компактный столбчатый график процента выполнения по дням."""

    def __init__(self, points: list[tuple[date, float]], today: date, height: int = 96):
        super().__init__()
        self.points, self.today = points, today
        self.setMinimumHeight(height)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)
        if points:
            avg = sum(v for _, v in points) / len(points)
            self.setAccessibleName(
                f"Выполнение привычек за {len(points)} дней, в среднем {avg:.0f}%")

    def _bar_rect(self, i: int, value: float) -> QRectF:
        n = len(self.points)
        label_h = 18
        w = self.width()
        slot = w / n
        bw = max(4.0, slot * 0.62)
        x = i * slot + (slot - bw) / 2 + 1
        h_full = self.height() - label_h - 4
        h = max(3.0, h_full * value / 100.0)
        return QRectF(x, h_full - h + 2, bw, h)

    def mouseMoveEvent(self, event) -> None:
        if self.points:
            i = min(len(self.points) - 1, int(event.position().x() / (self.width() / len(self.points))))
            d, v = self.points[i]
            self.setToolTip(f"{d.strftime('%d.%m')}: {v:.0f}%")
        super().mouseMoveEvent(event)

    def paintEvent(self, _event) -> None:
        if not self.points:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        h_full = self.height() - 18 - 4
        p.setPen(QPen(theme.color("border"), 1))
        p.drawLine(QPointF(0, h_full + 2.5), QPointF(self.width(), h_full + 2.5))
        block, gap = 5.0, 2.0
        accent = theme.color("accent")
        for i, (d, v) in enumerate(self.points):
            r = self._bar_rect(i, v)
            # столбик собран из «кирпичиков» снизу вверх
            capacity = int((h_full - 2) // (block + gap))
            count = round(capacity * v / 100.0)
            if v > 0:
                count = max(1, count)
            y = h_full + 1
            for _ in range(count):
                p.setPen(Qt.NoPen)
                p.setBrush(accent)
                p.drawRoundedRect(QRectF(r.left(), y - block, r.width(), block), 1.5, 1.5)
                y -= block + gap
        # подписи: первый день, середина, сегодня
        f = QFont(self.font())
        f.setPointSizeF(8.5)
        p.setFont(f)
        p.setPen(theme.color("text2"))
        p.setRenderHint(QPainter.TextAntialiasing)
        n = len(self.points)
        slot = self.width() / n
        for i in {0, n // 2, n - 1}:
            d = self.points[i][0]
            text = "сегодня" if d == self.today else d.strftime("%d.%m")
            rect = QRectF(i * slot + slot / 2 - 40, self.height() - 16, 80, 16)
            align = Qt.AlignHCenter
            if i == 0:
                rect = QRectF(0, self.height() - 16, 80, 16); align = Qt.AlignLeft
            elif i == n - 1:
                rect = QRectF(self.width() - 80, self.height() - 16, 80, 16); align = Qt.AlignRight
            p.drawText(rect, align | Qt.AlignVCenter, text)
        p.end()


class ClickableFrame(QFrame):
    clicked = Signal()

    def __init__(self, object_name: str = "rowClickable"):
        super().__init__()
        self.setObjectName(object_name)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.clicked.emit()
            return
        super().keyPressEvent(event)


class Page(QWidget):
    """Каркас раздела: заголовок сверху, под ним содержимое (по желанию — с прокруткой)."""

    MARGIN_H, MARGIN_V = 28, 22

    def __init__(self, title: str, subtitle: str = "", scroll: bool = True):
        super().__init__()
        from PySide6.QtWidgets import QScrollArea
        outer = QVBoxLayout(self)
        outer.setContentsMargins(self.MARGIN_H, self.MARGIN_V, self.MARGIN_H - 8, 0)
        outer.setSpacing(16)
        self.header = PageHeader(title, subtitle)
        self.header.setContentsMargins(0, 0, 8, 0)
        outer.addWidget(self.header)
        if scroll:
            self.scroll = QScrollArea()
            self.scroll.setWidgetResizable(True)
            self.scroll.setFrameShape(QFrame.NoFrame)
            self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            inner = QWidget()
            self.content = QVBoxLayout(inner)
            self.content.setContentsMargins(0, 0, 8, self.MARGIN_V)
            self.content.setSpacing(12)
            self.scroll.setWidget(inner)
            outer.addWidget(self.scroll, 1)
        else:
            self.scroll = None
            holder = QWidget()
            self.content = QVBoxLayout(holder)
            self.content.setContentsMargins(0, 0, 8, self.MARGIN_V)
            self.content.setSpacing(12)
            outer.addWidget(holder, 1)

    def keep_scroll(self):
        """Контекст: сохранить позицию прокрутки при перерисовке содержимого."""
        page = self

        class _Keep:
            def __enter__(self_inner):
                self_inner.v = page.scroll.verticalScrollBar().value() if page.scroll else 0

            def __exit__(self_inner, *exc):
                if page.scroll:
                    from PySide6.QtCore import QTimer
                    bar = page.scroll.verticalScrollBar()
                    QTimer.singleShot(0, lambda: bar.setValue(self_inner.v))
        return _Keep()


class ChipStrip(QWidget):
    """Ряд «плашек», который не сжимает текст: при узком окне его листают —
    колесом мыши или тонкой полосой прокрутки снизу."""

    def __init__(self):
        super().__init__()
        from PySide6.QtWidgets import QScrollArea, QSizePolicy
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.area = QScrollArea()
        self.area.setObjectName("chipStrip")
        self.area.setFrameShape(QFrame.NoFrame)
        self.area.setWidgetResizable(True)
        self.area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        inner = QWidget()
        inner.setObjectName("chipStripInner")
        self.row = QHBoxLayout(inner)
        self.row.setContentsMargins(0, 2, 0, 2)
        self.row.setSpacing(6)
        self.area.setWidget(inner)
        self.area.viewport().installEventFilter(self)
        outer.addWidget(self.area)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self._drag_x = None

    def addWidget(self, wdg: QWidget) -> None:
        from PySide6.QtWidgets import QSizePolicy
        wdg.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)   # текст плашки никогда не обрезается
        self.row.addWidget(wdg)
        self._fit()

    def addStretch(self) -> None:
        self.row.addStretch()

    def clear(self) -> None:
        clear_layout(self.row)

    def _fit(self) -> None:
        h = max((self.row.itemAt(i).widget().sizeHint().height() for i in range(self.row.count())
                 if self.row.itemAt(i).widget()), default=30) + 6
        bar = self.area.horizontalScrollBar().sizeHint().height()
        self.setFixedHeight(h + bar)     # место под полосу есть всегда — ряд не «прыгает»

    def eventFilter(self, obj, e) -> bool:
        from PySide6.QtCore import QEvent
        bar = self.area.horizontalScrollBar()
        if e.type() == QEvent.Wheel and bar.maximum() > 0:
            d = e.angleDelta()
            bar.setValue(bar.value() - (d.y() or d.x()))
            return True
        return False


def chip(text: str, checked: bool = False) -> QPushButton:
    btn = QPushButton(text)
    btn.setProperty("kind", "chip")
    btn.setCheckable(True)
    btn.setChecked(checked)
    btn.setCursor(Qt.PointingHandCursor)
    return btn


def dot_icon(color: str, size: int = 10):
    from PySide6.QtGui import QIcon, QPixmap
    pm = QPixmap(size * 2, size * 2)
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(topic_color(color))
    p.drawEllipse(QRectF(1, 1, size - 2, size - 2))
    p.end()
    return QIcon(pm)


def remember_splitter(split, db, key: str, default: list[int]) -> None:
    """Размеры частей QSplitter запоминаются (ширину блоков можно тянуть мышью за границу)."""
    from PySide6.QtCore import QTimer
    try:
        sizes = [int(x) for x in db.get_pref(key, "").split(",") if x]
    except ValueError:
        sizes = []
    split.setSizes(sizes if len(sizes) == split.count() and sum(sizes) > 0 else default)
    timer = QTimer(split)
    timer.setSingleShot(True)
    timer.setInterval(500)
    timer.timeout.connect(lambda: db.set_pref(key, ",".join(str(s) for s in split.sizes())))
    split.splitterMoved.connect(lambda *_: timer.start())
