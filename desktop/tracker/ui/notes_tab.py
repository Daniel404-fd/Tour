from __future__ import annotations

from datetime import date, datetime

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QFontMetrics, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QSplitter,
    QComboBox, QHBoxLayout, QInputDialog, QLineEdit, QListWidget, QListWidgetItem, QMenu,
    QMessageBox, QPlainTextEdit, QVBoxLayout, QWidget,
)

from .. import logic
from ..db import Database
from . import icons
from . import widgets as w
from .theme import theme

AUTOSAVE_MS = 600


def when_text(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return ""
    today = date.today()
    if dt.date() == today:
        return f"сегодня, {dt:%H:%M}"
    if (today - dt.date()).days == 1:
        return f"вчера, {dt:%H:%M}"
    return w.human_date(dt.date(), today)


class NoteListRow(QWidget):
    def __init__(self, note: logic.Note):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(2)
        top = QHBoxLayout()
        top.setSpacing(6)
        title = w.label()
        title.setTextFormat(Qt.PlainText)
        f = title.font(); f.setWeight(f.Weight.DemiBold); title.setFont(f)
        title.setText(QFontMetrics(f).elidedText(note.display_title, Qt.ElideRight,
                                                 230 if note.pinned else 250))
        top.addWidget(title, 1)
        if note.pinned:
            pin = w.label()
            pin.setPixmap(icons.pixmap("pin", theme["accent"], 14))
            pin.setToolTip("Закреплена")
            top.addWidget(pin)
        lay.addLayout(top)
        body_lines = [ln.strip() for ln in note.body.splitlines() if ln.strip()]
        if not note.title.strip() and body_lines:
            body_lines = body_lines[1:]
        preview = body_lines[0][:70] if body_lines else "Нет текста"
        sub = w.label("", "caption")
        sub.setText(QFontMetrics(sub.font()).elidedText(
            f"{when_text(note.updated_at)}  ·  {preview}", Qt.ElideRight, 240))
        sub.setTextFormat(Qt.PlainText)
        lay.addWidget(sub)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)


class FolderList(QListWidget):
    """Список папок; на папку можно перетащить заметку из списка заметок."""

    def __init__(self, page: "NotesPage"):
        super().__init__()
        self.page = page
        self.setObjectName("folderList")
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setIconSize(QSize(18, 18))
        self.setAccessibleName("Папки заметок")

    def dragEnterEvent(self, e) -> None:
        if e.source() is self.page.list:
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e) -> None:
        it = self.itemAt(e.position().toPoint())
        if e.source() is self.page.list and it is not None and it.data(Qt.UserRole) != logic.FOLDER_ALL:
            e.acceptProposedAction()
        else:
            e.ignore()

    def dropEvent(self, e) -> None:
        it = self.itemAt(e.position().toPoint())
        src = self.page.list.currentItem()
        if it is None or src is None:
            return e.ignore()
        fid = it.data(Qt.UserRole)
        if fid == logic.FOLDER_ALL:
            return e.ignore()
        self.page.move_note(src.data(Qt.UserRole), None if fid == logic.FOLDER_NONE else fid)
        e.acceptProposedAction()


class NotesPage(w.Page):
    def __init__(self, db: Database, navigate=None):
        super().__init__("Заметки", scroll=False)
        self.db = db
        self.current_id: int | None = None
        try:
            self.folder = int(db.get_pref("notes_folder", str(logic.FOLDER_ALL)))
        except ValueError:
            self.folder = logic.FOLDER_ALL
        self._loading = False
        self._dirty = False
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(AUTOSAVE_MS)
        self.timer.timeout.connect(self.flush)

        new_btn = w.button("Новая заметка", "primary", "plus", "Новая заметка (Ctrl+N)")
        new_btn.clicked.connect(self.new_item)
        self.header.add_action(new_btn)

        # папки | список | текст — все границы можно тянуть мышью, папки можно свернуть
        body = QSplitter(Qt.Horizontal)
        body.setObjectName("pageSplit")
        body.setHandleWidth(12)

        # ---- папки ----
        fcol = QVBoxLayout()
        fcol.setContentsMargins(0, 0, 0, 0)
        fcol.setSpacing(8)
        fhead = QHBoxLayout()
        fhead.addWidget(w.label("Папки", "section"))
        fhead.addStretch()
        add_f = w.button("", "ghost", "plus", "Новая папка")
        add_f.setFixedSize(30, 28)
        add_f.clicked.connect(self.add_folder)
        fhead.addWidget(add_f)
        fcol.addLayout(fhead)
        self.folders = FolderList(self)
        self.folders.currentItemChanged.connect(self._on_folder)
        self.folders.setContextMenuPolicy(Qt.CustomContextMenu)
        self.folders.customContextMenuRequested.connect(self._folder_menu)
        self.folders.itemDoubleClicked.connect(lambda it: self.rename_folder(it))
        fcol.addWidget(self.folders, 1)
        fcol.addWidget(w.label("Перетащите заметку на папку, чтобы переложить её.", "caption", wrap=True))
        fw = QWidget()
        fw.setLayout(fcol)
        fw.setMinimumWidth(150)
        body.addWidget(fw)

        left = QVBoxLayout()
        left.setSpacing(8)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск по заметкам")
        self.search.setClearButtonEnabled(True)
        self.search.addAction(icons.icon("search", theme["text3"], size=16), QLineEdit.LeadingPosition)
        self.search.textChanged.connect(lambda: self._reload_list())
        left.addWidget(self.search)
        self.list = QListWidget()
        self.list.setObjectName("noteList")
        self.list.setAccessibleName("Список заметок")
        self.list.currentItemChanged.connect(self._on_select)
        self.list.setDragEnabled(True)
        self.list.setDragDropMode(QListWidget.DragOnly)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._note_menu)
        left.addWidget(self.list, 1)
        self.list_empty = w.label("", "empty", wrap=True)
        self.list_empty.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        left.addWidget(self.list_empty, 1)
        lw = QWidget()
        lw.setLayout(left)
        lw.setMinimumWidth(200)
        left.setContentsMargins(0, 0, 0, 0)
        body.addWidget(lw)

        # редактор
        self.editor = w.Card(margins=24)
        self.editor.setObjectName("paper")   # белый лист, как в Блокноте
        self.editor.body.setSpacing(8)
        bar = QHBoxLayout()
        self.meta = w.label("", "caption")
        self.folder_combo = QComboBox()
        self.folder_combo.setAccessibleName("Папка заметки")
        self.folder_combo.setToolTip("Папка, в которой лежит заметка")
        self.folder_combo.setMinimumWidth(150)
        self.folder_combo.activated.connect(self._combo_moved)
        bar.addWidget(self.folder_combo)
        bar.addStretch()
        self.pin_btn = w.button("Закрепить", "ghost", "pin", "Закреплённые заметки показываются "
                                "вверху списка и на главной")
        self.pin_btn.setCheckable(True)
        self.pin_btn.toggled.connect(self._toggle_pin)
        self.del_btn = w.button("Удалить", "ghost", "trash")
        self.del_btn.clicked.connect(self.delete_current)
        bar.addWidget(self.pin_btn)
        bar.addWidget(self.del_btn)
        self.editor.body.addLayout(bar)
        self.title = QLineEdit()
        self.title.setObjectName("noteTitle")
        self.title.setPlaceholderText("Название")
        self.title.textEdited.connect(self._changed)
        self.editor.body.addWidget(self.title)
        self.text = QPlainTextEdit()
        self.text.setObjectName("noteBody")
        self.text.document().setDocumentMargin(0)
        self.text.setPlaceholderText("Текст заметки… Сохраняется автоматически.")
        self.text.textChanged.connect(self._changed)
        self.editor.body.addWidget(self.text, 1)
        self.editor.body.addWidget(self.meta)
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(self.editor, 1)
        self.empty = w.label("Заметок пока нет.\nНажмите «Новая заметка» или Ctrl+N — "
                             "идеи, списки, мысли.", "empty", wrap=True)
        self.empty.setAlignment(Qt.AlignCenter)
        rl.addWidget(self.empty, 1)
        right.setMinimumWidth(300)
        body.addWidget(right)
        body.setStretchFactor(2, 1)
        body.setCollapsible(1, False)
        body.setCollapsible(2, False)
        w.remember_splitter(body, db, "split_notes", [200, 290, 700])
        self.content.addWidget(body, 1)

        QShortcut(QKeySequence.Find, self, activated=self.search.setFocus)

    # ---- данные ----

    def _changed(self) -> None:
        if self._loading or self.current_id is None:
            return
        self._dirty = True
        self.timer.start()

    def flush(self) -> None:
        """Сохранить текущую заметку (по таймеру, при переключении и при закрытии окна)."""
        self.timer.stop()
        if not self._dirty or self.current_id is None:
            return
        self.db.update_note(self.current_id, self.title.text().strip(), self.text.toPlainText())
        self._dirty = False
        self.meta.setText("Сохранено · " + when_text(datetime.now().isoformat()))
        note = self.db.get_note(self.current_id)
        item = self._item_for(self.current_id)
        if note and item:
            self.list.setItemWidget(item, NoteListRow(note))

    def _item_for(self, note_id: int) -> QListWidgetItem | None:
        for i in range(self.list.count()):
            it = self.list.item(i)
            if it.data(Qt.UserRole) == note_id:
                return it
        return None

    def new_item(self) -> None:
        self.flush()
        self.search.clear()
        folder = self.folder if self.folder > 0 else None
        self.current_id = self.db.add_note(folder_id=folder)
        self.refresh()
        self.title.setFocus()

    def focus_item(self, note_id: int | None = None, new: bool = False) -> None:
        if new:
            self.new_item()
        elif note_id is not None:
            self.flush()
            self.search.clear()
            self.current_id = note_id
            self.folder = logic.FOLDER_ALL
            self.refresh()

    def _toggle_pin(self, on: bool) -> None:
        if self._loading or self.current_id is None:
            return
        self.flush()
        self.db.set_note_pinned(self.current_id, on)
        self._reload_folders()
        self._reload_list()

    def delete_current(self) -> None:
        if self.current_id is None:
            return
        note = self.db.get_note(self.current_id)
        box = QMessageBox(QMessageBox.Warning, "Удалить заметку",
                          f"Удалить заметку «{note.display_title if note else ''}»?", parent=self)
        box.setInformativeText("Это действие нельзя отменить.")
        yes = box.addButton("Удалить", QMessageBox.DestructiveRole)
        box.addButton("Отмена", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is yes:
            self.timer.stop()
            self._dirty = False
            self.db.delete_note(self.current_id)
            self.current_id = None
            self.refresh()

    # ---- отрисовка ----

    def _on_select(self, item: QListWidgetItem | None, _prev=None) -> None:
        if self._loading:
            return
        self.flush()
        self.current_id = item.data(Qt.UserRole) if item else None
        self._load_editor()

    def _load_editor(self) -> None:
        note = self.db.get_note(self.current_id) if self.current_id is not None else None
        self._loading = True
        self.editor.setVisible(note is not None)
        if note:
            self.title.setText(note.title)
            self.text.setPlainText(note.body)
            self.pin_btn.setChecked(note.pinned)
            self.pin_btn.setText("Закреплена" if note.pinned else "Закрепить")
            self.meta.setText(f"Изменена {when_text(note.updated_at)}")
            self.folder_combo.clear()
            self.folder_combo.addItem(icons.icon("folder", theme["text3"], size=16), "Без папки", None)
            for f in self.db.list_folders():
                self.folder_combo.addItem(icons.icon("folder", theme["text2"], size=16), f.name, f.id)
            self.folder_combo.setCurrentIndex(max(0, self.folder_combo.findData(note.folder_id)))
        self._loading = False

    # ---- папки ----

    def _reload_folders(self) -> None:
        all_notes = self.db.list_notes()
        folders = self.db.list_folders()
        ids = {f.id for f in folders}
        if self.folder not in ids and self.folder not in (logic.FOLDER_ALL, logic.FOLDER_NONE):
            self.folder = logic.FOLDER_ALL
        if not folders and self.folder == logic.FOLDER_NONE:
            self.folder = logic.FOLDER_ALL
        entries = [(logic.FOLDER_ALL, "Все заметки", len(all_notes), "notes")]
        for f in folders:
            entries.append((f.id, f.name, sum(1 for n in all_notes if n.folder_id == f.id), "folder"))
        if folders:
            entries.append((logic.FOLDER_NONE, "Без папки",
                            sum(1 for n in all_notes if n.folder_id is None), "folder"))
        self._loading = True
        self.folders.clear()
        for fid, name, count, icon in entries:
            it = QListWidgetItem(icons.icon(icon, theme["text2"], selected=theme["text"], size=18),
                                 f"{name}   {count}")
            it.setData(Qt.UserRole, fid)
            it.setToolTip(name)
            if fid > 0:
                it.setData(Qt.UserRole + 1, name)
            self.folders.addItem(it)
            if fid == self.folder:
                self.folders.setCurrentItem(it)
        self._loading = False

    def _on_folder(self, item, _prev=None) -> None:
        if self._loading or item is None:
            return
        self.flush()
        self.folder = item.data(Qt.UserRole)
        self.db.set_pref("notes_folder", str(self.folder))
        self._reload_list()

    def _folder_menu(self, pos) -> None:
        it = self.folders.itemAt(pos)
        menu = QMenu(self)
        if it is not None and it.data(Qt.UserRole) > 0:
            menu.addAction("Переименовать…", lambda: self.rename_folder(it))
            menu.addAction("Удалить папку…", lambda: self.delete_folder(it))
            menu.addSeparator()
        menu.addAction("Новая папка…", self.add_folder)
        menu.exec(self.folders.viewport().mapToGlobal(pos))

    def add_folder(self) -> None:
        name, ok = QInputDialog.getText(self, "Новая папка", "Название папки:")
        if ok and name.strip():
            self.folder = self.db.add_folder(name.strip())
            self.db.set_pref("notes_folder", str(self.folder))
            self.refresh()

    def rename_folder(self, it) -> None:
        fid = it.data(Qt.UserRole)
        if fid is None or fid <= 0:
            return
        name, ok = QInputDialog.getText(self, "Переименовать папку", "Название папки:",
                                        text=it.data(Qt.UserRole + 1))
        if ok and name.strip():
            self.db.rename_folder(fid, name.strip())
            self.refresh()

    def delete_folder(self, it) -> None:
        fid = it.data(Qt.UserRole)
        name = it.data(Qt.UserRole + 1)
        box = QMessageBox(QMessageBox.Question, "Удалить папку", f"Удалить папку «{name}»?", parent=self)
        box.setInformativeText("Заметки из неё не удалятся — они окажутся в «Без папки».")
        yes = box.addButton("Удалить папку", QMessageBox.DestructiveRole)
        box.addButton("Отмена", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is yes:
            self.db.delete_folder(fid)
            self.refresh()

    def move_note(self, note_id: int, folder_id: int | None) -> None:
        self.flush()
        self.db.move_note(note_id, folder_id)
        self.refresh()

    def _combo_moved(self, _i) -> None:
        if self.current_id is not None:
            self.move_note(self.current_id, self.folder_combo.currentData())

    def _note_menu(self, pos) -> None:
        it = self.list.itemAt(pos)
        if it is None:
            return
        nid = it.data(Qt.UserRole)
        note = self.db.get_note(nid)
        menu = QMenu(self)
        move = menu.addMenu("Переместить в папку")
        move.addAction("Без папки", lambda: self.move_note(nid, None)).setEnabled(note.folder_id is not None)
        for f in self.db.list_folders():
            a = move.addAction(f.name, lambda fid=f.id: self.move_note(nid, fid))
            a.setEnabled(note.folder_id != f.id)
        move.addSeparator()
        move.addAction("Новая папка…", lambda: self._new_folder_for(nid))
        menu.addAction("Открепить" if note.pinned else "Закрепить",
                       lambda: (self.db.set_note_pinned(nid, not note.pinned), self.refresh()))
        menu.addSeparator()
        menu.addAction("Удалить…", lambda: (self.list.setCurrentItem(it), self.delete_current()))
        menu.exec(self.list.viewport().mapToGlobal(pos))

    def _new_folder_for(self, nid: int) -> None:
        name, ok = QInputDialog.getText(self, "Новая папка", "Название папки:")
        if ok and name.strip():
            self.move_note(nid, self.db.add_folder(name.strip()))

    # ---- список ----

    def _reload_list(self) -> None:
        notes = logic.filter_by_folder(self.db.list_notes(), self.folder)
        notes = logic.sort_notes(logic.search_notes(notes, self.search.text()))
        self._loading = True
        self.list.clear()
        for n in notes:
            it = QListWidgetItem()
            it.setData(Qt.UserRole, n.id)
            it.setSizeHint(QSize(260, 56))
            it.setToolTip(n.display_title)
            self.list.addItem(it)
            self.list.setItemWidget(it, NoteListRow(n))
        self._loading = False
        ids = [n.id for n in notes]
        if self.current_id not in ids:
            self.current_id = ids[0] if ids else None
        if self.current_id is not None:
            self._loading = True
            self.list.setCurrentItem(self._item_for(self.current_id))
            self._loading = False
        has_any = bool(self.db.list_notes())
        self.list.setVisible(bool(notes))
        self.list_empty.setVisible(not notes)
        if self.search.text().strip():
            self.list_empty.setText("Ничего не найдено.")
        elif not has_any:
            self.list_empty.setText("Заметок пока нет.")
        else:
            self.list_empty.setText("В этой папке пока нет заметок.\nНажмите «Новая заметка» или "
                                    "перетащите сюда заметку.")
        self.empty.setVisible(not has_any)
        self._load_editor()
        if not notes:
            self.editor.setVisible(False)
            self.empty.setVisible(True)
            if has_any:
                self.empty.setText("Выберите заметку или создайте новую.")

    def refresh(self) -> None:
        self.flush()
        n = len(self.db.list_notes())
        self.header.set_subtitle(f"{n} {logic.plural(n, 'заметка', 'заметки', 'заметок')}" if n else "")
        self._reload_folders()
        self._reload_list()
