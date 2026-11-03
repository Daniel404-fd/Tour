from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QBrush, QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QDateEdit, QDialog, QDialogButtonBox,
    QFormLayout, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMenu, QMessageBox, QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from .. import logic
from ..db import Database
from . import widgets as w
from .theme import theme, topic_color

STATUS_FILTERS = [("Активные", logic.FILTER_ACTIVE), ("Выполненные", logic.FILTER_DONE),
                  ("Все", logic.FILTER_ALL), ("Архив", logic.FILTER_ARCHIVED)]


def _dialog_buttons(dlg: QDialog, ok_text: str) -> QDialogButtonBox:
    buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
    ok = buttons.button(QDialogButtonBox.Ok)
    ok.setText(ok_text)
    ok.setProperty("kind", "primary")
    ok.setDefault(True)
    buttons.button(QDialogButtonBox.Cancel).setText("Отмена")
    buttons.accepted.connect(dlg.accept)
    buttons.rejected.connect(dlg.reject)
    return buttons


# ---------------------------------------------------------------- подзадачи

class SubtaskList(QWidget):
    """Список подзадач: галочка — выполнено, двойной щелчок — переименовать, Delete — удалить."""

    changed = Signal()

    def __init__(self, entries: list[dict] | None = None, compact: bool = False):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.progress = w.label("", "caption")
        lay.addWidget(self.progress)
        self.list = QListWidget()
        self.list.setObjectName("subtasks")
        self.list.setAccessibleName("Подзадачи")
        self.list.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.list.setDragDropMode(QAbstractItemView.InternalMove)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        self.compact = compact
        self.list.setMinimumHeight(60 if compact else 90)
        lay.addWidget(self.list, 0 if compact else 1)
        add_row = QHBoxLayout()
        add_row.setSpacing(6)
        self.add_edit = QLineEdit()
        self.add_edit.setPlaceholderText("Новая подзадача")
        self.add_edit.setToolTip("Введите и нажмите Enter")
        self.add_edit.setAccessibleName("Новая подзадача")
        self.add_edit.returnPressed.connect(self._add)
        add_btn = w.button("", "ghost", "plus", "Добавить подзадачу")
        add_btn.setFixedSize(32, 30)
        add_btn.clicked.connect(self._add)
        add_row.addWidget(self.add_edit, 1)
        add_row.addWidget(add_btn)
        lay.addLayout(add_row)
        QShortcut(QKeySequence(Qt.Key_Delete), self.list, activated=self._delete_current)
        self._loading = False
        self.set_entries(entries or [])
        self.list.itemChanged.connect(self._item_changed)
        self.list.model().rowsMoved.connect(lambda *_: self._emit())

    def set_entries(self, entries: list[dict]) -> None:
        self._loading = True
        self.list.clear()
        for e in entries:
            self._append(e)
        self._loading = False
        self._update_progress()

    def _append(self, e: dict) -> None:
        item = QListWidgetItem(e["title"])
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsEditable | Qt.ItemIsDragEnabled)
        item.setFlags(item.flags() & ~Qt.ItemIsDropEnabled)
        item.setCheckState(Qt.Checked if e.get("done") else Qt.Unchecked)
        item.setData(Qt.UserRole, e.get("id", 0))
        self._style(item)
        self.list.addItem(item)

    def _style(self, item: QListWidgetItem) -> None:
        f = item.font()
        f.setStrikeOut(item.checkState() == Qt.Checked)
        item.setFont(f)
        item.setForeground(QBrush(theme.color("text3" if item.checkState() == Qt.Checked else "text")))

    def entries(self) -> list[dict]:
        out = []
        for i in range(self.list.count()):
            it = self.list.item(i)
            title = it.text().strip()
            if title:
                out.append({"id": it.data(Qt.UserRole) or 0, "title": title, "done": it.checkState() == Qt.Checked})
        return out

    def _update_progress(self) -> None:
        e = self.entries()
        done = sum(1 for x in e if x["done"])
        self.progress.setText(f"Выполнено {done} из {len(e)}" if e else "Разбейте задачу на шаги — так проще начать.")
        if self.compact:   # в карточке список растёт по содержимому, а не занимает всю высоту
            rows = max(2, min(12, self.list.count()))
            self.list.setFixedHeight(rows * 30 + 8)

    def _emit(self) -> None:
        if not self._loading:
            self._update_progress()
            self.changed.emit()

    def _item_changed(self, item: QListWidgetItem) -> None:
        if self._loading:
            return
        self._loading = True
        self._style(item)
        self._loading = False
        self._emit()

    def _add(self) -> None:
        title = self.add_edit.text().strip()
        if not title:
            return
        self._loading = True
        self._append({"id": 0, "title": title, "done": False})
        self._loading = False
        self.add_edit.clear()
        self._emit()

    def _delete_current(self) -> None:
        row = self.list.currentRow()
        if row >= 0:
            self.list.takeItem(row)
            self._emit()

    def _menu(self, pos) -> None:
        item = self.list.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        menu.addAction("Переименовать", lambda: self.list.editItem(item))
        menu.addAction("Удалить", lambda: (self.list.setCurrentItem(item), self._delete_current()))
        menu.exec(self.list.viewport().mapToGlobal(pos))


def apply_subtasks(db: Database, task_id: int, entries: list[dict]) -> None:
    """Привести подзадачи задачи к списку entries (id=0 — новая), включая порядок."""
    existing = {s.id: s for s in db.subtasks(task_id)}
    keep = {e["id"] for e in entries if e["id"]}
    for sid in existing:
        if sid not in keep:
            db.delete_subtask(sid)
    for pos, e in enumerate(entries):
        sid = e["id"]
        if sid and sid in existing:
            cur = existing[sid]
            if cur.title != e["title"]:
                db.rename_subtask(sid, e["title"])
            if cur.done != e["done"]:
                db.set_subtask_done(sid, e["done"])
            if cur.position != pos:
                db.set_subtask_position(sid, pos)
        else:
            sid = db.add_subtask(task_id, e["title"])
            if e["done"]:
                db.set_subtask_done(sid, True)
            db.set_subtask_position(sid, pos)


# ---------------------------------------------------------------- диалог задачи

class TaskDialog(QDialog):
    def __init__(self, parent: QWidget, topics: list[logic.Topic], task: logic.Task | None = None,
                 default_topic: int | None = None, subtasks: list | None = None):
        super().__init__(parent)
        self.setWindowTitle("Задача" if task else "Новая задача")
        self.setMinimumWidth(460)
        self.task = task or logic.Task(0, "", topic_id=default_topic)
        form = QFormLayout(self)
        form.setContentsMargins(20, 20, 20, 16)
        form.setVerticalSpacing(12)
        form.setHorizontalSpacing(14)

        self.title_edit = QLineEdit(self.task.title)
        self.title_edit.setPlaceholderText("Что нужно сделать")
        self.error = w.label("", "danger")
        self.error.hide()
        self.desc_edit = QPlainTextEdit(self.task.description)
        self.desc_edit.setPlaceholderText("Подробности — необязательно")
        self.desc_edit.setFixedHeight(90)

        self.topic = QComboBox()
        self.topic.addItem("Без темы", None)
        for t in topics:
            self.topic.addItem(w.dot_icon(t.color), t.name, t.id)
        idx = self.topic.findData(self.task.topic_id)
        self.topic.setCurrentIndex(max(idx, 0))

        self.has_deadline = QCheckBox("Есть срок")
        self.deadline_edit = QDateEdit()
        self.deadline_edit.setCalendarPopup(True)
        self.deadline_edit.setDisplayFormat("dd.MM.yyyy")
        d = self.task.deadline or date.today()
        self.deadline_edit.setDate(QDate(d.year, d.month, d.day))
        self.has_deadline.setChecked(self.task.deadline is not None)
        self.deadline_edit.setEnabled(self.task.deadline is not None)
        self.has_deadline.toggled.connect(self.deadline_edit.setEnabled)
        deadline_row = QHBoxLayout()
        deadline_row.addWidget(self.has_deadline)
        deadline_row.addWidget(self.deadline_edit, 1)

        self.priority = QComboBox()
        for value, name in logic.PRIORITY_NAMES.items():
            self.priority.addItem(name, value)
        self.priority.setCurrentIndex(self.priority.findData(self.task.priority))

        self.done_box = QCheckBox("Выполнена")
        self.done_box.setChecked(self.task.done)

        form.addRow("Название", self.title_edit)
        form.addRow("", self.error)
        form.addRow("Описание", self.desc_edit)
        form.addRow("Тема", self.topic)
        form.addRow("Срок", deadline_row)
        form.addRow("Приоритет", self.priority)
        self.subtasks = SubtaskList([{"id": x.id, "title": x.title, "done": x.done} for x in (subtasks or [])])
        form.addRow("Подзадачи", self.subtasks)
        form.addRow("", self.done_box)
        form.addRow(_dialog_buttons(self, "Сохранить"))
        self.title_edit.textChanged.connect(lambda: self.error.hide())

    def accept(self) -> None:
        if not self.title_edit.text().strip():
            self.error.setText("Введите название задачи.")
            self.error.show()
            self.title_edit.setFocus()
            return
        super().accept()

    def result_subtasks(self) -> list[dict]:
        pending = self.subtasks.add_edit.text().strip()   # набрали, но не нажали Enter — тоже сохраняем
        if pending:
            self.subtasks._add()
        return self.subtasks.entries()

    def result_task(self) -> logic.Task:
        qd = self.deadline_edit.date()
        done = self.done_box.isChecked()
        return logic.Task(
            id=self.task.id,
            title=self.title_edit.text().strip(),
            description=self.desc_edit.toPlainText().strip(),
            deadline=date(qd.year(), qd.month(), qd.day()) if self.has_deadline.isChecked() else None,
            priority=int(self.priority.currentData()),
            done=done,
            completed_on=self.task.completed_on if (done and self.task.done) else None,
            archived=self.task.archived,
            topic_id=self.topic.currentData(),
        )


# ---------------------------------------------------------------- темы

class TopicEditDialog(QDialog):
    def __init__(self, parent: QWidget, topic: logic.Topic | None = None, used: set[str] = frozenset()):
        super().__init__(parent)
        self.setWindowTitle("Тема" if topic else "Новая тема")
        self.setMinimumWidth(380)
        self.used = {u.lower() for u in used}
        self.original = topic.name.lower() if topic else None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 16)
        lay.setSpacing(10)
        lay.addWidget(w.label("Название", "secondary"))
        self.name = QLineEdit(topic.name if topic else "")
        self.name.setPlaceholderText("Например, «Дом», «Работа», «Учёба»")
        lay.addWidget(self.name)
        self.error = w.label("", "danger")
        self.error.hide()
        lay.addWidget(self.error)
        lay.addWidget(w.label("Цвет метки", "secondary"))
        row = QHBoxLayout()
        row.setSpacing(8)
        self.colors = QButtonGroup(self)
        current = topic.color if topic else logic.TOPIC_COLORS[0]
        for i, c in enumerate(logic.TOPIC_COLORS):
            b = QPushButton()
            b.setCheckable(True)
            b.setFixedSize(30, 30)
            b.setCursor(Qt.PointingHandCursor)
            b.setAccessibleName(f"Цвет {i + 1}")
            col = topic_color(c).name()
            b.setStyleSheet(
                f"QPushButton {{ background: {col}; border-radius: 15px; border: 2px solid {col}; }}"
                f"QPushButton:checked {{ border: 3px solid {theme['text']}; }}")
            b.setProperty("hex", c)
            b.setChecked(c.lower() == current.lower())
            self.colors.addButton(b)
            row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)
        lay.addSpacing(6)
        lay.addWidget(_dialog_buttons(self, "Сохранить"))

    def accept(self) -> None:
        name = self.name.text().strip()
        msg = ""
        if not name:
            msg = "Введите название темы."
        elif name.lower() in self.used and name.lower() != self.original:
            msg = f"Тема «{name}» уже есть."
        if msg:
            self.error.setText(msg)
            self.error.show()
            self.name.setFocus()
            return
        super().accept()

    def value(self) -> tuple[str, str]:
        btn = self.colors.checkedButton()
        return self.name.text().strip(), (btn.property("hex") if btn else logic.TOPIC_COLORS[0])


class TopicsDialog(QDialog):
    """Управление темами: добавить, изменить, удалить."""

    def __init__(self, parent: QWidget, db: Database):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Темы задач")
        self.setMinimumSize(440, 380)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 16)
        lay.setSpacing(10)
        lay.addWidget(w.label("Темы помогают разделить задачи по сферам жизни. "
                              "Задачу можно отнести к одной теме.", "secondary", wrap=True))
        body = QHBoxLayout()
        self.list = QListWidget()
        self.list.setIconSize(QSize(12, 12))
        self.list.itemDoubleClicked.connect(lambda *_: self.edit())
        body.addWidget(self.list, 1)
        side = QVBoxLayout()
        add = w.button("Добавить…", "primary", "plus")
        add.clicked.connect(self.add)
        self.edit_btn = w.button("Изменить…")
        self.edit_btn.clicked.connect(self.edit)
        self.del_btn = w.button("Удалить…", "danger")
        self.del_btn.clicked.connect(self.delete)
        for b in (add, self.edit_btn, self.del_btn):
            side.addWidget(b)
        side.addStretch()
        body.addLayout(side)
        lay.addLayout(body, 1)
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.button(QDialogButtonBox.Close).setText("Готово")
        close.rejected.connect(self.accept)
        lay.addWidget(close)
        self.list.currentRowChanged.connect(self._update_buttons)
        self.reload()

    def reload(self, select_id: int | None = None) -> None:
        self.list.clear()
        counts: dict[int, int] = {}
        for t in self.db.list_tasks():
            if t.topic_id and not t.archived:
                counts[t.topic_id] = counts.get(t.topic_id, 0) + 1
        for t in self.db.list_topics():
            n = counts.get(t.id, 0)
            item = QListWidgetItem(w.dot_icon(t.color, 12),
                                   f"{t.name}  ·  {n} {logic.plural(n, 'задача', 'задачи', 'задач')}")
            item.setData(Qt.UserRole, t)
            self.list.addItem(item)
            if t.id == select_id:
                self.list.setCurrentItem(item)
        if self.list.count() and self.list.currentRow() < 0:
            self.list.setCurrentRow(0)
        self._update_buttons()

    def _update_buttons(self) -> None:
        has = self.list.currentItem() is not None
        self.edit_btn.setEnabled(has)
        self.del_btn.setEnabled(has)

    def _names(self) -> set[str]:
        return {t.name for t in self.db.list_topics()}

    def add(self) -> None:
        dlg = TopicEditDialog(self, used=self._names())
        if dlg.exec() == QDialog.Accepted:
            name, color = dlg.value()
            self.reload(self.db.add_topic(name, color))

    def edit(self) -> None:
        item = self.list.currentItem()
        if not item:
            return
        topic: logic.Topic = item.data(Qt.UserRole)
        dlg = TopicEditDialog(self, topic, used=self._names())
        if dlg.exec() == QDialog.Accepted:
            topic.name, topic.color = dlg.value()
            self.db.update_topic(topic)
            self.reload(topic.id)

    def delete(self) -> None:
        item = self.list.currentItem()
        if not item:
            return
        topic: logic.Topic = item.data(Qt.UserRole)
        box = QMessageBox(QMessageBox.Question, "Удалить тему", f"Удалить тему «{topic.name}»?",
                          parent=self)
        box.setInformativeText("Задачи этой темы не удалятся — они станут «без темы».")
        yes = box.addButton("Удалить", QMessageBox.DestructiveRole)
        box.addButton("Отмена", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is yes:
            self.db.delete_topic(topic.id)
            self.reload()


# ---------------------------------------------------------------- страница

class TasksPage(w.Page):
    COLUMNS = ["Задача", "Шаги", "Тема", "Срок", "Приоритет"]

    def __init__(self, db: Database, navigate=None):
        super().__init__("Задачи", scroll=False)
        self.db = db
        self.status = logic.FILTER_ACTIVE
        try:
            self.topic_filter = int(db.get_pref("tasks_topic", str(logic.TOPIC_ALL)))
        except ValueError:
            self.topic_filter = logic.TOPIC_ALL

        topics_btn = w.button("Темы…", None, "tag", "Добавить, переименовать или удалить темы")
        topics_btn.clicked.connect(self.manage_topics)
        new_btn = w.button("Новая задача", "primary", "plus", "Новая задача (Ctrl+N)")
        new_btn.clicked.connect(self.new_item)
        self.header.add_action(topics_btn)
        self.header.add_action(new_btn)

        # фильтры: статус и тема
        filters = QHBoxLayout()
        filters.setSpacing(6)
        self.status_group = QButtonGroup(self)
        self.status_group.setExclusive(True)
        for name, value in STATUS_FILTERS:
            c = w.chip(name, value == self.status)
            c.setProperty("value", value)
            self.status_group.addButton(c)
            filters.addWidget(c)
        self.status_group.buttonClicked.connect(self._status_changed)
        filters.addStretch()
        self.content.addLayout(filters)

        self.topic_row = QHBoxLayout()
        self.topic_row.setSpacing(6)
        self.content.addLayout(self.topic_row)
        self.topic_group = QButtonGroup(self)
        self.topic_group.setExclusive(True)
        self.topic_group.buttonClicked.connect(self._topic_changed)

        # действия с выделенной задачей — над таблицей, рядом с ней
        actions = QHBoxLayout()
        actions.setSpacing(6)
        self.count_label = w.label("", "secondary")
        actions.addWidget(self.count_label)
        actions.addStretch()
        self.done_btn = w.button("Выполнено", None, "check", "Отметить выполненной или вернуть (Пробел)")
        self.done_btn.clicked.connect(self.toggle_selected)
        self.edit_btn = w.button("Изменить…", None, "edit", "Изменить задачу (Enter)")
        self.edit_btn.clicked.connect(self.edit_selected)
        self.more_btn = w.menu_button("Другие действия с задачей")
        more = QMenu(self.more_btn)
        self.archive_action = more.addAction("Отправить в архив", self.archive_selected)
        more.addSeparator()
        more.addAction("Удалить навсегда…", self.delete_selected)
        self.more_btn.setMenu(more)
        for b in (self.done_btn, self.edit_btn, self.more_btn):
            actions.addWidget(b)
        self.content.addLayout(actions)

        self.table = QTableWidget(0, len(self.COLUMNS))
        self.table.setHorizontalHeaderLabels(self.COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        header = self.table.horizontalHeader()
        header.setHighlightSections(False)
        header.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        for col in range(1, len(self.COLUMNS)):
            header.setSectionResizeMode(col, QHeaderView.Interactive)
        self.table.setColumnWidth(1, 56)
        self.table.setColumnWidth(2, 130)
        self.table.setColumnWidth(3, 200)
        self.table.setColumnWidth(4, 96)
        self.table.cellDoubleClicked.connect(lambda *_: self.edit_selected())
        self.table.itemSelectionChanged.connect(self._update_actions)
        self.table.itemSelectionChanged.connect(self._show_detail)

        self.empty = w.label("", "empty", wrap=True)
        self.empty.setAlignment(Qt.AlignCenter)

        # карточка выбранной задачи: описание и подзадачи можно отмечать, не открывая диалог
        self.detail = QFrame()
        self.detail.setObjectName("card")
        self.detail.setFixedWidth(300)
        dl = QVBoxLayout(self.detail)
        dl.setContentsMargins(16, 14, 16, 14)
        dl.setSpacing(8)
        self.d_title = w.label("", "section", wrap=True)
        self.d_meta = w.label("", "caption", wrap=True)
        self.d_desc = w.label("", "secondary", wrap=True)
        self.d_desc.setTextInteractionFlags(Qt.TextSelectableByMouse)
        dl.addWidget(self.d_title)
        dl.addWidget(self.d_meta)
        dl.addWidget(self.d_desc)
        dl.addWidget(w.label("Подзадачи", "section"))
        self.d_subs = SubtaskList(compact=True)
        self.d_subs.changed.connect(self._detail_subtasks_changed)
        dl.addWidget(self.d_subs)
        open_btn = w.button("Изменить задачу…", "ghost", "edit")
        open_btn.clicked.connect(self.edit_selected)
        dl.addWidget(open_btn, 0, Qt.AlignLeft)
        dl.addStretch(1)
        self._detail_task_id: int | None = None

        body = QHBoxLayout()
        body.setSpacing(12)
        left = QVBoxLayout()
        left.setSpacing(0)
        left.addWidget(self.table, 1)
        left.addWidget(self.empty)
        body.addLayout(left, 1)
        body.addWidget(self.detail)
        self.content.addLayout(body, 1)

        QShortcut(QKeySequence(Qt.Key_Space), self.table, activated=self.toggle_selected)
        QShortcut(QKeySequence(Qt.Key_Return), self.table, activated=self.edit_selected)
        QShortcut(QKeySequence(Qt.Key_Delete), self.table, activated=self.delete_selected)

    # ---- фильтры ----

    def _status_changed(self, btn) -> None:
        self.status = btn.property("value")
        self.refresh()

    def _topic_changed(self, btn) -> None:
        self._set_topic(btn.property("value"))

    def _set_topic(self, value) -> None:
        if value is None or value == self.topic_filter:
            return
        self.topic_filter = value
        self.db.set_pref("tasks_topic", str(value))
        self.refresh()

    CHIP_LIMIT = 6   # больше тем — фильтр становится выпадающим списком

    def _rebuild_topic_chips(self, topics: list[logic.Topic], counts: dict | None = None) -> None:
        for b in self.topic_group.buttons():
            self.topic_group.removeButton(b)
        w.clear_layout(self.topic_row)
        counts = counts or {}
        ids = {t.id for t in topics}
        if self.topic_filter not in ids and self.topic_filter not in (logic.TOPIC_ALL, logic.TOPIC_NONE):
            self.topic_filter = logic.TOPIC_ALL
        entries = [("Все темы", logic.TOPIC_ALL, None)] + \
                  [(t.name, t.id, t.color) for t in topics] + \
                  ([("Без темы", logic.TOPIC_NONE, None)] if topics else [])
        if not topics:
            hint = w.label("Темы помогают разделить задачи: дом, работа, учёба…", "caption")
            add = w.button("Создать тему…", "ghost", "plus")
            add.clicked.connect(self.manage_topics)
            self.topic_row.addWidget(hint)
            self.topic_row.addWidget(add)
            self.topic_row.addStretch()
            return
        if len(topics) > self.CHIP_LIMIT:
            self.topic_row.addWidget(w.label("Тема:", "secondary"))
            combo = QComboBox()
            combo.setAccessibleName("Фильтр по теме")
            combo.setMinimumWidth(240)
            combo.setMaxVisibleItems(16)
            for name, value, color in entries:
                text = f"{name}  ·  {counts.get(value, 0)}"
                if color:
                    combo.addItem(w.dot_icon(color), text, value)
                else:
                    combo.addItem(text, value)
            combo.setCurrentIndex(max(0, combo.findData(self.topic_filter)))
            combo.currentIndexChanged.connect(lambda _i: self._set_topic(combo.currentData()))
            self.topic_row.addWidget(combo)
            if self.topic_filter != logic.TOPIC_ALL:
                clear = w.button("Сбросить", "ghost")
                clear.clicked.connect(lambda: self._set_topic(logic.TOPIC_ALL))
                self.topic_row.addWidget(clear)
            self.topic_row.addStretch()
            return
        for name, value, color in entries:
            c = w.chip(f"{name} {counts[value]}" if counts.get(value) else name, value == self.topic_filter)
            c.setProperty("value", value)
            if color:
                c.setIcon(w.dot_icon(color))
                c.setIconSize(QSize(10, 10))
            self.topic_group.addButton(c)
            self.topic_row.addWidget(c)
        self.topic_row.addStretch()

    # ---- действия ----

    def manage_topics(self) -> None:
        TopicsDialog(self, self.db).exec()
        self.refresh()

    def new_item(self) -> None:
        default = self.topic_filter if self.topic_filter > 0 else None
        dlg = TaskDialog(self, self.db.list_topics(), default_topic=default)
        if dlg.exec() == QDialog.Accepted:
            subs = dlg.result_subtasks()
            tid = self.db.add_task(dlg.result_task())
            apply_subtasks(self.db, tid, subs)
            self.refresh()

    def focus_item(self, task_id: int | None = None) -> None:
        if task_id is not None:
            self.open_task(task_id)

    def open_task(self, task_id: int) -> None:
        task = self.db.get_task(task_id)
        if task is None:
            return
        dlg = TaskDialog(self, self.db.list_topics(), task, subtasks=self.db.subtasks(task_id))
        if dlg.exec() == QDialog.Accepted:
            subs = dlg.result_subtasks()
            self.db.update_task(dlg.result_task())
            apply_subtasks(self.db, task_id, subs)
        self.refresh()

    def _selected(self) -> logic.Task | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        task_id = self.table.item(rows[0].row(), 0).data(Qt.UserRole)
        return self.db.get_task(task_id)

    def _update_actions(self) -> None:
        task = self._selected()
        for b in (self.done_btn, self.edit_btn, self.more_btn):
            b.setEnabled(task is not None)
        if task is not None:
            self.done_btn.setText("Вернуть в работу" if task.done else "Выполнено")
            self.archive_action.setText("Вернуть из архива" if task.archived else "Отправить в архив")

    def _show_detail(self) -> None:
        task = self._selected()
        self.detail.setVisible(task is not None)
        if task is None:
            self._detail_task_id = None
            return
        today = date.today()
        topic = next((t for t in self.db.list_topics() if t.id == task.topic_id), None)
        self.d_title.setText(task.title)
        meta = []
        if topic:
            meta.append(topic.name)
        if task.deadline:
            meta.append(f"срок {w.human_date(task.deadline, today)}" +
                        ("" if task.done else f" · {logic.due_text(task.deadline, today)}"))
        meta.append(f"приоритет: {logic.PRIORITY_NAMES[task.priority].lower()}")
        if task.done:
            meta.append("выполнена")
        self.d_meta.setText(" · ".join(meta))
        self.d_desc.setText(task.description)
        self.d_desc.setVisible(bool(task.description))
        if self._detail_task_id != task.id or not self.d_subs.list.hasFocus():
            self.d_subs.set_entries([{"id": x.id, "title": x.title, "done": x.done}
                                     for x in self.db.subtasks(task.id)])
        self._detail_task_id = task.id

    def _detail_subtasks_changed(self) -> None:
        # откладываем: список нельзя пересоздавать прямо из его же сигнала
        QTimer.singleShot(0, self._apply_detail_subtasks)

    def _apply_detail_subtasks(self) -> None:
        if self._detail_task_id is None or self.db.get_task(self._detail_task_id) is None:
            return
        apply_subtasks(self.db, self._detail_task_id, self.d_subs.entries())
        # id новых подзадач нужны списку, чтобы следующие правки не создавали дубли
        self.d_subs.set_entries([{"id": x.id, "title": x.title, "done": x.done}
                                 for x in self.db.subtasks(self._detail_task_id)])
        self._refresh_table_only()

    def _refresh_table_only(self) -> None:
        self._in_detail = True
        try:
            self.refresh()
        finally:
            self._in_detail = False

    def _context_menu(self, pos) -> None:
        if self._selected() is None:
            return
        menu = QMenu(self)
        task = self._selected()
        menu.addAction("Вернуть в работу" if task.done else "Отметить выполненной", self.toggle_selected)
        menu.addAction("Изменить…", self.edit_selected)
        menu.addAction("Вернуть из архива" if task.archived else "Отправить в архив", self.archive_selected)
        menu.addSeparator()
        menu.addAction("Удалить навсегда…", self.delete_selected)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def edit_selected(self) -> None:
        task = self._selected()
        if task:
            self.open_task(task.id)

    def toggle_selected(self) -> None:
        task = self._selected()
        if task is None:
            return
        task.done = not task.done
        task.completed_on = None
        self.db.update_task(task)
        self.refresh()

    def archive_selected(self) -> None:
        task = self._selected()
        if task:
            self.db.set_task_archived(task.id, not task.archived)
            self.refresh()

    def delete_selected(self) -> None:
        task = self._selected()
        if task is None:
            return
        box = QMessageBox(QMessageBox.Warning, "Удалить задачу",
                          f"Удалить задачу «{task.title}» навсегда?", parent=self)
        box.setInformativeText("Это действие нельзя отменить. Чтобы убрать задачу из списка, "
                               "отправьте её в архив.")
        yes = box.addButton("Удалить", QMessageBox.DestructiveRole)
        box.addButton("Отмена", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is yes:
            self.db.delete_task(task.id)
            self.refresh()

    # ---- отрисовка ----

    def refresh(self) -> None:
        today = date.today()
        selected = self._selected()
        topics = self.db.list_topics()
        topic_by_id = {t.id: t for t in topics}
        all_tasks = self.db.list_tasks()
        by_status = logic.filter_tasks(all_tasks, self.status)
        counts = {logic.TOPIC_ALL: len(by_status), logic.TOPIC_NONE: sum(1 for t in by_status if t.topic_id is None)}
        for t in by_status:
            if t.topic_id is not None:
                counts[t.topic_id] = counts.get(t.topic_id, 0) + 1
        self._rebuild_topic_chips(topics, counts)
        subs = self.db.all_subtasks()

        active = [t for t in all_tasks if not t.done and not t.archived]
        overdue = sum(1 for t in all_tasks if logic.is_overdue(t, today))
        sub = f"{len(active)} {logic.plural(len(active), 'активная', 'активные', 'активных')}"
        if overdue:
            sub += f" · {overdue} {logic.plural(overdue, 'просрочена', 'просрочены', 'просрочено')}"
        self.header.set_subtitle(sub)

        tasks = logic.sort_tasks(logic.filter_by_topic(
            logic.filter_tasks(all_tasks, self.status), self.topic_filter))
        self.count_label.setText(f"Показано: {len(tasks)}")

        danger, warn = theme.color("danger"), theme.color("warn")
        danger_bg, warn_bg = theme.color("danger_soft"), theme.color("warn_soft")
        muted = theme.color("text3")
        self.table.setRowCount(len(tasks))
        reselect = None
        for row, task in enumerate(tasks):
            topic = topic_by_id.get(task.topic_id)
            if task.deadline:
                fmt = "%d.%m" if task.deadline.year == today.year else "%d.%m.%Y"
                due = task.deadline.strftime(fmt)
                if not task.done and not task.archived:
                    due += f" · {logic.due_text(task.deadline, today)}"
            else:
                due = "—"
            title = task.title + ("  (выполнена)" if task.done else "")
            st = subs.get(task.id)
            steps = f"{sum(1 for x in st if x.done)}/{len(st)}" if st else ""
            values = [title, steps, topic.name if topic else "—", due, logic.PRIORITY_NAMES[task.priority]]
            overdue_t, today_t = logic.is_overdue(task, today), logic.is_due_today(task, today)
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 0:
                    item.setData(Qt.UserRole, task.id)
                    tip = task.description
                    if st:
                        tip = (tip + "\n\n" if tip else "") + "\n".join(
                            ("✓ " if x.done else "○ ") + x.title for x in st)
                    if tip:
                        item.setToolTip(tip)
                    if task.done:
                        f = item.font(); f.setStrikeOut(True); item.setFont(f)
                if col == 2 and topic:
                    item.setIcon(w.dot_icon(topic.color))
                if col == 1 and st:
                    item.setToolTip("Выполнено подзадач")
                    if all(x.done for x in st):
                        item.setForeground(QBrush(theme.color("accent")))
                if task.done or task.archived:
                    item.setForeground(QBrush(muted))
                if overdue_t:
                    item.setBackground(QBrush(danger_bg))
                    if col == 3:
                        item.setForeground(QBrush(danger))
                elif today_t:
                    item.setBackground(QBrush(warn_bg))
                    if col == 3:
                        item.setForeground(QBrush(warn))
                if col == 4 and task.priority == logic.PRIORITY_HIGH and not task.done:
                    f = item.font(); f.setBold(True); item.setFont(f)
                self.table.setItem(row, col, item)
            if selected and task.id == selected.id:
                reselect = row
        if reselect is not None:
            self.table.selectRow(reselect)
        self.table.setVisible(bool(tasks))
        self.empty.setVisible(not tasks)
        if not getattr(self, "_in_detail", False):
            self._show_detail()
        if not tasks:
            if self.status == logic.FILTER_ACTIVE and not all_tasks:
                self.empty.setText("Задач пока нет. Нажмите «Новая задача» или Ctrl+N.")
            elif self.status == logic.FILTER_ACTIVE:
                self.empty.setText("Здесь нет активных задач — всё сделано.")
            else:
                self.empty.setText("По выбранным фильтрам ничего нет.")
        self._update_actions()
