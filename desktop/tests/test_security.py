import sqlite3
from datetime import date

import pytest

from tracker import backup, storage
from tracker.db import CorruptDatabase, Database
from tracker.logic import Task
from tracker.session import Session
from tracker.storage import Keyring, WrongPassword

# Быстрые параметры scrypt для тестов
storage.KDF_PARAMS.update(n=2 ** 10)


def test_atomic_write_replaces_whole_file(tmp_path):
    p = tmp_path / "f.bin"
    storage.atomic_write(p, b"first")
    storage.atomic_write(p, b"second")
    assert p.read_bytes() == b"second"
    assert not (tmp_path / "f.bin.tmp").exists()


def test_every_change_is_persisted_immediately(tmp_path):
    path = tmp_path / "t.sqlite3"
    db = Database(path)
    db.add_habit("Зарядка")
    # Без close(): данные уже на диске и открываются обычным SQLite
    conn = sqlite3.connect(path)
    assert conn.execute("SELECT name FROM habits").fetchall() == [("Зарядка",)]
    conn.close()


def test_corrupt_file_detected(tmp_path):
    path = tmp_path / "t.sqlite3"
    path.write_bytes(b"this is not a database" * 100)
    with pytest.raises(CorruptDatabase):
        Database(path)


def test_keyring_password_and_recovery():
    ring, code = Keyring.create("секрет")
    blob = ring.encrypt(b"hello")
    header = storage.read_header(blob)
    assert b"hello" not in blob
    assert Keyring.unlock(header, password="секрет").decrypt(blob) == b"hello"
    assert Keyring.unlock(header, recovery=code.lower().replace("-", " ")).decrypt(blob) == b"hello"
    with pytest.raises(WrongPassword):
        Keyring.unlock(header, password="не тот")
    with pytest.raises(WrongPassword):
        Keyring.unlock(header, recovery="AAAA-BBBB-CCCC-DDDD-EEEE-FFFF")


def test_tampered_ciphertext_detected():
    ring, _ = Keyring.create("pw")
    blob = bytearray(ring.encrypt(b"data" * 50))
    blob[-5] ^= 0xFF
    with pytest.raises(storage.CorruptFile):
        ring.decrypt(bytes(blob))


def test_enable_change_disable_password(tmp_path):
    s = Session.open_plain(tmp_path)
    s.db.add_task(Task(0, "Секретная задача"))
    code = s.enable_password("1234")
    assert s.encrypted
    assert not (tmp_path / storage.PLAIN_NAME).exists()
    raw = (tmp_path / storage.ENCRYPTED_NAME).read_bytes()
    assert "Секретная".encode() not in raw
    # открытые копии, сделанные до пароля, тоже зашифрованы
    assert all(b.encrypted for b in backup.list_backups(backup.backup_dir(tmp_path)))

    with pytest.raises(WrongPassword):
        Session.open_encrypted(tmp_path, password="0000")
    s2 = Session.open_encrypted(tmp_path, password="1234")
    assert [t.title for t in s2.db.list_tasks()] == ["Секретная задача"]

    # забыли пароль: вход по коду, новый пароль
    s3 = Session.open_encrypted(tmp_path, recovery=code)
    s3.change_password("новый")
    with pytest.raises(WrongPassword):
        Session.open_encrypted(tmp_path, password="1234")
    s4 = Session.open_encrypted(tmp_path, password="новый")
    new_code = s4.new_recovery_code()
    with pytest.raises(WrongPassword):
        Session.open_encrypted(tmp_path, recovery=code)
    assert Session.open_encrypted(tmp_path, recovery=new_code).db.list_tasks()

    s4.disable_password()
    assert not (tmp_path / storage.ENCRYPTED_NAME).exists()
    s5 = Session.open_plain(tmp_path)
    assert [t.title for t in s5.db.list_tasks()] == ["Секретная задача"]


def test_auto_backup_once_a_day_and_prune(tmp_path):
    s = Session.open_plain(tmp_path)
    s.db.add_habit("Чтение")
    assert s.auto_backup() is True
    assert s.auto_backup() is False          # второй раз за день — нет
    folder = backup.backup_dir(tmp_path)
    for i in range(35):
        backup.make_backup(s.db.snapshot(), s.db.store, folder, "auto",
                           now=__import__("datetime").datetime(2026, 1, 1, 10, 0, i))
    backup.make_backup(s.db.snapshot(), s.db.store, folder, "manual")
    backup.prune(folder, keep=30)
    infos = backup.list_backups(folder)
    assert sum(1 for b in infos if b.kind == "auto") == 30
    assert any(b.kind == "manual" for b in infos)


def test_extra_folder_gets_copies(tmp_path):
    data, cloud = tmp_path / "data", tmp_path / "YandexDisk"
    s = Session.open_plain(data)
    s.set_extra_dir(cloud)
    s.backup_now()
    assert len(backup.list_backups(cloud)) == 2   # при выборе папки + вручную


def test_restore_from_backup_with_safety_copy(tmp_path):
    s = Session.open_plain(tmp_path)
    s.db.add_habit("Старая")
    [path] = s.backup_now()
    s.db.add_habit("Новая")
    blob = backup.read_backup(path)
    s.restore(blob)
    assert [h.name for h in s.db.list_habits()] == ["Старая"]
    safety = [b for b in backup.list_backups(backup.backup_dir(tmp_path)) if b.kind == "safety"]
    assert len(safety) == 1
    restored = backup.read_backup(safety[0].path)
    assert {h.name for h in Database(tmp_path / "x.sqlite3", data=restored).list_habits()} == {"Старая", "Новая"}


def test_encrypted_backup_after_password_change(tmp_path):
    s = Session.open_plain(tmp_path)
    s.db.add_habit("Бег")
    s.enable_password("old")
    [path] = s.backup_now()
    s.change_password("new")
    # ключ данных не меняется — текущей сессией копия читается без пароля
    assert backup.validate(backup.read_backup(path, current=s.keyring))
    with pytest.raises(backup.NeedsSecret):
        backup.read_backup(path)
    assert backup.validate(backup.read_backup(path, password="old"))


def test_read_backup_rejects_garbage(tmp_path):
    p = tmp_path / "HabitTracker_2026-01-01_100000_manual.sqlite3"
    p.write_bytes(b"garbage")
    with pytest.raises(storage.CorruptFile):
        backup.read_backup(p)


def test_login_with_corrupt_encrypted_file_offers_repair(tmp_path, monkeypatch):
    """Верный пароль + повреждённый файл → не падение, а предложение восстановить из копии."""
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QDialog
    app = QApplication.instance() or QApplication([])
    from tracker.ui import security

    s = Session.open_plain(tmp_path)
    s.db.add_habit("Бег")
    s.enable_password("1234")
    s.backup_now()
    enc = tmp_path / storage.ENCRYPTED_NAME
    b = bytearray(enc.read_bytes()); b[-50] ^= 0xFF; enc.write_bytes(bytes(b))

    dlg = security.LoginDialog(tmp_path)
    dlg.field.setText("1234")
    dlg.accept()
    assert dlg.result() == QDialog.Accepted and dlg.corrupt is not None

    calls = []

    class FakeLogin(security.LoginDialog):
        def exec(self):
            self.field.setText("1234"); self.accept(); return QDialog.Accepted

    monkeypatch.setattr(security, "LoginDialog", FakeLogin)
    monkeypatch.setattr(security, "_repair", lambda d, r, k=None: calls.append((r, k)) or False)
    assert security.open_session(tmp_path) is None
    assert calls and "повреж" in calls[0][0] and calls[0][1] is not None


def test_repair_keeps_encryption(tmp_path, monkeypatch):
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
    app = QApplication.instance() or QApplication([])
    from tracker.ui import security

    s = Session.open_plain(tmp_path)
    s.db.add_habit("Бег")
    s.enable_password("1234")
    [good] = s.backup_now()
    ring = s.keyring
    enc = tmp_path / storage.ENCRYPTED_NAME
    enc.write_bytes(enc.read_bytes()[:-40])           # обрезанный файл

    class Pick(security.RestoreDialog):
        def exec(self):
            self.chosen = good
            return QDialog.Accepted

    monkeypatch.setattr(security, "RestoreDialog", Pick)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    assert security._repair(tmp_path, "test", ring) is True
    assert [h.name for h in Session.open_encrypted(tmp_path, password="1234").db.list_habits()] == ["Бег"]
    assert any(p.name.startswith("tracker.htenc.corrupt-") for p in tmp_path.iterdir())
