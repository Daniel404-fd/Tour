"""Минимальный клиент WebDAV (Яндекс Диск: https://webdav.yandex.ru) и процесс синхронизации.
Без Qt, только стандартная библиотека."""
from __future__ import annotations

import base64
import ssl
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass

YANDEX_URL = "https://webdav.yandex.ru"
FOLDER = "HabitTracker-sync"
TIMEOUT = 25


class SyncError(Exception):
    """Понятное человеку описание, что пошло не так."""


@dataclass
class RemoteFile:
    name: str
    etag: str
    size: int


class WebDav:
    def __init__(self, base_url: str, login: str, password: str, folder: str = FOLDER):
        self.base = base_url.rstrip("/")
        self.folder = folder.strip("/")
        token = base64.b64encode(f"{login}:{password}".encode("utf-8")).decode("ascii")
        self.headers = {"Authorization": f"Basic {token}", "User-Agent": "HabitTracker/2.4"}
        self.ctx = ssl.create_default_context()

    def _url(self, name: str = "") -> str:
        path = "/" + urllib.parse.quote(self.folder) + "/"
        if name:
            path += urllib.parse.quote(name)
        return self.base + path

    def _req(self, method: str, url: str, data: bytes | None = None,
             headers: dict | None = None) -> tuple[int, bytes, dict]:
        req = urllib.request.Request(url, data=data, method=method, headers={**self.headers, **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT, context=self.ctx) as r:
                return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read() if e.fp else b"", dict(e.headers or {})
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise SyncError("Нет соединения с Яндекс Диском. Проверьте интернет.") from e

    @staticmethod
    def _check(status: int, what: str) -> None:
        if status == 401:
            raise SyncError("Яндекс Диск не принял логин или пароль приложения. "
                            "Проверьте их в настройках синхронизации.")
        if status == 403:
            raise SyncError("Яндекс Диск запретил доступ. Создайте пароль приложения для «Файлов» (WebDAV).")
        if status == 507:
            raise SyncError("На Яндекс Диске закончилось место.")
        if status >= 400:
            raise SyncError(f"Яндекс Диск ответил ошибкой {status} ({what}).")

    def ensure_folder(self) -> None:
        status, _, _ = self._req("MKCOL", self._url())
        if status not in (201, 405, 409):   # 405 — папка уже есть
            self._check(status, "создание папки")

    def list(self) -> list[RemoteFile]:
        status, body, _ = self._req("PROPFIND", self._url(), headers={"Depth": "1",
                                    "Content-Type": "application/xml"},
                                    data=b'<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop>'
                                         b'<d:getetag/><d:getcontentlength/><d:resourcetype/>'
                                         b'</d:prop></d:propfind>')
        if status == 404:
            return []
        self._check(status, "список файлов")
        ns = {"d": "DAV:"}
        out = []
        for resp in ET.fromstring(body).findall("d:response", ns):
            href = urllib.parse.unquote(resp.findtext("d:href", "", ns))
            name = href.rstrip("/").rsplit("/", 1)[-1]
            prop = resp.find("d:propstat/d:prop", ns)
            if prop is None or prop.find("d:resourcetype/d:collection", ns) is not None:
                continue
            etag = (prop.findtext("d:getetag", "", ns) or "").strip('"')
            size = int(prop.findtext("d:getcontentlength", "0", ns) or 0)
            out.append(RemoteFile(name, etag, size))
        return out

    def get(self, name: str) -> bytes:
        status, body, _ = self._req("GET", self._url(name))
        self._check(status, f"загрузка {name}")
        return body

    def put(self, name: str, data: bytes) -> None:
        status, _, _ = self._req("PUT", self._url(name), data=data,
                                 headers={"Content-Type": "application/octet-stream"})
        self._check(status, f"отправка {name}")


# ---------------------------------------------------------------- процесс

def device_file(device_id: str) -> str:
    return f"device-{device_id}.json.gz"


def fetch_remote(dav: WebDav, own_device: str, cache: dict) -> tuple[list[dict], dict]:
    """Скачать файлы других устройств. cache: {имя: etag} — неизменившиеся не качаем повторно.
    Возвращает (данные изменившихся устройств, новый cache)."""
    from . import sync
    dav.ensure_folder()
    payloads, new_cache = [], {}
    for f in dav.list():
        if not f.name.startswith("device-") or f.name == device_file(own_device):
            continue
        new_cache[f.name] = f.etag
        if f.etag and cache.get(f.name) == f.etag:
            continue
        try:
            payloads.append(sync.decode(dav.get(f.name)))
        except (ValueError, OSError) as e:
            raise SyncError(f"Файл {f.name} на Диске повреждён или от новой версии программы.") from e
    return payloads, new_cache
