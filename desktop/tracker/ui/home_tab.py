"""Главная: что важно сегодня — привычки, ближайшие сроки, цели, закреплённая заметка."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QComboBox, QFrame, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from .. import cal, logic
from ..db import Database
from . import widgets as w
from .goals_tab import deadline_text, progress_bar

CHART_DAYS = 14
WIDE = 940   # от этой ширины — две колонки
NARROW_ORDER: dict[int, int] = {}


def greeting(now: datetime) -> str:
    h = now.hour
    if 5 <= h < 12:
        return "Доброе утро"
    if 12 <= h < 18:
        return "Добрый день"
    if 18 <= h < 23:
        return "Добрый вечер"
    return "Доброй ночи"


def _row(last: bool) -> QFrame:
    f = QFrame()
    f.setObjectName("rowLast" if last else "row")
    return f


class HomePage(w.Page):
    def __init__(self, db: Database, navigate):
        super().__init__("")
        self.db = db
        self.navigate = navigate
        # Две независимые колонки: карточки разной высоты не оставляют пустот.
        self.columns = QHBoxLayout()
        self.columns.setSpacing(12)
        self.col = [QVBoxLayout(), QVBoxLayout()]
        for c in self.col:
            c.setSpacing(12)
            c.setAlignment(Qt.AlignTop)
        self.columns.addLayout(self.col[0], 3)
        self.columns.addLayout(self.col[1], 2)
        self.content.addLayout(self.columns)
        self.content.addStretch()
        self.cards: list[tuple[QWidget, int]] = []   # (карточка, колонка в широком режиме)
        self._wide: bool | None = None

    # ---- раскладка: 2 колонки на широком окне, 1 — на узком ----

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        wide = self.width() >= WIDE
        if wide != self._wide:
            self._place()

    def _place(self) -> None:
        self._wide = self.width() >= WIDE
        for c in self.col:
            while c.count():
                c.takeAt(0)
        # на узком окне — одна колонка в порядке важности
        order = self.cards if self._wide else sorted(self.cards, key=lambda cc: NARROW_ORDER[id(cc[0])])
        for card, col in order:
            self.col[col if self._wide else 0].addWidget(card)
        self.columns.setStretch(1, 2 if self._wide else 0)

    # ---- данные ----

    def refresh(self) -> None:
        today = date.today()
        now = datetime.now()
        habits = self.db.list_habits()
        marks = self.db.all_marks()
        tasks = self.db.list_tasks()
        topics = {t.id: t for t in self.db.list_topics()}
        goals = logic.active_goals(self.db.list_goals())
        steps = self.db.all_steps()
        self._saved = self.db.saved_amounts()
        notes = logic.sort_notes(self.db.list_notes())

        self.header.title.setText(f"{w.WEEKDAYS_FULL[today.weekday()]}, {w.human_date(today, today)}")
        done_today = sum(1 for h in habits if today in marks.get(h.id, set()))
        overdue = sum(1 for t in tasks if logic.is_overdue(t, today))
        parts = [greeting(now) + "."]
        if habits:
            left = len(habits) - done_today
            parts.append("Все привычки на сегодня отмечены." if left == 0 else
                         f"Осталось отметить {left} {logic.plural(left, 'привычку', 'привычки', 'привычек')}.")
        if overdue:
            parts.append(f"{overdue} {logic.plural(overdue, 'задача просрочена', 'задачи просрочены', 'задач просрочено')}.")
        self.header.set_subtitle(" ".join(parts))

        with self.keep_scroll():
            for card, _ in self.cards:
                card.hide()
                card.deleteLater()
            cal_c = self._calendar_card(today)
            habits_c = self._habits_card(habits, marks, today)
            tasks_c = self._tasks_card(tasks, topics, today)
            chart_c = self._chart_card(habits, marks, today)
            goals_c = self._goals_card(goals, steps, today)
            note_c = self._note_card(notes)
            self.cards = [(habits_c, 0), (tasks_c, 0), (cal_c, 1), (chart_c, 1), (goals_c, 1), (note_c, 1)]
            NARROW_ORDER.clear()
            for i, c in enumerate((cal_c, habits_c, tasks_c, chart_c, goals_c, note_c)):
                NARROW_ORDER[id(c)] = i
            self._place()

    # ---- карточки ----

    def _link(self, text: str, index) -> QPushButton:
        b = w.button(text, "ghost")
        b.clicked.connect(lambda: self.navigate(index))
        return b

    def _habits_card(self, habits, marks, today) -> w.Card:
        card = w.Card("Привычки сегодня", self._link("Все привычки", "habits"))
        if not habits:
            card.body.addWidget(w.label("Добавьте первую привычку — и отмечайте её здесь одним "
                                        "щелчком.", "secondary", wrap=True))
            return card
        box = QVBoxLayout()
        box.setSpacing(0)
        for i, h in enumerate(habits):
            hm = marks.get(h.id, set())
            done = today in hm
            row = _row(i == len(habits) - 1)
            lay = QHBoxLayout(row)
            lay.setContentsMargins(0, 8, 0, 8)
            lay.setSpacing(12)
            check = QPushButton("✓")
            check.setProperty("kind", "check")
            check.setCheckable(True)
            check.setChecked(done)
            check.setCursor(Qt.PointingHandCursor)
            check.setAccessibleName(f"{h.name}: {'выполнено' if done else 'не выполнено'} сегодня")
            check.setToolTip("Снять отметку" if done else "Отметить выполненной сегодня")
            check.toggled.connect(lambda on, hid=h.id: self._mark(hid, on))
            lay.addWidget(check)
            name = w.label(h.name)
            name.setTextFormat(Qt.PlainText)
            lay.addWidget(name, 1)
            streak = logic.current_streak(hm, today)
            if streak:
                lay.addWidget(w.label(f"{streak} {logic.plural(streak, 'день', 'дня', 'дней')} подряд",
                                      "caption"))
            lay.addWidget(w.HeatStrip(logic.last_days(today, 7), hm, today, cell=10, gap=3))
            box.addWidget(row)
        card.body.addLayout(box)
        return card

    def _mark(self, habit_id: int, on: bool) -> None:
        self.db.set_mark(habit_id, date.today(), on)
        self.refresh()

    def _calendar_card(self, today: date) -> w.Card:
        card = w.Card("Сегодня в календаре", self._link("Календарь", "calendar"))
        visible = {c.id: c for c in self.db.list_calendars() if c.visible}
        events = [e for e in self.db.list_events() if e.calendar_id in visible]
        start = datetime.combine(today, time.min)
        occs = cal.occurrences(events, start, start + timedelta(days=1))
        now = datetime.now()
        if not occs:
            card.body.addWidget(w.label("На сегодня событий нет.", "secondary"))
            add = w.button("Добавить событие", None, "plus")
            add.clicked.connect(lambda: self.navigate("calendar", day=today))
            card.body.addWidget(add, 0, Qt.AlignLeft)
            return card
        for o in occs[:6]:
            row = w.ClickableFrame("rowLast")
            row.setToolTip("Открыть в календаре")
            lay = QHBoxLayout(row)
            lay.setContentsMargins(0, 4, 0, 4)
            lay.setSpacing(10)
            color = o.event.color or visible[o.event.calendar_id].color
            bar = QFrame()
            bar.setFixedSize(4, 32)
            bar.setStyleSheet(f"background: {color}; border-radius: 2px;")
            lay.addWidget(bar)
            col = QVBoxLayout()
            col.setSpacing(0)
            t = w.label(o.event.title or "(без названия)")
            t.setTextFormat(Qt.PlainText)
            past = not o.event.all_day and o.end <= now
            if past:
                t.setProperty("role", "secondary")
            col.addWidget(t)
            when = "Весь день" if o.event.all_day else f"{o.start:%H:%M}–{o.end:%H:%M}"
            if not o.event.all_day and o.start <= now < o.end:
                when += " · идёт сейчас"
            if o.event.location:
                when += f" · {o.event.location}"
            col.addWidget(w.label(when, "caption"))
            lay.addLayout(col, 1)
            row.clicked.connect(lambda: self.navigate("calendar", day=today))
            card.body.addWidget(row)
        if len(occs) > 6:
            card.body.addWidget(w.label(f"и ещё {len(occs) - 6}", "caption"))
        return card

    def _period_combo(self, days: int) -> QComboBox:
        combo = QComboBox()
        combo.setAccessibleName("Период для ближайших задач")
        for value, name in logic.UPCOMING_CHOICES:
            combo.addItem(name, value)
        combo.setCurrentIndex(max(0, combo.findData(days)))

        def changed(_i):
            self.db.set_pref("upcoming_days", str(combo.currentData()))
            QTimer.singleShot(0, self.refresh)   # перестроить после выхода из обработчика
        combo.currentIndexChanged.connect(changed)
        return combo

    def _tasks_card(self, tasks, topics, today) -> w.Card:
        try:
            days = int(self.db.get_pref("upcoming_days", "4"))
        except ValueError:
            days = 4
        upcoming = logic.upcoming_tasks(tasks, today, days)
        actions = QWidget()
        al = QHBoxLayout(actions)
        al.setContentsMargins(0, 0, 0, 0)
        al.setSpacing(6)
        al.addWidget(self._period_combo(days))
        al.addWidget(self._link("Все задачи", "tasks"))
        card = w.Card("Ближайшие задачи", actions)
        period = {4: "ближайшие 4 дня", 7: "ближайшую неделю", 14: "ближайшие две недели"}.get(
            days, f"ближайшие {days} дн.")
        card.body.addWidget(w.label(f"Просроченные и со сроком на {period}", "caption"))
        if not upcoming:
            card.body.addWidget(w.label("На ближайшие дни сроков нет.", "secondary"))
            return card
        box = QVBoxLayout()
        box.setSpacing(0)
        for i, t in enumerate(upcoming[:10]):
            row = w.ClickableFrame()
            row.setObjectName("row" if i < min(len(upcoming), 10) - 1 else "rowLast")
            row.setToolTip("Открыть задачу")
            lay = QHBoxLayout(row)
            lay.setContentsMargins(0, 8, 0, 8)
            lay.setSpacing(12)
            check = QPushButton("✓")
            check.setProperty("kind", "check")
            check.setCheckable(True)
            check.setCursor(Qt.PointingHandCursor)
            check.setToolTip("Отметить выполненной")
            check.setAccessibleName(f"Отметить «{t.title}» выполненной")
            check.toggled.connect(lambda on, tid=t.id: self._complete(tid))
            lay.addWidget(check)
            col = QVBoxLayout()
            col.setSpacing(1)
            title = w.label(t.title)
            title.setTextFormat(Qt.PlainText)
            if t.priority == logic.PRIORITY_HIGH:
                f = title.font(); f.setWeight(f.Weight.DemiBold); title.setFont(f)
            col.addWidget(title)
            topic = topics.get(t.topic_id)
            if topic:
                tl = w.label("", "caption")
                tl.setText(w.topic_html(topic.name, topic.color))
                col.addWidget(tl)
            lay.addLayout(col, 1)
            role = "danger" if logic.is_overdue(t, today) else ("warn" if t.deadline == today else "secondary")
            lay.addWidget(w.label(logic.due_text(t.deadline, today), role))
            row.clicked.connect(lambda tid=t.id: self.navigate("tasks", task_id=tid))
            box.addWidget(row)
        card.body.addLayout(box)
        if len(upcoming) > 10:
            card.body.addWidget(w.label(f"и ещё {len(upcoming) - 10}", "caption"))
        return card

    def _complete(self, task_id: int) -> None:
        task = self.db.get_task(task_id)
        if task:
            task.done = True
            self.db.update_task(task)
        self.refresh()

    def _chart_card(self, habits, marks, today) -> w.Card:
        card = w.Card(f"Привычки за {CHART_DAYS} дней", self._link("Статистика", "stats"))
        if not habits:
            card.body.addWidget(w.label("График появится, когда вы начнёте отмечать привычки.",
                                        "secondary", wrap=True))
            return card
        points = logic.completion_by_day(habits, marks, today, CHART_DAYS)
        avg = sum(v for _, v in points) / len(points)
        week = points[-7:]
        prev = points[:7]
        delta = sum(v for _, v in week) / 7 - sum(v for _, v in prev) / 7
        trend = ""
        if abs(delta) >= 1:
            trend = f" · эта неделя {'лучше' if delta > 0 else 'хуже'} прошлой на {abs(delta):.0f}%"
        card.body.addWidget(w.label(f"В среднем {avg:.0f}% отмечено{trend}", "secondary"))
        card.body.addWidget(w.MiniBars(points, today))
        return card

    def _goals_card(self, goals, steps, today) -> w.Card:
        card = w.Card("Цели", self._link("Все цели", "goals"))
        if not goals:
            card.body.addWidget(w.label("Поставьте долгосрочную цель и разбейте её на шаги.",
                                        "secondary", wrap=True))
            return card
        for g in goals[:3]:
            row = w.ClickableFrame("rowLast")
            row.setToolTip("Открыть цель")
            lay = QVBoxLayout(row)
            lay.setContentsMargins(0, 4, 0, 6)
            lay.setSpacing(5)
            head = QHBoxLayout()
            title = w.label(g.title)
            title.setTextFormat(Qt.PlainText)
            head.addWidget(title, 1)
            prog = logic.goal_progress(g, steps.get(g.id, []), self._saved.get(g.id, 0.0))
            head.addWidget(w.label(f"{round(prog * 100)}%", "secondary"))
            lay.addLayout(head)
            lay.addWidget(progress_bar(prog))
            text, role = deadline_text(g, today)
            lay.addWidget(w.label(text, role or "caption"))
            row.clicked.connect(lambda gid=g.id: self.navigate("goals", goal_id=gid))
            card.body.addWidget(row)
        if len(goals) > 3:
            card.body.addWidget(w.label(f"и ещё {len(goals) - 3}", "caption"))
        return card

    def _note_card(self, notes) -> w.Card:
        note = notes[0] if notes else None
        title = "Закреплённая заметка" if note and note.pinned else "Последняя заметка"
        card = w.Card(title, self._link("Все заметки", "notes"))
        if not note:
            new = w.button("Написать заметку", None, "plus")
            new.clicked.connect(lambda: self.navigate("notes", new=True))
            card.body.addWidget(w.label("Здесь будет закреплённая или последняя заметка.",
                                        "secondary", wrap=True))
            card.body.addWidget(new, 0, Qt.AlignLeft)
            return card
        frame = w.ClickableFrame("rowLast")
        frame.setToolTip("Открыть заметку")
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        t = w.label(note.display_title)
        t.setTextFormat(Qt.PlainText)
        f = t.font(); f.setWeight(f.Weight.DemiBold); t.setFont(f)
        lay.addWidget(t)
        lines = [ln for ln in note.body.splitlines() if ln.strip()]
        if not note.title.strip() and lines:
            lines = lines[1:]
        preview = "\n".join(lines[:5])
        if preview:
            p = w.label(preview, "secondary", wrap=True)
            p.setTextFormat(Qt.PlainText)
            lay.addWidget(p)
        frame.clicked.connect(lambda nid=note.id: self.navigate("notes", note_id=nid))
        card.body.addWidget(frame)
        return card
