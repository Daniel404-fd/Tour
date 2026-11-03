"""Синхронизация из окна программы: фоновый поток, обновление экрана, статус."""
import os
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication

from tracker.logic import Task
from tracker.session import Session
from tests.test_webdav_sync import dav_server  # noqa: F401  (фикстура)


def wait(app, cond, timeout=15):
    end = time.time() + timeout
    while time.time() < end and not cond():
        app.processEvents()
        time.sleep(0.02)
    assert cond()


def test_window_syncs_in_background(tmp_path, dav_server, monkeypatch):
    url, _ = dav_server
    app = QApplication.instance() or QApplication([])
    from tracker.ui import theme
    theme.install(app)
    from tracker.ui.main_window import MainWindow, SETTINGS
    phone = Session.open_plain(tmp_path / "phone")
    phone.set_sync("me@yandex.ru", "app-pass", "Телефон", url=url)
    phone.db.add_task(Task(0, "Купить хлеб"))
    phone.sync_now()

    pc = Session.open_plain(tmp_path / "pc")
    pc.set_sync("me@yandex.ru", "app-pass", "ПК", url=url)
    win = MainWindow(pc)
    statuses = []
    win.sync.statusChanged.connect(lambda t, ok: statuses.append((t, ok)))
    win.sidebar.setCurrentRow(SETTINGS)
    win.sync.run()
    wait(app, lambda: not win.sync.busy)
    assert statuses[-1][1] is True and "добавлено 1" in statuses[-1][0], statuses
    assert [t.title for t in pc.db.list_tasks()] == ["Купить хлеб"]
    # правка на ПК → автосинхронизация по таймеру (ускоряем)
    from tracker.ui import sync_controller
    monkeypatch.setattr(sync_controller, "AFTER_EDIT_MS", 10)
    pc.db.add_task(Task(0, "С компьютера"))
    wait(app, lambda: win.sync.debounce.isActive() or win.sync.busy or len(statuses) > 2)
    wait(app, lambda: not win.sync.busy and not win.sync.debounce.isActive())
    phone.sync_now()
    assert sorted(t.title for t in phone.db.list_tasks()) == ["Купить хлеб", "С компьютера"]
    win.close()
