"""Вложения заметок: хранение, удаление, синхронизация файлов, просмотр."""
from pathlib import Path

from tracker import attachments as att, sync
from tracker.db import Database
from tests.test_v25 import app, keep  # noqa: F401


def _png(path: Path) -> Path:
    from PySide6.QtGui import QImage, QColor
    img = QImage(40, 30, QImage.Format_RGB32)
    img.fill(QColor("#1D4ED8"))
    img.save(str(path))
    return path


def test_add_remove_and_cascade(tmp_path, app):
    db = Database(tmp_path / "d" / "tracker.sqlite3")
    n = db.add_note("Ремонт")
    src = _png(tmp_path / "фото.png")
    aid = att.add_file(db, n, src)
    a = db.get_attachment(aid)
    assert a.name == "фото.png" and a.mime == "image/png" and att.path_of(db, a.file).exists()
    assert att.kind(a.name) == "image" and db.attachment_counts() == {n: 1}
    att.remove(db, aid)
    assert not att.path_of(db, a.file).exists() and db.list_attachments() == []
    aid = att.add_file(db, n, src)
    stored = db.get_attachment(aid).file
    db.delete_note(n)                                  # запись уходит каскадом, файл — уборкой
    assert db.list_attachments() == []
    assert att.cleanup(db) == 1 and not att.path_of(db, stored).exists()


def test_attachment_rows_sync(tmp_path, app):
    pc, ph = Database(tmp_path / "pc" / "t.sqlite3"), Database(tmp_path / "ph" / "t.sqlite3")
    n = pc.add_note("Договор")
    att.add_bytes(pc, n, b"%PDF-1.4 test", "договор.pdf")
    ph.sync_merge([sync.decode(pc.sync_export("ПК"))])
    [a] = ph.list_attachments()
    assert a.name == "договор.pdf" and ph.get_note(a.note_id).title == "Договор"


def test_sync_files_up_and_down(tmp_path):
    class FakeDav:
        store: dict = {}

        def __init__(self):
            self.folder = "HabitTracker-sync"
            self.base = "x"

        def list(self):
            from tracker.webdav import RemoteFile
            return [RemoteFile(k, "e", len(v)) for k, v in FakeDav.store.items()]

        def ensure_folder(self):
            pass

        def put(self, name, data):
            FakeDav.store[name] = data

        def get(self, name):
            return FakeDav.store[name]
    import tracker.webdav as wd
    orig = wd.WebDav
    wd.WebDav = FakeDav
    try:
        a_dir, b_dir = tmp_path / "a", tmp_path / "b"
        a_dir.mkdir()
        (a_dir / "f1.jpg").write_bytes(b"photo")
        assert att.sync_files(FakeDav(), a_dir, {"f1.jpg"}) == (1, 0)
        assert att.sync_files(FakeDav(), b_dir, {"f1.jpg"}) == (0, 1)
        assert (b_dir / "f1.jpg").read_bytes() == b"photo"
        assert att.sync_files(FakeDav(), b_dir, {"f1.jpg"}) == (0, 0)     # второй раз ничего не гоняем
    finally:
        wd.WebDav = orig


def test_strip_and_viewer(tmp_path, app):
    from tracker.ui.attachments_ui import AttachmentStrip, AttachmentViewer
    db = Database(tmp_path / "d" / "tracker.sqlite3")
    n = db.add_note("Фото")
    att.add_file(db, n, _png(tmp_path / "a.png"))
    att.add_bytes(db, n, "строка 1\nстрока 2".encode(), "заметка.txt")
    att.add_bytes(db, n, b"\x00\x01", "архив.zip")
    strip = keep(AttachmentStrip(db))
    strip.set_note(n)
    assert "Вложения · 3" in strip.title.text()
    v = keep(AttachmentViewer(None, db, db.list_attachments(n), 0))
    assert v.stack.currentWidget() is v.image
    v.go(1)
    assert v.stack.currentWidget() is v.text and "строка 2" in v.text.toPlainText()
    v.go(1)
    assert v.stack.currentWidget() is v.other
    strip.add_paths([str(_png(tmp_path / "b.png"))])
    assert len(db.list_attachments(n)) == 4


def test_pdf_view(tmp_path, app):
    from PySide6.QtGui import QPdfWriter, QPainter
    from tracker.ui.attachments_ui import AttachmentViewer
    pdf = tmp_path / "doc.pdf"
    wr = QPdfWriter(str(pdf))
    p = QPainter(wr)
    p.drawText(100, 100, "Привет")
    p.end()
    db = Database(tmp_path / "d" / "tracker.sqlite3")
    n = db.add_note("PDF")
    att.add_file(db, n, pdf)
    v = keep(AttachmentViewer(None, db, db.list_attachments(n), 0))
    assert v.pdf is not None and v.stack.currentWidget() is v.pdf and v.pdf_doc.pageCount() == 1
