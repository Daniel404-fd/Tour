"""Вложения в заметках: полоса миниатюр под текстом и просмотр внутри программы
(фото — с увеличением, PDF — постранично, текст — как текст, остальное — открыть или сохранить)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QFrame, QGraphicsPixmapItem, QGraphicsScene, QGraphicsView, QHBoxLayout, QLabel,
    QMenu, QMessageBox, QPlainTextEdit, QStackedWidget, QVBoxLayout, QWidget,
)

from .. import attachments as att
from . import icons
from . import widgets as w
from .theme import theme

THUMB = 84
_thumb_cache: dict[str, QPixmap] = {}


def _thumb(path: Path) -> QPixmap | None:
    key = str(path)
    if key in _thumb_cache:
        return _thumb_cache[key]
    img = QImage(str(path))
    if img.isNull():
        return None
    pm = QPixmap.fromImage(img.scaled(THUMB * 2, THUMB * 2, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
    pm.setDevicePixelRatio(2)
    _thumb_cache[key] = pm
    return pm


class Tile(QFrame):
    """Одна миниатюра: фото — картинкой, файл — значком с именем и размером."""
    clicked = Signal()

    def __init__(self, db, a):
        super().__init__()
        self.a = a
        self.setObjectName("attTile")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(THUMB, THUMB)
        self.setToolTip(f"{a.name} · {att.human_size(a.size)}\nЩелчок — открыть, правый щелчок — действия")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(2)
        path = att.path_of(db, a.file)
        pm = _thumb(path) if att.kind(a.name) == "image" and path.exists() else None
        if pm is not None:
            lab = QLabel()
            lab.setAlignment(Qt.AlignCenter)
            side = THUMB - 8
            canvas = QPixmap(side * 2, side * 2)
            canvas.setDevicePixelRatio(2)
            canvas.fill(Qt.transparent)
            p = QPainter(canvas)
            p.setRenderHint(QPainter.Antialiasing)
            from PySide6.QtGui import QPainterPath
            clip = QPainterPath()
            clip.addRoundedRect(0, 0, side, side, 6, 6)
            p.setClipPath(clip)
            sw, sh = pm.width() / 2, pm.height() / 2
            p.drawPixmap(int((side - sw) / 2), int((side - sh) / 2), pm)
            p.end()
            lab.setPixmap(canvas)
            lay.addWidget(lab)
        else:
            ic = QLabel()
            ic.setAlignment(Qt.AlignCenter)
            name = {"pdf": "notes", "text": "notes"}.get(att.kind(a.name), "folder")
            ic.setPixmap(icons.icon(name, theme["text2"]).pixmap(26, 26))
            lay.addWidget(ic, 1)
            nm = QLabel(a.name if path.exists() else "загружается…")
            nm.setObjectName("attName")
            nm.setAlignment(Qt.AlignCenter)
            nm.setWordWrap(True)
            f = nm.font(); f.setPointSizeF(f.pointSizeF() * 0.8); nm.setFont(f)
            nm.setText(nm.fontMetrics().elidedText(nm.text(), Qt.ElideMiddle, THUMB * 2 - 16))
            lay.addWidget(nm)

    def mouseReleaseEvent(self, e) -> None:
        if e.button() == Qt.LeftButton:
            self.clicked.emit()


class AttachmentStrip(QWidget):
    """Вложения заметки + кнопка «Прикрепить». Файлы можно перетащить на заметку или вставить (Ctrl+V)."""
    changed = Signal()

    def __init__(self, db):
        super().__init__()
        self.db = db
        self.note_id: int | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(6)
        head = QHBoxLayout()
        self.title = w.label("", "caption")
        head.addWidget(self.title)
        head.addStretch()
        self.add_btn = w.button("Прикрепить файл или фото", "ghost", "plus",
                                "Можно и перетащить файлы на заметку или вставить картинку (Ctrl+V)")
        self.add_btn.clicked.connect(self.pick)
        head.addWidget(self.add_btn)
        lay.addLayout(head)
        self.strip = w.ChipStrip()
        lay.addWidget(self.strip)

    def set_note(self, note_id: int | None) -> None:
        self.note_id = note_id
        self.reload()

    def reload(self) -> None:
        self.strip.clear()
        items = self.db.list_attachments(self.note_id) if self.note_id else []
        self.title.setText(f"Вложения · {len(items)}" if items else "")
        self.strip.setVisible(bool(items))
        for a in items:
            t = Tile(self.db, a)
            t.clicked.connect(lambda a=a, items=items: AttachmentViewer(self, self.db, items, items.index(a)).exec())
            t.setContextMenuPolicy(Qt.CustomContextMenu)
            t.customContextMenuRequested.connect(lambda pos, a=a, t=t: self._menu(a, t.mapToGlobal(pos)))
            self.strip.addWidget(t)
        self.strip.addStretch()
        self.strip.setFixedHeight(THUMB + 14 if items else 0)

    def _menu(self, a, pos) -> None:
        m = QMenu(self)
        m.addAction("Открыть", lambda: AttachmentViewer(self, self.db, [a], 0).exec())
        m.addAction("Открыть в программе", lambda: open_external(self.db, a))
        m.addAction("Сохранить как…", lambda: save_as(self, self.db, a))
        m.addSeparator()
        m.addAction("Удалить", lambda: self.remove(a))
        m.exec(pos)

    def remove(self, a) -> None:
        if w.confirm(self, "Удалить вложение", f"Удалить «{a.name}» из заметки?"):
            att.remove(self.db, a.id)
            self.reload()
            self.changed.emit()

    def pick(self) -> None:
        if self.note_id is None:
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "Прикрепить к заметке", str(Path.home()))
        self.add_paths(paths)

    def add_paths(self, paths) -> None:
        if self.note_id is None:
            return
        errors = []
        for p in paths:
            try:
                att.add_file(self.db, self.note_id, p)
            except (att.AttachmentError, OSError) as e:
                errors.append(str(e))
        if errors:
            QMessageBox.warning(self, "Не всё прикрепилось", "\n".join(errors))
        self.reload()
        self.changed.emit()

    def add_image(self, img: QImage) -> None:
        if self.note_id is None or img.isNull():
            return
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice
        from datetime import datetime
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.WriteOnly)
        img.save(buf, "PNG")
        att.add_bytes(self.db, self.note_id, bytes(ba), f"Снимок {datetime.now():%d.%m %H-%M-%S}.png")
        self.reload()
        self.changed.emit()


def open_external(db, a) -> None:
    p = att.path_of(db, a.file)
    if p.exists():
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))


def save_as(parent, db, a) -> None:
    dest, _ = QFileDialog.getSaveFileName(parent, "Сохранить вложение", str(Path.home() / a.name))
    if dest:
        try:
            att.save_copy(db, a, dest)
        except OSError as e:
            QMessageBox.warning(parent, "Не удалось сохранить", str(e))


class ImageView(QGraphicsView):
    """Фото: колесо — увеличить/уменьшить, перетаскивание — двигать, двойной щелчок — по размеру окна."""

    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.item = QGraphicsPixmapItem()
        self.item.setTransformationMode(Qt.SmoothTransformation)
        self.scene().addItem(self.item)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setFrameShape(QFrame.NoFrame)
        self.setObjectName("imageView")

    def set_image(self, path: Path) -> bool:
        pm = QPixmap(str(path))
        self.item.setPixmap(pm)
        self.scene().setSceneRect(self.item.boundingRect())
        self.fit()
        return not pm.isNull()

    def fit(self) -> None:
        self.resetTransform()
        r = self.item.boundingRect()
        if r.width() > self.viewport().width() or r.height() > self.viewport().height():
            self.fitInView(self.item, Qt.KeepAspectRatio)

    def wheelEvent(self, e) -> None:
        f = 1.15 if e.angleDelta().y() > 0 else 1 / 1.15
        self.scale(f, f)

    def mouseDoubleClickEvent(self, _e) -> None:
        self.fit()

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        if self.transform().m11() <= 1.0:
            self.fit()


class AttachmentViewer(QDialog):
    """Просмотр вложения прямо в программе; ← → — соседние вложения заметки."""

    def __init__(self, parent, db, items: list, index: int = 0):
        super().__init__(parent)
        self.db, self.items, self.i = db, items, index
        self.setObjectName("viewer")
        self.resize(980, 720)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 12)
        lay.setSpacing(8)
        bar = QHBoxLayout()
        self.prev_b = w.button("", "ghost", "chevron-left", "Предыдущее (←)")
        self.next_b = w.button("", "ghost", "chevron-right", "Следующее (→)")
        self.prev_b.clicked.connect(lambda: self.go(-1))
        self.next_b.clicked.connect(lambda: self.go(1))
        self.name = w.label("", "section")
        self.meta = w.label("", "caption")
        bar.addWidget(self.prev_b)
        bar.addWidget(self.next_b)
        bar.addWidget(self.name)
        bar.addWidget(self.meta)
        bar.addStretch()
        ext = w.button("Открыть в программе", None, None, "Открыть программой Windows по умолчанию")
        ext.clicked.connect(lambda: open_external(self.db, self.items[self.i]))
        save = w.button("Сохранить как…")
        save.clicked.connect(lambda: save_as(self, self.db, self.items[self.i]))
        bar.addWidget(ext)
        bar.addWidget(save)
        lay.addLayout(bar)
        self.stack = QStackedWidget()
        self.image = ImageView()
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setObjectName("viewerText")
        self.other = w.label("", "empty", wrap=True)
        self.other.setAlignment(Qt.AlignCenter)
        self.pdf = None
        for x in (self.image, self.text, self.other):
            self.stack.addWidget(x)
        lay.addWidget(self.stack, 1)
        self.show_current()

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key_Left:
            self.go(-1)
        elif e.key() == Qt.Key_Right:
            self.go(1)
        else:
            super().keyPressEvent(e)

    def go(self, d: int) -> None:
        if 0 <= self.i + d < len(self.items):
            self.i += d
            self.show_current()

    def show_current(self) -> None:
        a = self.items[self.i]
        self.setWindowTitle(a.name)
        self.name.setText(a.name)
        self.meta.setText(f"{att.human_size(a.size)}" + (f" · {self.i + 1} из {len(self.items)}" if len(self.items) > 1 else ""))
        self.prev_b.setVisible(len(self.items) > 1)
        self.next_b.setVisible(len(self.items) > 1)
        self.prev_b.setEnabled(self.i > 0)
        self.next_b.setEnabled(self.i < len(self.items) - 1)
        path = att.path_of(self.db, a.file)
        if not path.exists():
            self.other.setText("Файл ещё не загрузился с Яндекс Диска.\nОн появится после ближайшей синхронизации.")
            self.stack.setCurrentWidget(self.other)
            return
        k = att.kind(a.name)
        if k == "image" and self.image.set_image(path):
            self.stack.setCurrentWidget(self.image)
            return
        if k == "pdf" and self._show_pdf(path):
            return
        if k == "text":
            try:
                data = path.read_bytes()[:2_000_000]
                try:
                    txt = data.decode("utf-8")
                except UnicodeDecodeError:
                    txt = data.decode("cp1251", errors="replace")
                self.text.setPlainText(txt)
                self.stack.setCurrentWidget(self.text)
                return
            except OSError:
                pass
        self.other.setText(f"«{a.name}»\n\nЭтот тип файла показать здесь нельзя —\n"
                           "нажмите «Открыть в программе» или «Сохранить как…».")
        self.stack.setCurrentWidget(self.other)

    def _show_pdf(self, path: Path) -> bool:
        try:
            from PySide6.QtPdf import QPdfDocument
            from PySide6.QtPdfWidgets import QPdfView
        except ImportError:
            return False
        if self.pdf is None:
            self.pdf_doc = QPdfDocument(self)
            self.pdf = QPdfView(self)
            self.pdf.setDocument(self.pdf_doc)
            self.pdf.setPageMode(QPdfView.PageMode.MultiPage)
            self.pdf.setZoomMode(QPdfView.ZoomMode.FitToWidth)
            self.stack.addWidget(self.pdf)
        self.pdf_doc.load(str(path))
        if self.pdf_doc.pageCount() <= 0:
            return False
        self.stack.setCurrentWidget(self.pdf)
        return True


class DropAndPaste:
    """Подключить к заметке: файлы, брошенные на виджеты, и картинка из буфера (Ctrl+V) — во вложения."""

    def __init__(self, strip: AttachmentStrip, drop_targets: list, paste_target):
        from PySide6.QtCore import QObject
        self.strip = strip

        class F(QObject):
            def eventFilter(f, obj, e):
                from PySide6.QtCore import QEvent
                from PySide6.QtGui import QKeySequence
                from PySide6.QtWidgets import QApplication
                t = e.type()
                if t in (QEvent.DragEnter, QEvent.DragMove) and e.mimeData().hasUrls():
                    e.acceptProposedAction()
                    return True
                if t == QEvent.Drop and e.mimeData().hasUrls():
                    paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
                    paths = [p for p in paths if Path(p).is_file()]
                    if paths:
                        strip.add_paths(paths)
                        e.acceptProposedAction()
                        return True
                if t == QEvent.KeyPress and obj is paste_target and e.matches(QKeySequence.Paste):
                    md = QApplication.clipboard().mimeData()
                    if md.hasImage() and not md.hasText():
                        strip.add_image(QApplication.clipboard().image())
                        return True
                    if md.hasUrls() and all(u.isLocalFile() for u in md.urls()):
                        strip.add_paths([u.toLocalFile() for u in md.urls() if Path(u.toLocalFile()).is_file()])
                        return True
                return False
        self.filter = F(strip)
        for t in drop_targets:
            t.setAcceptDrops(True)
            t.installEventFilter(self.filter)
            if hasattr(t, "viewport"):
                t.viewport().setAcceptDrops(True)
                t.viewport().installEventFilter(self.filter)
        paste_target.installEventFilter(self.filter)
