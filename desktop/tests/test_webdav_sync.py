"""ПК и «телефон» синхронизируются через настоящий WebDAV-сервер (локальный, как Яндекс Диск)."""
import socket
import threading
import time
from datetime import date

import pytest

from tracker.logic import Task
from tracker.session import Session
from tracker.webdav import SyncError, WebDav


@pytest.fixture
def dav_server(tmp_path):
    from cheroot import wsgi
    from wsgidav.wsgidav_app import WsgiDAVApp
    root = tmp_path / "disk"
    root.mkdir()
    sock = socket.socket(); sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]; sock.close()
    app = WsgiDAVApp({
        "provider_mapping": {"/": str(root)},
        "http_authenticator": {"domain_controller": None, "accept_basic": True, "accept_digest": False,
                               "default_to_digest": False},
        "simple_dc": {"user_mapping": {"*": {"me@yandex.ru": {"password": "app-pass"}}}},
        "verbose": 0, "logging": {"enable": False},
    })
    server = wsgi.Server(("127.0.0.1", port), app)
    t = threading.Thread(target=server.start, daemon=True)
    t.start()
    time.sleep(0.5)
    yield f"http://127.0.0.1:{port}", root
    server.stop()


def session(tmp_path, name, url, device):
    s = Session.open_plain(tmp_path / name)
    s.set_sync("me@yandex.ru", "app-pass", device, url=url)
    return s


def test_pc_and_phone_sync_through_webdav(tmp_path, dav_server):
    url, root = dav_server
    pc = session(tmp_path, "pc", url, "ПК")
    phone = session(tmp_path, "phone", url, "Телефон")
    pc.db.add_task(Task(0, "С компьютера"))
    h = pc.db.add_habit("Зарядка")
    pc.db.set_mark(h, date(2026, 11, 3), True)
    pc.sync_now()
    phone.sync_now()
    assert [t.title for t in phone.db.list_tasks()] == ["С компьютера"]
    phone.db.add_task(Task(0, "С телефона"))
    phone.sync_now()
    stats = pc.sync_now()
    assert stats.added == 1
    assert sorted(t.title for t in pc.db.list_tasks()) == ["С компьютера", "С телефона"]
    files = sorted(p.name for p in (root / "HabitTracker-sync").iterdir())
    assert len(files) == 2 and all(f.startswith("device-") for f in files)
    # ничего не менялось — второй раз файл телефона не скачивается
    assert not pc.sync_now().changed


def test_wrong_password_gives_clear_error(tmp_path, dav_server):
    url, _ = dav_server
    s = Session.open_plain(tmp_path / "x")
    s.set_sync("me@yandex.ru", "wrong", "ПК", url=url)
    with pytest.raises(SyncError, match="логин или пароль"):
        s.sync_now()


def test_no_network_gives_clear_error(tmp_path):
    s = Session.open_plain(tmp_path / "x")
    s.set_sync("me@yandex.ru", "p", "ПК", url="http://127.0.0.1:9")
    with pytest.raises(SyncError, match="Нет соединения"):
        s.sync_now()


def test_password_not_stored_in_plain_text(tmp_path):
    s = Session.open_plain(tmp_path / "x")
    s.set_sync("me@yandex.ru", "секрет123", "ПК")
    text = (tmp_path / "x" / "settings.json").read_text(encoding="utf-8")
    assert "секрет123" not in text
    from tracker.secret import unprotect
    assert unprotect(s.sync_settings["password"]) == "секрет123"
