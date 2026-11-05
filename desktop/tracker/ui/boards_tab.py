"""Доски — канбан для отдельных областей (например, двух работ): колонки с карточками-задачами
и свои заметки у каждой доски. Карточки перетаскиваются между колонками мышью; колонка «Готово»
отмечает задачу выполненной. Задачи досок не смешиваются с обычным списком «Задачи»,
но их сроки видны на главной и в календаре."""
from __future__ import annotations

from datetime import date, datetime

from PySide6.QtCore import QByteArray, QMimeData, QSize, Qt, QTimer
from PySide6.QtGui import QDrag, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QColorDialog, QDialog, QFrame, QHBoxLayout, QInputDialog, QLineEdit,
    QListWidget, QListWidgetItem, QMenu, QMessageBox, QPlainTextEdit, QScrollArea, QSplitter, QVBoxLayout,
    QWidget,
)

from .. import logic
from ..db import Database
from . import icons
from . import widgets as w
from .tasks_tab import TaskDialog, apply_subtasks
from .theme import theme, topic_color

MIME = "application/x-tracker-card"
COLUMN_W = 284
BOARD_COLORS = ["#0F6E6A", "#1D4ED8", "#7E22CE", "#BE185D", "#B45309", "#15803D", "#374151"]


# ---------------------------------------------------------------- карточка

class CardWidget(QFrame):
    def __init__(self, task: logic.Task, subs: list, topic: logic.Topic | None, today: date):
        super().__init__()
        self.setObjectName("kanbanCard")
        self.setAttribute(Qt.WA_TransparentForMouseEvents)     # мышь — у списка (выбор, перетаскивание)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 9, 12, 9)
        lay.setSpacing(5)
        title = w.label(task.title, wrap=True)
        title.setTextFormat(Qt.PlainText)
        if task.done:
            title.setStyleSheet(f"color: {theme['text3']}; text-decoration: line-through;")
        elif task.priority == logic.PRIORITY_HIGH:
            f = title.font(); f.setWeight(f.Weight.DemiBold); title.setFont(f)
        lay.addWidget(title)
        if task.description:
            first = task.description.strip().splitlines()[0][:90]
            lay.addWidget(w.label(first, "caption", wrap=True))
        meta = []
        if task.priority == logic.PRIORITY_HIGH and not task.done:
            meta.append(f"<span style='color:{theme['danger']}'>● важно</span>")
        if task.deadline:
            col = theme["text2"]
            if not task.done and task.deadline < today:
                col = theme["danger"]
            elif not task.done and task.deadline == today:
                col = theme["warn"]
            meta.append(f"<span style='color:{col}'>{task.deadline:%d.%m} · "
                        f"{logic.due_text(task.deadline, today) if not task.done else 'срок'}</span>")
        if subs:
            done = sum(1 for s in subs if s.done)
            meta.append(f"☑ {done}/{len(subs)}")
        if topic:
            meta.append(f"<span style='color:{topic_color(topic.color).name()}'>●</span> {topic.name}")
        if meta:
            m = w.label("", "caption", wrap=True)
            m.setTextFormat(Qt.RichText)
            m.setText(" &nbsp;·&nbsp; ".join(meta))
            lay.addWidget(m)


class ColumnList(QListWidget):
    """Список карточек колонки; принимает карточки из любой колонки этой доски."""

    def __init__(self, page: "BoardsPage", column: logic.BoardColumn):
        super().__init__()
        self.page = page
        self.column = column
        self.setObjectName("kanbanList")
        self.setAccessibleName(f"Колонка «{column.name}»")
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDropIndicatorShown(True)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setSpacing(3)
        self.setFrameShape(QFrame.NoFrame)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)
        self.itemDoubleClicked.connect(lambda it: page.open_card(it.data(Qt.UserRole)))
        self.currentItemChanged.connect(self._highlight)
        self.itemClicked.connect(lambda it: page.card_selected(it.data(Qt.UserRole)))
        QShortcut(QKeySequence(Qt.Key_Delete), self, activated=self._delete_current)
        QShortcut(QKeySequence(Qt.Key_Return), self, activated=self._open_current)

    def _highlight(self, cur, prev) -> None:
        from .theme import repolish
        for it, on in ((prev, False), (cur, True)):
            wdg = self.itemWidget(it) if it is not None else None
            if wdg is not None:
                wdg.setProperty("sel", "true" if on else "false")
                repolish(wdg)

    # ---- перетаскивание ----
    def mimeTypes(self):
        return [MIME]

    def mimeData(self, items):
        md = QMimeData()
        if items:
            md.setData(MIME, QByteArray(str(items[0].data(Qt.UserRole)).encode()))
        return md

    def supportedDropActions(self):
        return Qt.MoveAction

    def startDrag(self, _actions) -> None:
        item = self.currentItem()
        if item is None:
            return
        drag = QDrag(self)
        drag.setMimeData(self.mimeData([item]))
        wdg = self.itemWidget(item)
        if wdg is not None:
            pm = wdg.grab()
            drag.setPixmap(pm)
            drag.setHotSpot(pm.rect().center())
        drag.exec(Qt.MoveAction)

    def dropMimeData(self, index, data, action) -> bool:
        if not data.hasFormat(MIME):
            return False
        task_id = int(bytes(data.data(MIME)).decode())
        row = index if index >= 0 else self.count()
        # своя же карточка ниже по списку: её место ещё занято ею самой
        for i in range(min(row, self.count())):
            if self.item(i).data(Qt.UserRole) == task_id:
                row -= 1
                break
        # обновляем после того, как Qt закончит перетаскивание
        QTimer.singleShot(0, lambda: self.page.move_card(task_id, self.column.id, row))
        return False

    # ---- меню ----
    def _current_id(self):
        it = self.currentItem()
        return it.data(Qt.UserRole) if it else None

    def _open_current(self):
        if self._current_id() is not None:
            self.page.open_card(self._current_id())

    def _delete_current(self):
        if self._current_id() is not None:
            self.page.delete_card(self._current_id())

    def _menu(self, pos) -> None:
        it = self.itemAt(pos)
        if it is None:
            return
        tid = it.data(Qt.UserRole)
        m = QMenu(self)
        m.addAction("Открыть…", lambda: self.page.open_card(tid))
        move = m.addMenu("Переместить в")
        for c in self.page.columns:
            a = move.addAction(c.name, lambda cid=c.id: self.page.move_card(tid, cid, 0))
            a.setEnabled(c.id != self.column.id)
        other = [b for b in self.page.db.list_boards() if b.id != self.page.board_id]
        if other:
            to_board = m.addMenu("На другую доску")
            for b in other:
                to_board.addAction(b.name, lambda bid=b.id: self.page.move_to_board(tid, bid))
        to_tasks = m.addAction("Перенести в обычные задачи", lambda: self.page.move_to_tasks(tid))
        to_tasks.setToolTip("Карточка станет обычной задачей в разделе «Задачи»")
        m.addSeparator()
        m.addAction("Удалить", lambda: self.page.delete_card(tid))
        m.exec(self.viewport().mapToGlobal(pos))


class ColumnWidget(QFrame):
    def __init__(self, page: "BoardsPage", column: logic.BoardColumn, cards: list[logic.Task],
                 subs: dict, topics: dict, today: date):
        super().__init__()
        self.page = page
        self.column = column
        self.setObjectName("kanbanColumn")
        self.setFixedWidth(COLUMN_W)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 10, 8, 8)
        lay.setSpacing(6)
        head = QHBoxLayout()
        head.setContentsMargins(6, 0, 0, 0)
        name = w.label(column.name, "section")
        name.setToolTip("Двойной щелчок — переименовать")
        name.mouseDoubleClickEvent = lambda _e: page.rename_column(column)
        head.addWidget(name)
        cnt = w.label(str(len(cards)), "caption")
        head.addWidget(cnt)
        if column.is_done:
            done = w.label("✓", "caption")
            done.setToolTip("Колонка «готово»: карточки здесь считаются выполненными")
            head.addWidget(done)
        head.addStretch()
        more = w.menu_button(f"Действия с колонкой «{column.name}»")
        menu = QMenu(more)
        menu.addAction("Переименовать…", lambda: page.rename_column(column))
        a = menu.addAction("Колонка «готово»", lambda: page.set_done_column(column))
        a.setCheckable(True)
        a.setChecked(column.is_done)
        a.setToolTip("Карточки в этой колонке отмечаются выполненными")
        menu.addSeparator()
        menu.addAction("Сдвинуть влево", lambda: page.shift_column(column, -1))
        menu.addAction("Сдвинуть вправо", lambda: page.shift_column(column, 1))
        menu.addSeparator()
        menu.addAction("Удалить колонку…", lambda: page.delete_column(column))
        more.setMenu(menu)
        head.addWidget(more)
        lay.addLayout(head)

        self.list = ColumnList(page, column)
        for t in cards:
            it = QListWidgetItem()
            it.setData(Qt.UserRole, t.id)
            it.setToolTip(t.title)
            cw = CardWidget(t, subs.get(t.id, []), topics.get(t.topic_id), today)
            cw.setFixedWidth(COLUMN_W - 22)
            it.setSizeHint(QSize(COLUMN_W - 22, cw.sizeHint().height()))
            self.list.addItem(it)
            self.list.setItemWidget(it, cw)
        # новая карточка — сразу под заголовком, всегда на виду; Enter (или Ctrl+Enter) или кнопка «+»
        add_row = QHBoxLayout()
        add_row.setSpacing(4)
        self.add = QLineEdit()
        self.add.setObjectName("kanbanAdd")
        self.add.setPlaceholderText("Новая карточка…")
        self.add.setToolTip("Enter или Ctrl+Enter — добавить.\nМожно сразу со сроком и важностью: «Отчёт в пятницу !»")
        self.add.setAccessibleName(f"Новая карточка в колонке «{column.name}»")
        self.add.returnPressed.connect(self._add)
        for seq in ("Ctrl+Return", "Ctrl+Enter"):
            QShortcut(QKeySequence(seq), self.add, activated=self._add)
        self.add_btn = w.button("", "primary", "plus", "Добавить карточку (Enter)")
        self.add_btn.setFixedSize(32, 30)
        self.add_btn.setIcon(icons.icon("plus", theme["teal_text"]))
        self.add_btn.clicked.connect(self._add)
        add_row.addWidget(self.add, 1)
        add_row.addWidget(self.add_btn)
        lay.addLayout(add_row)
        lay.addWidget(self.list, 1)

    def _add(self) -> None:
        text = self.add.text().strip()
        if not text:
            return
        q = logic.parse_quick_task(text, self.page.db.list_topics(), date.today())
        if not q.title:
            return
        self.page.db.add_card(self.page.board_id, self.column.id, q.title, deadline=q.deadline,
                              priority=q.priority, topic_id=q.topic_id)
        self.page.refresh(focus_add=self.column.id)


# ---------------------------------------------------------------- карточка (справа)

class CardPanel(QWidget):
    """Выбранная карточка: описание и подзадачи — отмечаются и добавляются прямо здесь."""

    def __init__(self, page: "BoardsPage"):
        super().__init__()
        from .tasks_tab import SubtaskList
        self.page = page
        self.db = page.db
        self.task_id: int | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.title = w.label("", "section", wrap=True)
        self.title.setTextFormat(Qt.PlainText)
        self.meta = w.label("", "caption", wrap=True)
        self.desc = w.label("", "secondary", wrap=True)
        self.desc.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.desc.setTextFormat(Qt.PlainText)
        lay.addWidget(self.title)
        lay.addWidget(self.meta)
        lay.addWidget(self.desc)
        self.subs_title = w.label("Подзадачи", "section")
        lay.addWidget(self.subs_title)
        self.subs = SubtaskList(compact=True)
        self.subs.changed.connect(lambda: QTimer.singleShot(0, self._apply))
        lay.addWidget(self.subs)
        btns = QHBoxLayout()
        self.edit_btn = w.button("Изменить…", None, "edit")
        self.edit_btn.clicked.connect(lambda: self.page.open_card(self.task_id))
        self.done_btn = w.button("Готово", "primary", "check")
        self.done_btn.clicked.connect(self._toggle_done)
        btns.addWidget(self.edit_btn)
        btns.addWidget(self.done_btn)
        btns.addStretch()
        lay.addLayout(btns)
        lay.addStretch(1)
        self.show_task(None)

    def show_task(self, task_id: int | None) -> None:
        t = self.db.get_task(task_id) if task_id else None
        self.task_id = t.id if t else None
        for x in (self.meta, self.subs_title, self.subs, self.edit_btn, self.done_btn):
            x.setVisible(t is not None)
        if t is None:
            self.title.setText("Выберите карточку")
            self.desc.setText("Щёлкните по карточке, чтобы увидеть описание и разбить её на подзадачи. "
                              "Двойной щелчок — открыть целиком.")
            self.desc.show()
            return
        today = date.today()
        self.title.setText(t.title)
        col = next((c for c in self.page.columns if c.id == t.column_id), None)
        meta = [col.name if col else ""]
        if t.deadline:
            meta.append(f"срок {w.human_date(t.deadline, today)}" + ("" if t.done else f" · {logic.due_text(t.deadline, today)}"))
        meta.append("приоритет: " + logic.PRIORITY_NAMES[t.priority].lower())
        self.meta.setText(" · ".join(x for x in meta if x))
        self.desc.setText(t.description)
        self.desc.setVisible(bool(t.description))
        self.subs.set_entries([{"id": x.id, "title": x.title, "done": x.done} for x in self.db.subtasks(t.id)])
        self.done_btn.setText("Вернуть в работу" if t.done else "Готово")
        self.done_btn.setProperty("kind", None if t.done else "primary")
        from .theme import repolish
        repolish(self.done_btn)

    def _apply(self) -> None:
        if self.task_id is None or self.db.get_task(self.task_id) is None:
            return
        apply_subtasks(self.db, self.task_id, self.subs.entries())
        # новые подзадачи получили номера — без этого следующая правка создала бы дубли
        self.subs.set_entries([{"id": x.id, "title": x.title, "done": x.done} for x in self.db.subtasks(self.task_id)])
        self.page.refresh(keep_panel=True)

    def _toggle_done(self) -> None:
        t = self.db.get_task(self.task_id)
        if t:
            self.db.complete_task(t.id, not t.done)
            self.page.refresh()


# ---------------------------------------------------------------- заметки доски

class BoardNotes(QFrame):
    """Заметки этой доски: список сверху, текст снизу; сохраняются сами."""

    def __init__(self, page: "BoardsPage"):
        super().__init__()
        self.page = page
        self.db = page.db
        self.current: int | None = None
        self._loading = False
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(600)
        self.timer.timeout.connect(self.flush)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        head = QHBoxLayout()
        head.addStretch()
        add = w.button("", "ghost", "plus", "Новая заметка")
        add.setFixedSize(30, 28)
        add.clicked.connect(self.new_note)
        head.addWidget(add)
        lay.addLayout(head)
        self.list = QListWidget()
        self.list.setObjectName("noteList")
        self.list.setAccessibleName("Заметки доски")
        self.list.currentItemChanged.connect(self._select)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        lay.addWidget(self.list)
        self.title = QLineEdit()
        self.title.setObjectName("noteTitle")
        self.title.setPlaceholderText("Название")
        self.title.textEdited.connect(self._changed)
        self.body = QPlainTextEdit()
        self.body.setObjectName("noteBody")
        self.body.setPlaceholderText("Договорённости, ссылки, мысли по работе… Сохраняется само.")
        self.body.textChanged.connect(self._changed)
        lay.addWidget(self.title)
        lay.addWidget(self.body, 1)
        # пустое состояние — сверху, под заголовком (а не посередине панели)
        self.empty_box = QWidget()
        el = QVBoxLayout(self.empty_box)
        el.setContentsMargins(0, 4, 0, 0)
        el.setSpacing(8)
        el.addWidget(w.label("Заметки только этой доски: договорённости, контакты, идеи по работе.", "secondary", wrap=True))
        first = w.button("Новая заметка", None, "plus")
        first.clicked.connect(self.new_note)
        el.addWidget(first, 0, Qt.AlignLeft)
        el.addStretch(1)
        lay.addWidget(self.empty_box, 1)

    def load(self) -> None:
        self.flush()
        notes = logic.sort_notes(self.db.list_notes(board_id=self.page.board_id))
        self._loading = True
        self.list.clear()
        for n in notes:
            it = QListWidgetItem(("📌 " if n.pinned else "") + n.display_title)
            it.setData(Qt.UserRole, n.id)
            self.list.addItem(it)
        ids = [n.id for n in notes]
        if self.current not in ids:
            self.current = ids[0] if ids else None
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.UserRole) == self.current:
                self.list.setCurrentRow(i)
        self._loading = False
        self._show()

    def _show(self) -> None:
        note = self.db.get_note(self.current) if self.current else None
        self._loading = True
        self.title.setText(note.title if note else "")
        self.body.setPlainText(note.body if note else "")
        self._loading = False
        for x in (self.title, self.body):
            x.setVisible(note is not None)
        self.list.setVisible(self.list.count() > 0)
        self.empty_box.setVisible(note is None and self.list.count() == 0)
        self.list.setFixedHeight(min(170, self.list.count() * 34 + 10))

    def _select(self, item, _prev=None) -> None:
        if self._loading or item is None:
            return
        self.flush()
        self.current = item.data(Qt.UserRole)
        self._show()

    def _changed(self) -> None:
        if not self._loading and self.current is not None:
            self.timer.start()

    def flush(self) -> None:
        self.timer.stop()
        if self.current is None or self.page.board_id is None:
            return
        note = self.db.get_note(self.current)
        if note and (note.title != self.title.text().strip() or note.body != self.body.toPlainText()):
            self.db.update_note(self.current, self.title.text().strip(), self.body.toPlainText())
            for i in range(self.list.count()):
                it = self.list.item(i)
                if it.data(Qt.UserRole) == self.current:
                    n = self.db.get_note(self.current)
                    it.setText(("📌 " if n.pinned else "") + n.display_title)

    def new_note(self) -> None:
        if self.page.board_id is None:
            return
        self.flush()
        self.current = self.db.add_note(board_id=self.page.board_id)
        self.load()
        self.title.setFocus()

    def _menu(self, pos) -> None:
        it = self.list.itemAt(pos)
        if it is None:
            return
        nid = it.data(Qt.UserRole)
        n = self.db.get_note(nid)
        m = QMenu(self)
        m.addAction("Открепить" if n.pinned else "Закрепить", lambda: (self.db.set_note_pinned(nid, not n.pinned),
                                                                        self.load()))
        m.addAction("Удалить", lambda: self._delete(nid))
        m.exec(self.list.viewport().mapToGlobal(pos))

    def _delete(self, nid: int) -> None:
        n = self.db.get_note(nid)
        if w.confirm(self, "Удалить заметку", f"Удалить «{n.display_title}»?", "Это нельзя отменить."):
            if self.current == nid:
                self.current = None
            self.db.delete_note(nid)
            self.load()


# ---------------------------------------------------------------- страница

class BoardsPage(w.Page):
    def __init__(self, db: Database, navigate=None):
        super().__init__("Доски", scroll=False)
        self.db = db
        self.navigate = navigate
        self.columns: list[logic.BoardColumn] = []
        try:
            self.board_id: int | None = int(db.get_pref("board_current", "0")) or None
        except ValueError:
            self.board_id = None

        self.notes_btn = w.button("Панель", None, "notes", "Показать или скрыть панель справа: карточка и заметки доски")
        self.notes_btn.setCheckable(True)
        self.notes_btn.setChecked(db.get_pref("board_notes", "1") == "1")
        self.notes_btn.toggled.connect(self._toggle_notes)
        self.header.add_action(self.notes_btn)
        new_btn = w.button("Новая доска", "primary", "plus", "Новая доска — например, для второй работы")
        new_btn.clicked.connect(self.new_board)
        self.header.add_action(new_btn)

        top = QHBoxLayout()
        top.setSpacing(6)
        self.board_strip = w.ChipStrip()
        self.board_group = QButtonGroup(self)
        self.board_group.setExclusive(True)
        self.board_group.buttonClicked.connect(lambda b: self.select_board(b.property("value")))
        top.addWidget(self.board_strip, 1)
        self.board_more = w.menu_button("Действия с доской")
        bm = QMenu(self.board_more)
        bm.addAction("Переименовать…", self.rename_board)
        bm.addAction("Цвет…", self.recolor_board)
        bm.addAction("Новая колонка…", self.add_column)
        bm.addSeparator()
        bm.addAction("В архив", self.archive_board)
        bm.addAction("Удалить доску…", self.delete_board)
        self.board_more.setMenu(bm)
        top.addWidget(self.board_more)
        self.content.addLayout(top)

        self.split = QSplitter(Qt.Horizontal)
        self.split.setObjectName("pageSplit")
        self.split.setHandleWidth(8)
        self.kanban = QScrollArea()
        self.kanban.setObjectName("kanbanArea")
        self.kanban.setWidgetResizable(True)
        self.kanban.setFrameShape(QFrame.NoFrame)
        self.kanban.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        holder = QWidget()
        holder.setObjectName("kanbanHolder")
        self.cols_row = QHBoxLayout(holder)
        self.cols_row.setContentsMargins(0, 0, 0, 4)
        self.cols_row.setSpacing(10)
        self.kanban.setWidget(holder)
        self.split.addWidget(self.kanban)
        self.side = QFrame()
        self.side.setObjectName("card")
        self.side.setMinimumWidth(260)
        sl = QVBoxLayout(self.side)
        sl.setContentsMargins(14, 12, 14, 12)
        sl.setSpacing(10)
        seg = QHBoxLayout()
        seg.setSpacing(6)
        self.side_group = QButtonGroup(self)
        self.side_group.setExclusive(True)
        from PySide6.QtWidgets import QStackedWidget
        self.side_stack = QStackedWidget()
        self.card_panel = CardPanel(self)
        self.notes = BoardNotes(self)
        self.side_stack.addWidget(self.card_panel)
        self.side_stack.addWidget(self.notes)
        for i, name in enumerate(("Карточка", "Заметки доски")):
            c = w.chip(name, i == 0)
            c.setProperty("value", i)
            self.side_group.addButton(c)
            seg.addWidget(c)
        seg.addStretch()
        self.side_group.buttonClicked.connect(lambda b: self._side_tab(b.property("value")))
        sl.addLayout(seg)
        sl.addWidget(self.side_stack, 1)
        self.split.addWidget(self.side)
        self.split.setStretchFactor(0, 1)
        self.split.setCollapsible(0, False)
        w.remember_splitter(self.split, db, "split_boards", [800, 320])
        self.content.addWidget(self.split, 1)

        self.empty = QWidget()
        el = QVBoxLayout(self.empty)
        el.setAlignment(Qt.AlignCenter)
        txt = w.label("Доски — для отдельных областей: например, «Работа 1» и «Работа 2».\n"
                      "Каждая доска — свои колонки (К выполнению → В работе → Готово),\n"
                      "карточки перетаскиваются мышью, и у доски свои заметки.", "empty", wrap=True)
        txt.setAlignment(Qt.AlignCenter)
        el.addWidget(txt)
        row = QHBoxLayout()
        row.addStretch()
        b1 = w.button("Создать доску", "primary", "plus")
        b1.clicked.connect(self.new_board)
        b2 = w.button("Две доски для двух работ")
        b2.clicked.connect(self._two_jobs)
        row.addWidget(b1)
        row.addWidget(b2)
        row.addStretch()
        el.addLayout(row)
        self.content.addWidget(self.empty, 1)
        self._toggle_notes(self.notes_btn.isChecked(), save=False)

    # ---- доски ----
    def _boards(self):
        return self.db.list_boards()

    def select_board(self, board_id: int) -> None:
        self.notes.flush()
        self.board_id = board_id
        self.db.set_pref("board_current", str(board_id))
        self.refresh()

    def new_board(self) -> None:
        name, ok = QInputDialog.getText(self, "Новая доска", "Название (например, «Работа в N»):")
        if ok and name.strip():
            color = BOARD_COLORS[len(self.db.list_boards(include_archived=True)) % len(BOARD_COLORS)]
            self.select_board(self.db.add_board(name.strip(), color))

    def new_item(self) -> None:
        """Ctrl+N — новая карточка в первой колонке."""
        if self.board_id is None:
            return self.new_board()
        cols = self.cols_row
        for i in range(cols.count()):
            wdg = cols.itemAt(i).widget()
            if isinstance(wdg, ColumnWidget):
                wdg.add.setFocus()
                return

    def _two_jobs(self) -> None:
        a = self.db.add_board("Работа 1", BOARD_COLORS[1])
        self.db.add_board("Работа 2", BOARD_COLORS[2])
        self.select_board(a)

    def _board(self) -> logic.Board | None:
        return next((b for b in self.db.list_boards(include_archived=True) if b.id == self.board_id), None)

    def rename_board(self) -> None:
        b = self._board()
        if b is None:
            return
        name, ok = QInputDialog.getText(self, "Переименовать доску", "Название:", text=b.name)
        if ok and name.strip():
            b.name = name.strip()
            self.db.update_board(b)
            self.refresh()

    def recolor_board(self) -> None:
        b = self._board()
        if b is None:
            return
        from PySide6.QtGui import QColor
        c = QColorDialog.getColor(QColor(b.color), self, "Цвет доски")
        if c.isValid():
            b.color = c.name().upper()
            self.db.update_board(b)
            self.refresh()

    def archive_board(self) -> None:
        b = self._board()
        if b is None:
            return
        b.archived = True
        self.db.update_board(b)
        self.board_id = None
        self.refresh()

    def delete_board(self) -> None:
        b = self._board()
        if b is None:
            return
        n = len(self.db.list_tasks(board_id=b.id))
        if w.confirm(self, "Удалить доску",
                     f"Удалить доску «{b.name}» вместе с {n} "
                     f"{logic.plural(n, 'карточкой', 'карточками', 'карточками')} и её заметками?",
                     "Это нельзя отменить. Чтобы просто убрать доску — отправьте её в архив."):
            self.db.delete_board(b.id)
            self.board_id = None
            self.refresh()

    # ---- колонки ----
    def add_column(self) -> None:
        if self.board_id is None:
            return
        name, ok = QInputDialog.getText(self, "Новая колонка", "Название (например, «На проверке»):")
        if ok and name.strip():
            done = next((c for c in self.columns if c.is_done), None)
            cid = self.db.add_column(self.board_id, name.strip())
            if done is not None:      # новую колонку ставим перед «Готово»
                ids = [c.id for c in self.columns if c.id != done.id] + [cid, done.id]
                self.db.reorder_columns(self.board_id, ids)
            self.refresh()

    def rename_column(self, c: logic.BoardColumn) -> None:
        name, ok = QInputDialog.getText(self, "Колонка", "Название:", text=c.name)
        if ok and name.strip():
            c.name = name.strip()
            self.db.update_column(c)
            self.refresh()

    def set_done_column(self, c: logic.BoardColumn) -> None:
        c.is_done = not c.is_done
        self.db.update_column(c)
        self.refresh()

    def shift_column(self, c: logic.BoardColumn, step: int) -> None:
        ids = [x.id for x in self.columns]
        i = ids.index(c.id)
        j = max(0, min(len(ids) - 1, i + step))
        ids[i], ids[j] = ids[j], ids[i]
        self.db.reorder_columns(self.board_id, ids)
        self.refresh()

    def delete_column(self, c: logic.BoardColumn) -> None:
        others = [x for x in self.columns if x.id != c.id]
        cards = self.db.cards_in(c.id)
        if not others:
            QMessageBox.information(self, "Колонка", "У доски должна остаться хотя бы одна колонка.")
            return
        if cards:
            names = [x.name for x in others]
            choice, ok = QInputDialog.getItem(self, "Удалить колонку",
                                              f"В колонке {len(cards)} "
                                              f"{logic.plural(len(cards), 'карточка', 'карточки', 'карточек')}. "
                                              "Куда их переложить?", names, 0, False)
            if not ok:
                return
            target = others[names.index(choice)].id
        else:
            target = None
        self.db.delete_column(c.id, target)
        self.refresh()

    # ---- карточки ----
    def move_card(self, task_id: int, column_id: int, index: int) -> None:
        self.db.move_card(task_id, column_id, index)
        self.refresh()

    def move_to_board(self, task_id: int, board_id: int) -> None:
        cols = self.db.list_columns(board_id)
        if not cols:
            return
        t = self.db.get_task(task_id)
        t.board_id = board_id
        target = next((c for c in cols if c.is_done), cols[0]) if t.done else cols[0]
        t.column_id = target.id
        self.db.update_task(t)
        self.db.move_card(task_id, target.id, 0)
        self.refresh()

    def move_to_tasks(self, task_id: int) -> None:
        t = self.db.get_task(task_id)
        t.board_id = t.column_id = None
        self.db.update_task(t)
        self.refresh()

    def delete_card(self, task_id: int) -> None:
        t = self.db.get_task(task_id)
        if t and w.confirm(self, "Удалить карточку", f"Удалить «{t.title}»?",
                           "Вместе с подзадачами. Это нельзя отменить."):
            self.db.delete_task(task_id)
            self.refresh()

    def open_card(self, task_id: int) -> None:
        t = self.db.get_task(task_id)
        if t is None:
            return
        dlg = TaskDialog(self, self.db.list_topics(), t, subtasks=self.db.subtasks(task_id))
        dlg.setWindowTitle("Карточка")
        if dlg.exec() == QDialog.Accepted:
            subs = dlg.result_subtasks()
            new = dlg.result_task()
            self.db.update_task(new)
            apply_subtasks(self.db, task_id, subs)
            if new.done != t.done:      # «Выполнена» в окне — переложить в «Готово» или обратно
                self.db.complete_task(task_id, new.done)
        self.refresh()

    def focus_item(self, task_id: int | None = None, board_id: int | None = None) -> None:
        if task_id is not None:
            t = self.db.get_task(task_id)
            if t and t.board_id:
                self.board_id = t.board_id
                self.refresh()
                self.open_card(task_id)
        elif board_id is not None:
            self.select_board(board_id)

    def _side_tab(self, i: int) -> None:
        self.side_stack.setCurrentIndex(i)
        for b in self.side_group.buttons():
            b.setChecked(b.property("value") == i)

    def card_selected(self, task_id: int | None) -> None:
        self.selected = task_id
        for cw in (self.cols_row.itemAt(i).widget() for i in range(self.cols_row.count())):
            if isinstance(cw, ColumnWidget):          # подсветка — только у одной карточки на доске
                cur = cw.list.currentItem()
                if cur is not None and cur.data(Qt.UserRole) != task_id:
                    cw.list._highlight(None, cur)
                    cw.list.blockSignals(True)
                    cw.list.setCurrentRow(-1)
                    cw.list.blockSignals(False)
        self.card_panel.show_task(task_id)
        if task_id is not None:
            self._side_tab(0)

    def _toggle_notes(self, on: bool, save: bool = True) -> None:
        self.side.setVisible(on)
        if save:
            self.db.set_pref("board_notes", "1" if on else "0")

    def flush(self) -> None:
        self.notes.flush()

    # ---- отрисовка ----
    def refresh(self, focus_add: int | None = None, keep_panel: bool = False) -> None:
        boards = self._boards()
        if self.board_id not in {b.id for b in boards}:
            self.board_id = boards[0].id if boards else None
        has = self.board_id is not None
        self.split.setVisible(has)
        self.board_more.setVisible(has)
        self.notes_btn.setVisible(has)
        self.empty.setVisible(not has)

        for b in self.board_group.buttons():
            self.board_group.removeButton(b)
        self.board_strip.clear()
        for b in boards:
            n = sum(1 for t in self.db.list_tasks(board_id=b.id) if not t.done and not t.archived)
            c = w.chip(f"{b.name} {n}" if n else b.name, b.id == self.board_id)
            c.setProperty("value", b.id)
            c.setIcon(w.dot_icon(b.color))
            c.setIconSize(QSize(10, 10))
            self.board_group.addButton(c)
            self.board_strip.addWidget(c)
        self.board_strip.addStretch()

        hscroll = self.kanban.horizontalScrollBar().value()
        w.clear_layout(self.cols_row)
        if not has:
            self.header.set_subtitle("")
            return
        today = date.today()
        self.columns = self.db.list_columns(self.board_id)
        subs = self.db.all_subtasks()
        topics = {t.id: t for t in self.db.list_topics()}
        tasks = self.db.list_tasks(board_id=self.board_id)
        by_col: dict[int, list] = {}
        first = self.columns[0].id if self.columns else None
        for t in tasks:
            col = t.column_id if any(c.id == t.column_id for c in self.columns) else first
            by_col.setdefault(col, []).append(t)
        for c in self.columns:
            cards = sorted(by_col.get(c.id, []), key=lambda t: (t.position, t.id))
            cw = ColumnWidget(self, c, cards, subs, topics, today)
            self.cols_row.addWidget(cw)
            if focus_add == c.id:
                QTimer.singleShot(0, cw.add.setFocus)
        add_col = w.button("Колонка", "ghost", "plus", "Новая колонка")
        add_col.clicked.connect(self.add_column)
        self.cols_row.addWidget(add_col, 0, Qt.AlignTop)
        self.cols_row.addStretch()
        QTimer.singleShot(0, lambda: self.kanban.horizontalScrollBar().setValue(hscroll))
        open_n = sum(1 for t in tasks if not t.done)
        overdue = sum(1 for t in tasks if logic.is_overdue(t, today))
        sub = f"{open_n} {logic.plural(open_n, 'открытая карточка', 'открытые карточки', 'открытых карточек')}"
        if overdue:
            sub += f" · {overdue} просрочено"
        self.header.set_subtitle(sub)
        self.notes.load()
        sel = getattr(self, "selected", None)
        if sel is not None and self.db.get_task(sel) is None:
            sel = None
        if sel is not None:          # выделение карточки сохраняется после перерисовки
            for cw in (self.cols_row.itemAt(i).widget() for i in range(self.cols_row.count())):
                if isinstance(cw, ColumnWidget):
                    for k in range(cw.list.count()):
                        if cw.list.item(k).data(Qt.UserRole) == sel:
                            cw.list.blockSignals(True)
                            cw.list.setCurrentRow(k)
                            cw.list._highlight(cw.list.item(k), None)
                            cw.list.blockSignals(False)
        if not keep_panel:
            self.card_panel.show_task(sel)
