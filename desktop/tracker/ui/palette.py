"""Ctrl+K — поиск по всему и команды (как в Notion и Linear): задачи, карточки досок, заметки,
цели, привычки, события; «Новая задача: …», «Новая карточка в …», переходы по разделам."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QDialog, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout

from .. import cal, logic
from . import icons
from . import widgets as w
from .theme import theme


def _match(q: str, *texts: str) -> int:
    """0 — нет совпадения; больше — лучше (начало названия важнее середины текста)."""
    best = 0
    for i, t in enumerate(texts):
        tl = (t or "").lower()
        if not tl:
            continue
        if tl.startswith(q):
            best = max(best, 30 - i * 5)
        elif any(word.startswith(q) for word in tl.split()):
            best = max(best, 20 - i * 5)
        elif q in tl:
            best = max(best, 10 - i * 3)
    return best


class CommandPalette(QDialog):
    def __init__(self, window, sections: list[tuple[str, str]]):
        super().__init__(window)
        self.win = window
        self.db = window.db
        self.sections = sections
        self.setWindowTitle("Поиск и команды")
        self.setObjectName("palette")
        self.setMinimumWidth(620)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)
        self.edit = QLineEdit()
        self.edit.setObjectName("paletteEdit")
        self.edit.setPlaceholderText("Найти задачу, карточку, заметку… или команда: «новая задача Купить хлеб завтра»")
        self.edit.addAction(icons.icon("search", theme["text3"], size=16), QLineEdit.LeadingPosition)
        self.edit.textChanged.connect(self._update)
        self.edit.returnPressed.connect(self._run_current)
        self.edit.installEventFilter(self)
        lay.addWidget(self.edit)
        self.list = QListWidget()
        self.list.setObjectName("paletteList")
        self.list.setIconSize(QSize(16, 16))
        self.list.itemActivated.connect(self._run)
        self.list.setMinimumHeight(380)
        lay.addWidget(self.list, 1)
        lay.addWidget(w.label("↑↓ — выбрать · Enter — открыть · Esc — закрыть.  "
                              "Начните с «+», чтобы сразу создать задачу.", "caption"))
        self._update()

    def eventFilter(self, obj, e):
        from PySide6.QtCore import QEvent
        if obj is self.edit and e.type() == QEvent.KeyPress and e.key() in (Qt.Key_Down, Qt.Key_Up):
            row = self.list.currentRow() + (1 if e.key() == Qt.Key_Down else -1)
            # пропускаем заголовки групп
            while 0 <= row < self.list.count() and not (self.list.item(row).flags() & Qt.ItemIsSelectable):
                row += 1 if e.key() == Qt.Key_Down else -1
            if 0 <= row < self.list.count():
                self.list.setCurrentRow(row)
            return True
        return False

    # ---- результаты ----
    def _add_header(self, text: str) -> None:
        it = QListWidgetItem(text.upper())
        it.setFlags(Qt.NoItemFlags)
        f = it.font(); f.setPointSizeF(f.pointSizeF() * 0.8); f.setBold(True); it.setFont(f)
        it.setForeground(theme.color("text3"))
        self.list.addItem(it)

    def _add(self, icon: str, text: str, caption: str, action) -> None:
        it = QListWidgetItem(icons.icon(icon, theme["text2"]), text + (f"    —  {caption}" if caption else ""))
        it.setData(Qt.UserRole, action)
        it.setToolTip(text)
        self.list.addItem(it)

    def _update(self) -> None:
        raw = self.edit.text().strip()
        q = raw.lower()
        self.list.clear()
        today = date.today()
        # ---- команды создания
        create_text = raw[1:].strip() if raw.startswith("+") else raw
        for prefix in ("новая задача", "задача", "добавить"):
            if q.startswith(prefix + " ") or q.startswith(prefix + ":"):
                create_text = raw[len(prefix):].lstrip(" :")
        cmds = []
        if create_text:
            qt = logic.parse_quick_task(create_text, self.db.list_topics(), today)
            hint = " · ".join(qt.hints)
            if qt.title:
                cmds.append(("plus", f"Новая задача: {qt.title}", hint, ("new_task", create_text)))
                for b in self.db.list_boards():
                    cmds.append(("boards", f"Новая карточка в «{b.name}»: {qt.title}", hint,
                                 ("new_card", b.id, create_text)))
                cmds.append(("notes", f"Новая заметка: {create_text}", "", ("new_note", create_text)))
        if raw.startswith("+"):
            self._add_header("Создать")
            for c in cmds:
                self._add(*c)
            self._select_first()
            return
        # ---- переходы
        nav = [("today", "Обзор недели", "", ("go", "today", {"week": True}))]
        nav += [(key, f"Открыть: {title}", "", ("go", key, {})) for key, title in self.sections]
        nav_hits = [n for n in nav if not q or _match(q, n[1].replace("Открыть: ", ""))]
        results = []
        if len(q) >= 2:
            boards = {b.id: b for b in self.db.list_boards(include_archived=True)}
            for t in self.db.list_tasks(include_boards=True):
                score = _match(q, t.title, t.description, t.labels)
                if score:
                    where = boards[t.board_id].name if t.board_id in boards else "Задачи"
                    extra = (f" · {logic.due_text(t.deadline, today)}" if t.deadline and not t.done else "") + \
                        (" · выполнена" if t.done else "")
                    results.append((score - (5 if t.done else 0), "boards" if t.board_id else "tasks", t.title,
                                    where + extra, ("task", t.id, t.board_id)))
            for n in self.db.list_notes() + [n for b in boards for n in self.db.list_notes(board_id=b)]:
                score = _match(q, n.display_title, n.body)
                if score:
                    results.append((score, "notes", n.display_title,
                                    ("Заметка доски «" + boards[n.board_id].name + "»") if n.board_id in boards else "Заметка",
                                    ("note", n.id, n.board_id)))
            for g in self.db.list_goals():
                score = _match(q, g.title, g.description)
                if score:
                    results.append((score, "goals", g.title, "Цель", ("go", "goals", {"goal_id": g.id})))
            for h in self.db.list_habits():
                if _match(q, h.name):
                    results.append((_match(q, h.name), "habits", h.name, "Привычка", ("go", "habits", {})))
            evs = [e for e in self.db.list_events() if _match(q, e.title, e.location, e.description)]
            if evs:
                occs = cal.occurrences(evs, datetime.now() - timedelta(days=30), datetime.now() + timedelta(days=365))
                seen = set()
                for o in sorted(occs, key=lambda o: abs((o.start - datetime.now()).total_seconds())):
                    if o.event.id in seen:
                        continue
                    seen.add(o.event.id)
                    results.append((_match(q, o.event.title, o.event.location), "calendar", o.event.title or "(без названия)",
                                    f"Событие · {o.start:%d.%m %H:%M}", ("go", "calendar", {"day": o.start.date()})))
            for b in boards.values():
                if _match(q, b.name):
                    results.append((_match(q, b.name) + 5, "boards", b.name, "Доска", ("go", "boards", {"board_id": b.id})))
        results.sort(key=lambda r: -r[0])
        if results:
            self._add_header(f"Найдено · {len(results)}")
            for _, icon, text, caption, action in results[:40]:
                self._add(icon, text, caption, action)
        elif len(q) >= 2:
            self._add_header("Ничего не найдено")
        if cmds and q:
            self._add_header("Создать")
            for c in cmds[:4]:
                self._add(*c)
        if nav_hits:
            self._add_header("Разделы")
            for n in nav_hits[: (12 if not q else 5)]:
                self._add(*n)
        self._select_first()

    def _select_first(self) -> None:
        for i in range(self.list.count()):
            if self.list.item(i).flags() & Qt.ItemIsSelectable:
                self.list.setCurrentRow(i)
                return

    # ---- выполнение ----
    def _run_current(self) -> None:
        it = self.list.currentItem()
        if it is not None and it.flags() & Qt.ItemIsSelectable:
            self._run(it)

    def _run(self, item: QListWidgetItem) -> None:
        action = item.data(Qt.UserRole)
        if not action:
            return
        self.accept()
        kind = action[0]
        nav = self.win.navigate
        today = date.today()
        if kind == "go":
            nav(action[1], **action[2])
        elif kind == "task":
            nav("boards" if action[2] else "tasks", task_id=action[1])
        elif kind == "note":
            if action[2]:
                nav("boards", board_id=action[2])
            else:
                nav("notes", note_id=action[1])
        elif kind == "new_task":
            qt = logic.parse_quick_task(action[1], self.db.list_topics(), today)
            tid = self.db.add_task(logic.Task(0, qt.title, deadline=qt.deadline, priority=qt.priority,
                                              topic_id=qt.topic_id, repeat=qt.repeat, labels=", ".join(qt.labels)))
            nav("tasks")
            self.win.pages[self.win.stack.currentIndex()].refresh()
            self.win.show_undo(f"Задача добавлена: {qt.title}", lambda: None,
                               lambda: (self.db.delete_task(tid), self.win.pages[self.win.stack.currentIndex()].refresh()))
        elif kind == "new_card":
            qt = logic.parse_quick_task(action[2], self.db.list_topics(), today)
            col = self.db.list_columns(action[1])[0]
            self.db.add_card(action[1], col.id, qt.title, deadline=qt.deadline, priority=qt.priority,
                             topic_id=qt.topic_id, repeat=qt.repeat, labels=", ".join(qt.labels))
            nav("boards", board_id=action[1])
        elif kind == "new_note":
            nid = self.db.add_note(action[1][:80], "")
            nav("notes", note_id=nid)
