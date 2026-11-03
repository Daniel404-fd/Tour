"""Открытая база + хранилище + настройки: включение пароля, копии, восстановление. Без Qt."""
from __future__ import annotations

from pathlib import Path

from . import backup
from .db import Database
from .storage import (
    ENCRYPTED_NAME, PLAIN_NAME, EncryptedStore, Keyring, PlainStore, current_file, read_header,
)

MIN_PASSWORD = 4


class Session:
    def __init__(self, data_dir: Path, db: Database):
        self.data_dir = Path(data_dir)
        self.db = db
        self.settings = backup.Settings(self.data_dir)

    # ---- открытие ----

    @staticmethod
    def locate(data_dir: Path) -> tuple[Path, bool]:
        path, encrypted = current_file(data_dir)
        if path is None:
            return Path(data_dir) / PLAIN_NAME, False
        return path, encrypted

    @classmethod
    def open_plain(cls, data_dir: Path, on_save_error=None) -> "Session":
        path, _ = cls.locate(data_dir)
        return cls(data_dir, Database(store=PlainStore(path), on_save_error=on_save_error))

    @classmethod
    def open_encrypted(cls, data_dir: Path, password: str | None = None,
                       recovery: str | None = None, on_save_error=None) -> "Session":
        """WrongPassword — неверный пароль/код; CorruptFile/CorruptDatabase — файл повреждён."""
        path = Path(data_dir) / ENCRYPTED_NAME
        header = read_header(path.read_bytes())
        ring = Keyring.unlock(header, password=password, recovery=recovery)
        store = EncryptedStore(path, ring)
        return cls(data_dir, Database(store=store, on_save_error=on_save_error))

    @classmethod
    def open_with_keyring(cls, data_dir: Path, ring: Keyring, on_save_error=None) -> "Session":
        store = EncryptedStore(Path(data_dir) / ENCRYPTED_NAME, ring)
        return cls(data_dir, Database(store=store, on_save_error=on_save_error))

    @property
    def encrypted(self) -> bool:
        return self.db.store.encrypted

    @property
    def keyring(self) -> Keyring | None:
        return self.db.store.keyring if self.encrypted else None

    def folders(self) -> list[Path]:
        result = [backup.backup_dir(self.data_dir)]
        extra = self.settings.get("extra_backup_dir")
        if extra:
            result.append(Path(extra))
        return result

    # ---- копии ----

    def auto_backup(self) -> bool:
        return backup.auto_backup(self.db.snapshot(), self.db.store, self.data_dir, self.settings)

    def backup_now(self, kind: str = "manual") -> list[Path]:
        return backup.backup_everywhere(self.db.snapshot(), self.db.store, self.data_dir,
                                        self.settings, kind)

    def restore(self, blob: bytes) -> None:
        """Заменить данные копией; текущее состояние сначала уходит в страховочную копию."""
        self.backup_now("safety")
        self.db.replace_content(blob)
        self.settings.set("sync_cache", None)   # при следующей синхронизации перечитать всё

    def set_extra_dir(self, folder: Path | None) -> None:
        self.settings.set("extra_backup_dir", str(folder) if folder else None)
        if folder:
            backup.make_backup(self.db.snapshot(), self.db.store, Path(folder), "manual")

    # ---- пароль ----

    def enable_password(self, password: str) -> str:
        """Зашифровать базу и копии. Возвращает код восстановления — показать один раз."""
        self.backup_now("safety")
        ring, code = Keyring.create(password)
        self.db.set_store(EncryptedStore(self.data_dir / ENCRYPTED_NAME, ring))
        self._remove(self.data_dir / PLAIN_NAME)
        for folder in self.folders():
            backup.encrypt_plain_backups(folder, ring)
        return code

    def change_password(self, new_password: str) -> None:
        self.keyring.set_password(new_password)
        self.db.save()

    def new_recovery_code(self) -> str:
        code = self.keyring.new_recovery()
        self.db.save()
        return code

    def disable_password(self) -> None:
        """Снять шифрование. Старые зашифрованные копии остаются — их откроет пароль того времени."""
        self.backup_now("safety")
        self.db.set_store(PlainStore(self.data_dir / PLAIN_NAME))
        self._remove(self.data_dir / ENCRYPTED_NAME)

    @staticmethod
    def _remove(path: Path) -> None:
        for p in (path, path.with_name(path.name + ".tmp")):
            try:
                p.unlink()
            except FileNotFoundError:
                pass

    # ---- синхронизация через Яндекс Диск ----

    @property
    def sync_settings(self) -> dict:
        return dict(self.settings.get("sync") or {})

    @property
    def sync_enabled(self) -> bool:
        s = self.sync_settings
        return bool(s.get("enabled") and s.get("login") and s.get("password"))

    def set_sync(self, login: str, password: str, device_name: str, url: str | None = None) -> None:
        from .secret import protect
        self.settings.set("sync", {"enabled": True, "login": login.strip(),
                                   "password": protect(password), "device_name": device_name.strip() or "ПК",
                                   "url": url or None})
        self.settings.set("sync_cache", None)

    def disable_sync(self) -> None:
        s = self.sync_settings
        s["enabled"] = False
        self.settings.set("sync", s)

    def dav(self):
        from .secret import unprotect
        from .webdav import YANDEX_URL, WebDav
        s = self.sync_settings
        return WebDav(s.get("url") or YANDEX_URL, s.get("login", ""), unprotect(s.get("password")))

    # шаги разделены: сеть можно делать в фоне, слияние — в основном потоке (база не потокобезопасна)
    def sync_fetch(self, device_id: str | None = None) -> tuple[list[dict], dict]:
        """Сетевой шаг: можно вызывать в фоновом потоке, если device_id передан заранее."""
        from .webdav import fetch_remote
        return fetch_remote(self.dav(), device_id or self.db.device_id(),
                            dict(self.settings.get("sync_cache") or {}))

    def sync_apply(self, payloads: list[dict], cache: dict):
        stats = self.db.sync_merge(payloads)
        blob = self.db.sync_export(self.sync_settings.get("device_name") or "ПК")
        return stats, blob, cache

    def sync_upload(self, blob: bytes, cache: dict, device_id: str | None = None) -> None:
        from .webdav import device_file
        self.dav().put(device_file(device_id or self.db.device_id()), blob)
        self.settings.set("sync_cache", cache)
        from .sync import now_ts
        self.settings.set("last_sync", now_ts())

    def sync_now(self):
        """Всё сразу (для тестов и простых случаев)."""
        payloads, cache = self.sync_fetch()
        stats, blob, cache = self.sync_apply(payloads, cache)
        self.sync_upload(blob, cache)
        return stats
