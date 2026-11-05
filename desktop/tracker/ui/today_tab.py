"""«Сегодня» — один экран на день: просроченное, задачи и карточки досок на сегодня, привычки
и план дня по часам (задачу можно перетащить на время — появится событие в календаре).
Вкладка «Обзор недели» — итоги недели и разбор хвостов (по мотивам еженедельного обзора GTD)."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

from PySide6.QtCore import QByteArray, QMimeData, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLineEdit, QMenu, QPushButton, QScrollArea, QSplitter, QStackedWidget,
    QVBoxLayout, QWidget,
)

from .. import cal, logic
from ..cal import Event
from ..db import Database
from . import widgets as w
from .calendar_tab import CalendarPage, TimeGrid
from .theme import theme, topic_color

TASK_MIME = "application/x-tracker-task"
WEEKDAYS_FULL = w.WEEKDAYS_FULL


# ---------------------------------------------------------------- строка задачи (можно тащить на время)

class TaskRow(QFrame):
    def __init__(self, page: "TodayPage", task: logic.Task, boards: dict, topics: dict, today: date,
                 show_due: bool = False):
        super().__init__()
        self.page = page
        self.task = task
        self.setObjectName("rowClickable")
        self.setCursor(Qt.OpenHandCursor)
        self.setToolTip("Перетащите на время в плане дня справа · двойной щелчок — открыть")
        self._press: QPoint | None = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 6, 4, 6)
        lay.setSpacing(10)
        check = QPushButton("✓")
        check.setProperty("kind", "check")
        check.setCheckable(True)
        check.setChecked(task.done)
        check.setCursor(Qt.PointingHandCursor)
        check.setAccessibleName(f"Отметить «{task.title}» выполненной")
        check.toggled.connect(lambda on: page.complete(task.id, on))
        lay.addWidget(check)
        col = QVBoxLayout()
        col.setSpacing(1)
        title = w.label(task.title, wrap=True)
        title.setTextFormat(Qt.PlainText)
        if task.priority == logic.PRIORITY_HIGH and not task.done:
            f = title.font(); f.setWeight(f.Weight.DemiBold); title.setFont(f)
        if task.done:
            title.setStyleSheet(f"color: {theme['text3']}; text-decoration: line-through;")
        col.addWidget(title)
        bits = []
        b = boards.get(task.board_id)
        if b:
            bits.append(f"<span style='color:{topic_color(b.color).name()}'>●</span> {b.name}")
        tp = topics.get(task.topic_id)
        if tp:
            bits.append(f"<span style='color:{topic_color(tp.color).name()}'>●</span> {tp.name}")
        if task.repeat:
            bits.append("↻ " + logic.repeat_text(task.repeat).lower())
        bits += [f"#{l}" for l in task.label_list]
        if bits:
            m = w.label("", "caption", wrap=True)
            m.setTextFormat(Qt.RichText)
            m.setText(" &nbsp;·&nbsp; ".join(bits))
            col.addWidget(m)
        lay.addLayout(col, 1)
        if show_due and task.deadline:
            role = "danger" if task.deadline < today and not task.done else "caption"
            lay.addWidget(w.label(logic.due_text(task.deadline, today), role))
        more = w.menu_button(f"Действия с «{task.title}»")
        mm = QMenu(more)
        mm.addAction("На сегодня", lambda: page.reschedule(task.id, today))
        mm.addAction("На завтра", lambda: page.reschedule(task.id, today + timedelta(days=1)))
        mm.addAction("На понедельник", lambda: page.reschedule(task.id, today + timedelta(days=7 - today.weekday())))
        mm.addAction("Убрать срок", lambda: page.reschedule(task.id, None))
        mm.addSeparator()
        mm.addAction("Открыть…", lambda: page.open_task(task))
        more.setMenu(mm)
        lay.addWidget(more)

    def mouseDoubleClickEvent(self, _e) -> None:
        self.page.open_task(self.task)

    def mousePressEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self._press = e.position().toPoint()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e) -> None:
        if self._press is None or (e.position().toPoint() - self._press).manhattanLength() < 8:
            return
        self._press = None
        md = QMimeData()
        md.setData(TASK_MIME, QByteArray(str(self.task.id).encode()))
        drag = QDrag(self)
        drag.setMimeData(md)
        pm = self.grab()
        drag.setPixmap(pm.scaledToWidth(min(pm.width(), 320), Qt.SmoothTransformation))
        drag.exec(Qt.CopyAction)


class DayGrid(TimeGrid):
    """Сетка одного дня, на которую можно бросить задачу."""
    taskDropped = Signal(int, object)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)

    def dragEnterEvent(self, e) -> None:
        if e.mimeData().hasFormat(TASK_MIME):
            e.acceptProposedAction()

    def dragMoveEvent(self, e) -> None:
        if e.mimeData().hasFormat(TASK_MIME):
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:
        if not e.mimeData().hasFormat(TASK_MIME):
            return
        tid = int(bytes(e.mimeData().data(TASK_MIME)).decode())
        _, start = self.pos_to(e.position())
        start = start.replace(minute=(start.minute // 15) * 15, second=0, microsecond=0)
        e.acceptProposedAction()
        QTimer.singleShot(0, lambda: self.taskDropped.emit(tid, start))


# ---------------------------------------------------------------- страница

class TodayPage(w.Page):
    def __init__(self, db: Database, navigate=None):
        super().__init__("Сегодня", scroll=False)
        self.db = db
        self.navigate = navigate
        self.week_offset = 0
        # календарная страница без показа: её окна событий и перенос переиспользуем
        self.cal = CalendarPage(db, navigate or (lambda *a, **k: None))
        self.cal.setParent(self)
        self.cal.hide()

        seg = QHBoxLayout()
        self.tab_group = QButtonGroup(self)
        for i, name in enumerate(("Сегодня", "Обзор недели")):
            c = w.chip(name, i == 0)
            c.setProperty("value", i)
            self.tab_group.addButton(c)
            seg.addWidget(c)
        self.tab_group.buttonClicked.connect(lambda b: self._tab(b.property("value")))
        holder = QWidget()
        holder.setLayout(seg)
        self.header.add_action(holder)

        self.stack = QStackedWidget()
        self.content.addWidget(self.stack, 1)

        # ---- сегодня: список | план дня
        split = QSplitter(Qt.Horizontal)
        split.setObjectName("pageSplit")
        split.setHandleWidth(12)
        self.left = QScrollArea()
        self.left.setWidgetResizable(True)
        self.left.setFrameShape(QFrame.NoFrame)
        lw = QWidget()
        self.box = QVBoxLayout(lw)
        self.box.setContentsMargins(0, 0, 8, 0)
        self.box.setSpacing(12)
        self.left.setWidget(lw)
        self.left.setMinimumWidth(320)
        split.addWidget(self.left)

        plan = QFrame()
        plan.setObjectName("card")
        pl = QVBoxLayout(plan)
        pl.setContentsMargins(0, 10, 0, 0)
        pl.setSpacing(4)
        ph = QHBoxLayout()
        ph.setContentsMargins(16, 0, 12, 0)
        ph.addWidget(w.label("План дня", "section"))
        ph.addStretch()
        open_cal = w.button("В календаре", "ghost")
        open_cal.clicked.connect(lambda: self.navigate and self.navigate("calendar", day=date.today()))
        ph.addWidget(open_cal)
        pl.addLayout(ph)
        hint = w.label("Перетащите задачу слева на нужное время — появится блок в календаре. "
                       "Щелчок по пустому месту — новое событие.", "caption", wrap=True)
        hint.setContentsMargins(16, 0, 12, 4)
        pl.addWidget(hint)
        self.grid = DayGrid()
        self.grid_scroll = QScrollArea()
        self.grid_scroll.setWidgetResizable(True)
        self.grid_scroll.setFrameShape(QFrame.NoFrame)
        self.grid_scroll.setWidget(self.grid)
        pl.addWidget(self.grid_scroll, 1)
        self.grid.taskDropped.connect(self.plan_task)
        self.grid.itemClicked.connect(lambda it: (self.cal.open_item(it), self.refresh()))
        self.grid.createRequested.connect(lambda s, e, a: (self.cal.create_at(s, e, a), self.refresh()))
        self.grid.changeRequested.connect(lambda o, s, e: (self.cal.change_occurrence(o, s, e), self.refresh()))
        plan.setMinimumWidth(300)
        split.addWidget(plan)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 1)
        w.remember_splitter(split, db, "split_today", [560, 440])
        self.stack.addWidget(split)

        # ---- обзор недели
        self.week = QScrollArea()
        self.week.setWidgetResizable(True)
        self.week.setFrameShape(QFrame.NoFrame)
        ww = QWidget()
        self.wbox = QVBoxLayout(ww)
        self.wbox.setContentsMargins(0, 0, 8, 0)
        self.wbox.setSpacing(12)
        self.week.setWidget(ww)
        self.stack.addWidget(self.week)
        self._scrolled = False

    # ---- действия ----
    def _tab(self, i: int) -> None:
        self.stack.setCurrentIndex(i)
        for b in self.tab_group.buttons():
            b.setChecked(b.property("value") == i)
        self.refresh()

    def focus_item(self, week: bool = False) -> None:
        self._tab(1 if week else 0)

    def complete(self, task_id: int, on: bool) -> None:
        self.db.complete_task(task_id, on)
        QTimer.singleShot(150, self.refresh)     # галочка успевает «нажаться» — потом строка уходит

    def reschedule(self, task_id: int, day: date | None) -> None:
        t = self.db.get_task(task_id)
        if t:
            t.deadline = day
            self.db.update_task(t)
        self.refresh()

    def open_task(self, task: logic.Task) -> None:
        if self.navigate:
            self.navigate("boards" if task.board_id else "tasks", task_id=task.id)

    def plan_task(self, task_id: int, start: datetime) -> None:
        t = self.db.get_task(task_id)
        if t is None:
            return
        cals = self.db.list_calendars()
        cid = next((c.id for c in cals if c.visible), cals[0].id)
        self.db.add_event(Event(0, t.title, start, start + timedelta(hours=1), calendar_id=cid,
                                description="Время на задачу" + (f": {t.description}" if t.description else "")))
        if t.deadline is None or t.deadline > start.date():
            t.deadline = start.date()        # запланировали на сегодня — значит, и срок сегодня
            self.db.update_task(t)
        self.refresh()

    def _all_reschedule(self, ids: list[int], day: date) -> None:
        for tid in ids:
            t = self.db.get_task(tid)
            if t:
                t.deadline = day
                self.db.update_task(t)
        self.refresh()

    def _quick(self, field: QLineEdit) -> None:
        q = logic.parse_quick_task(field.text(), self.db.list_topics(), date.today())
        if not q.title:
            return
        self.db.add_task(logic.Task(0, q.title, deadline=q.deadline or date.today(), priority=q.priority,
                                    topic_id=q.topic_id, repeat=q.repeat, labels=", ".join(q.labels)))
        self.refresh()
        QTimer.singleShot(0, lambda: self._quick_field.setFocus())

    # ---- отрисовка ----
    def refresh(self) -> None:
        if self.stack.currentIndex() == 1:
            self._fill_week()
        else:
            self._fill_today()

    def _section(self, title: str, action: QWidget | None = None) -> w.Card:
        card = w.Card(title, action)
        self.box.addWidget(card)
        return card

    def _fill_today(self) -> None:
        today = date.today()
        v = self.left.verticalScrollBar().value()
        w.clear_layout(self.box)
        boards = {b.id: b for b in self.db.list_boards(include_archived=True)}
        topics = {t.id: t for t in self.db.list_topics()}
        done_cols = {c.id for b in boards.values() for c in self.db.list_columns(b.id) if c.is_done}
        tasks = [t for t in self.db.list_tasks(include_boards=True)
                 if not t.archived and t.id not in w.PENDING_DELETE and (t.board_id is None or t.board_id in boards)]
        open_tasks = [t for t in tasks if not t.done and t.column_id not in done_cols]
        overdue = sorted((t for t in open_tasks if t.deadline and t.deadline < today), key=lambda t: (t.deadline, t.priority))
        due = sorted((t for t in tasks if t.deadline == today and (not t.done or t.completed_on == today)),
                     key=lambda t: (t.done, t.priority, t.id))
        tomorrow = sorted((t for t in open_tasks if t.deadline == today + timedelta(days=1)), key=lambda t: t.priority)
        habits = self.db.list_habits()
        marks = self.db.all_marks()

        if overdue:
            move = w.button("Всё на сегодня", "ghost")
            move.clicked.connect(lambda: self._all_reschedule([t.id for t in overdue], today))
            card = self._section(f"Просрочено · {len(overdue)}", move)
            for t in overdue:
                card.body.addWidget(TaskRow(self, t, boards, topics, today, show_due=True))

        open_today = sum(1 for t in due if not t.done)
        card = self._section(f"На сегодня · {open_today}" if due else "На сегодня")
        self._quick_field = QLineEdit()
        self._quick_field.setPlaceholderText("Добавить на сегодня: «Позвонить в банк @личное !»")
        self._quick_field.returnPressed.connect(lambda: self._quick(self._quick_field))
        add = w.button("", "primary", "plus", "Добавить (Enter)")
        add.setFixedSize(32, 30)
        add.clicked.connect(lambda: self._quick(self._quick_field))
        row = QHBoxLayout()
        row.addWidget(self._quick_field, 1)
        row.addWidget(add)
        card.body.addLayout(row)
        if not due:
            card.body.addWidget(w.label("На сегодня задач со сроком нет.", "secondary"))
        for t in due:
            card.body.addWidget(TaskRow(self, t, boards, topics, today))

        if habits:
            left = sum(1 for h in habits if today not in marks.get(h.id, set()))
            card = self._section(f"Привычки · осталось {left}" if left else "Привычки · всё отмечено")
            hrow = QHBoxLayout()
            hrow.setSpacing(6)
            strip = w.ChipStrip()
            for h in habits:
                on = today in marks.get(h.id, set())
                c = w.chip(("✓ " if on else "") + h.name, on)
                c.toggled.connect(lambda val, hid=h.id: (self.db.set_mark(hid, today, val), QTimer.singleShot(0, self.refresh)))
                strip.addWidget(c)
            strip.addStretch()
            card.body.addWidget(strip)

        if tomorrow:
            card = self._section(f"Завтра · {len(tomorrow)}")
            for t in tomorrow[:6]:
                card.body.addWidget(TaskRow(self, t, boards, topics, today))
        self.box.addStretch()
        QTimer.singleShot(0, lambda: self.left.verticalScrollBar().setValue(v))

        # план дня
        items = [i for i in self.cal._items([today]) if i.occ is not None]
        self.grid.set_data([today], items)
        if not self._scrolled:
            self._scrolled = True
            h = max(0, datetime.now().hour - 2)
            QTimer.singleShot(0, lambda: self.grid_scroll.verticalScrollBar().setValue(int(h * self.grid.hour_h)))
        n_ev = len(items)
        parts = [f"{WEEKDAYS_FULL[today.weekday()]}, {w.human_date(today, today)}"]
        if open_today:
            parts.append(f"{open_today} {logic.plural(open_today, 'задача', 'задачи', 'задач')}")
        if overdue:
            parts.append(f"{len(overdue)} просрочено")
        if n_ev:
            parts.append(f"{n_ev} {logic.plural(n_ev, 'событие', 'события', 'событий')}")
        self.header.set_subtitle(" · ".join(parts))

    # ---- обзор недели ----
    def _week_card(self, title: str, action: QWidget | None = None) -> w.Card:
        card = w.Card(title, action)
        self.wbox.addWidget(card)
        return card

    def _fill_week(self) -> None:
        today = date.today()
        w.clear_layout(self.wbox)
        start = today - timedelta(days=today.weekday()) + timedelta(weeks=self.week_offset)
        end = start + timedelta(days=6)
        nav = QHBoxLayout()
        prev_b = w.button("", "ghost", "chevron-left", "Предыдущая неделя")
        next_b = w.button("", "ghost", "chevron-right", "Следующая неделя")
        prev_b.clicked.connect(lambda: self._shift_week(-1))
        next_b.clicked.connect(lambda: self._shift_week(1))
        next_b.setEnabled(self.week_offset < 0)
        nav.addWidget(prev_b)
        nav.addWidget(w.label(f"Неделя {start.day} {w.MONTHS_GEN[start.month - 1]} — {end.day} {w.MONTHS_GEN[end.month - 1]}"
                              + (" (эта)" if self.week_offset == 0 else ""), "section"))
        nav.addWidget(next_b)
        nav.addStretch()
        save = w.button("Записать итоги в заметку", None, "notes",
                        "Создать заметку с итогами недели — в папке «Обзоры недели»")
        nav.addWidget(save)
        self.wbox.addLayout(nav)

        boards = {b.id: b for b in self.db.list_boards(include_archived=True)}
        tasks = [t for t in self.db.list_tasks(include_boards=True) if t.id not in w.PENDING_DELETE]
        done = [t for t in tasks if t.done and t.completed_on and start <= t.completed_on <= end]
        habits = self.db.list_habits()
        marks = self.db.all_marks()
        days = [start + timedelta(days=i) for i in range(7) if start + timedelta(days=i) <= today]

        # 1. сделано
        card = self._week_card(f"Сделано · {len(done)}")
        if not done:
            card.body.addWidget(w.label("За эту неделю пока ничего не отмечено выполненным.", "secondary"))
        groups: dict[str, list] = {}
        for t in done:
            groups.setdefault(boards[t.board_id].name if t.board_id in boards else "Задачи", []).append(t)
        for name, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
            card.body.addWidget(w.label(f"{name} · {len(items)}", "secondary"))
            for t in sorted(items, key=lambda t: t.completed_on)[:12]:
                lab = w.label(f"✓  {t.title}", "caption")
                lab.setTextFormat(Qt.PlainText)
                card.body.addWidget(lab)
            if len(items) > 12:
                card.body.addWidget(w.label(f"и ещё {len(items) - 12}", "caption"))

        # 2. привычки
        if habits and days:
            card = self._week_card("Привычки")
            for h in habits:
                hm = marks.get(h.id, set())
                cnt = sum(1 for d in days if d in hm)
                row = QHBoxLayout()
                name = w.label(h.name)
                name.setMinimumWidth(180)
                row.addWidget(name)
                row.addWidget(w.HeatStrip(days, hm, today))
                role = "accent" if cnt == len(days) else ("danger" if cnt == 0 else "secondary")
                row.addWidget(w.label(f"{cnt} из {len(days)}", role))
                row.addStretch()
                card.body.addLayout(row)

        # 3. хвосты: просроченное — решить, что с ним делать
        done_cols = {c.id for b in boards.values() for c in self.db.list_columns(b.id) if c.is_done}
        overdue = sorted((t for t in tasks if not t.done and not t.archived and t.deadline and t.deadline < today
                          and t.column_id not in done_cols), key=lambda t: t.deadline)
        if self.week_offset == 0:
            mon = today + timedelta(days=7 - today.weekday())
            act = None
            if overdue:
                act = w.button("Всё — на понедельник", "ghost")
                act.clicked.connect(lambda: self._all_reschedule([t.id for t in overdue], mon))
            card = self._week_card(f"Хвосты · {len(overdue)}" if overdue else "Хвостов нет", act)
            if not overdue:
                card.body.addWidget(w.label("Просроченных задач нет — отлично.", "secondary"))
            topics = {t.id: t for t in self.db.list_topics()}
            for t in overdue[:20]:
                card.body.addWidget(TaskRow(self, t, boards, topics, today, show_due=True))

            # 4. цели
            goals = logic.active_goals(self.db.list_goals())
            if goals:
                card = self._week_card("Цели")
                steps = self.db.all_steps()
                saved = self.db.saved_amounts()
                flags = self.db.goal_task_flags()
                for g in goals[:8]:
                    p = logic.goal_progress(g, steps.get(g.id, []), saved.get(g.id, 0.0), flags.get(g.id, []))
                    row = QHBoxLayout()
                    row.addWidget(w.label(g.title), 1)
                    row.addWidget(w.label(f"{round(p * 100)}%", "accent"))
                    if g.target_date:
                        row.addWidget(w.label(logic.due_text(g.target_date, today), "caption"))
                    card.body.addLayout(row)

            # 5. следующая неделя
            nstart, nend = mon, mon + timedelta(days=6)
            nxt = sorted((t for t in tasks if not t.done and t.deadline and nstart <= t.deadline <= nend),
                         key=lambda t: t.deadline)
            evs = cal.occurrences([e for e in self.db.list_events()], datetime.combine(nstart, time.min),
                                  datetime.combine(nend + timedelta(days=1), time.min))
            card = self._week_card(f"Следующая неделя · {len(nxt)} задач, {len(evs)} событий")
            for t in nxt[:12]:
                lab = w.label(f"{w.WEEKDAYS_SHORT[t.deadline.weekday()]} · {t.title}"
                              + (f" · {boards[t.board_id].name}" if t.board_id in boards else ""), "secondary")
                lab.setTextFormat(Qt.PlainText)
                card.body.addWidget(lab)
            if not nxt:
                card.body.addWidget(w.label("Сроков на следующую неделю пока нет — хорошее время что-то запланировать.",
                                            "secondary", wrap=True))
        self.wbox.addStretch()
        save.clicked.connect(lambda: self._save_review(start, end, done, overdue, habits, marks, days))
        self.header.set_subtitle(f"Сделано за неделю: {len(done)}")

    def _shift_week(self, d: int) -> None:
        self.week_offset = min(0, self.week_offset + d)
        self._fill_week()

    def _save_review(self, start, end, done, overdue, habits, marks, days) -> None:
        title = f"Неделя {start.day} {w.MONTHS_GEN[start.month - 1]} — {end.day} {w.MONTHS_GEN[end.month - 1]}"
        lines = [f"Сделано: {len(done)}"] + [f"  ✓ {t.title}" for t in done[:30]]
        if habits and days:
            lines.append("")
            lines.append("Привычки:")
            lines += [f"  {h.name}: {sum(1 for d in days if d in marks.get(h.id, set()))} из {len(days)}" for h in habits]
        if overdue:
            lines.append("")
            lines.append(f"Осталось хвостов: {len(overdue)}")
        lines += ["", "Что получилось:", "", "Что мешало:", "", "Главное на следующую неделю:", ""]
        folder = next((f.id for f in self.db.list_folders() if f.name == "Обзоры недели"), None)
        if folder is None:
            folder = self.db.add_folder("Обзоры недели")
        nid = self.db.add_note(title, "\n".join(lines), folder_id=folder)
        if self.navigate:
            self.navigate("notes", note_id=nid)
