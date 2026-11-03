"""Резервные копии и настройки. Без Qt.

* Автоматическая копия — раз в день при запуске; хранятся последние KEEP_AUTO.
* Дополнительная папка (например, в Яндекс Диске или OneDrive) — копия уходит и туда,
  чтобы данные пережили поломку или переустановку компьютера.
* Если включён пароль, копии тоже зашифрованы.
* Перед восстановлением, сменой пароля и т. п. делается страховочная копия.
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from . import storage
from .storage import Keyring, atomic_write, is_encrypted, read_header

PREFIX = "HabitTracker_"
KEEP_AUTO = 30
SETTINGS_NAME = "settings.json"
_NAME_RE = re.compile(r"^HabitTracker_(\d{4}-\d{2}-\d{2})_(\d{4})(\d{2})?_([a-z-]+)\.(sqlite3|htenc)$")

KIND_NAMES = {"auto": "автоматическая", "manual": "вручную", "safety": "страховочная"}


# ---------------------------------------------------------------- настройки

class Settings:
    def __init__(self, data_dir: Path):
        self.path = Path(data_dir) / SETTINGS_NAME
        self.data: dict = {}
        try:
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.data = {}

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def set(self, key: str, value) -> None:
        if value is None:
            self.data.pop(key, None)
        else:
            self.data[key] = value
        atomic_write(self.path, json.dumps(self.data, ensure_ascii=False, indent=2).encode("utf-8"))


# ---------------------------------------------------------------- копии

@dataclass
class BackupInfo:
    path: Path
    when: datetime
    kind: str
    encrypted: bool
    size: int

    @property
    def kind_name(self) -> str:
        return KIND_NAMES.get(self.kind, self.kind)


def backup_dir(data_dir: Path) -> Path:
    return Path(data_dir) / "backups"


def _name(kind: str, encrypted: bool, now: datetime) -> str:
    ext = "htenc" if encrypted else "sqlite3"
    return f"{PREFIX}{now:%Y-%m-%d_%H%M%S}_{kind}.{ext}"


def make_backup(snapshot: bytes, store, folder: Path, kind: str = "manual",
                now: datetime | None = None) -> Path:
    from datetime import timedelta
    now = (now or datetime.now()).replace(microsecond=0)
    path = Path(folder) / _name(kind, store.encrypted, now)
    while path.exists():  # две копии за одну секунду не должны затирать друг друга
        now += timedelta(seconds=1)
        path = Path(folder) / _name(kind, store.encrypted, now)
    atomic_write(path, store.wrap_for_backup(snapshot))
    return path


def list_backups(folder: Path) -> list[BackupInfo]:
    folder = Path(folder)
    if not folder.is_dir():
        return []
    result = []
    for p in folder.iterdir():
        m = _NAME_RE.match(p.name)
        if not m or not p.is_file():
            continue
        try:
            when = datetime.strptime(m.group(1) + m.group(2) + (m.group(3) or "00"), "%Y-%m-%d%H%M%S")
            result.append(BackupInfo(p, when, m.group(4), m.group(5) == "htenc", p.stat().st_size))
        except (ValueError, OSError):
            continue
    return sorted(result, key=lambda b: b.when, reverse=True)


def prune(folder: Path, keep: int = KEEP_AUTO) -> int:
    """Удалить старые автоматические копии сверх `keep`. Ручные и страховочные не трогаем."""
    autos = [b for b in list_backups(folder) if b.kind == "auto"]
    removed = 0
    for b in autos[keep:]:
        try:
            b.path.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def backup_everywhere(snapshot: bytes, store, data_dir: Path, settings: Settings,
                      kind: str) -> list[Path]:
    """Копия в основную папку и, если задана, в дополнительную. Ошибки доп. папки не фатальны."""
    made = [make_backup(snapshot, store, backup_dir(data_dir), kind)]
    extra = settings.get("extra_backup_dir")
    if extra:
        try:
            made.append(make_backup(snapshot, store, Path(extra), kind))
            if kind == "auto":
                prune(Path(extra))
        except OSError:
            pass
    if kind == "auto":
        prune(backup_dir(data_dir))
    return made


def auto_backup(snapshot: bytes, store, data_dir: Path, settings: Settings,
                today: date | None = None) -> bool:
    """Раз в день сохранить копию — состояние на начало дня."""
    today = today or date.today()
    if settings.get("last_auto_backup") == today.isoformat():
        return False
    backup_everywhere(snapshot, store, data_dir, settings, "auto")
    settings.set("last_auto_backup", today.isoformat())
    return True


# ---------------------------------------------------------------- чтение копий

class NeedsSecret(Exception):
    """Копия зашифрована — нужен пароль или код восстановления на момент её создания."""


def validate(blob: bytes) -> bool:
    """Это целая база трекера?"""
    conn = sqlite3.connect(":memory:")
    try:
        conn.deserialize(blob)
        if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            return False
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return {"habits", "tasks"} <= tables
    except sqlite3.DatabaseError:
        return False
    finally:
        conn.close()


def read_backup(path: Path, current: Keyring | None = None, password: str | None = None,
                recovery: str | None = None) -> bytes:
    """Прочитать копию. Зашифрованную сначала пробуем текущим ключом данных
    (ключ не меняется при смене пароля), иначе нужен пароль/код того времени."""
    blob = Path(path).read_bytes()
    if not is_encrypted(blob):
        data = blob
    else:
        header = read_header(blob)
        ring = None
        if password is None and recovery is None and current is not None:
            try:
                data = current.decrypt(blob)
                ring = current
            except storage.CorruptFile:
                ring = None
        if ring is None:
            if password is None and recovery is None:
                raise NeedsSecret()
            ring = Keyring.unlock(header, password=password, recovery=recovery)
            data = ring.decrypt(blob)
    if not validate(data):
        raise storage.CorruptFile("Копия повреждена или это не файл трекера")
    return data


def encrypt_plain_backups(folder: Path, keyring: Keyring) -> int:
    """При включении пароля — зашифровать старые открытые копии, чтобы не оставлять данные открытыми."""
    n = 0
    for b in list_backups(folder):
        if b.encrypted:
            continue
        try:
            blob = b.path.read_bytes()
            target = b.path.with_suffix(".htenc")
            atomic_write(target, keyring.encrypt(blob))
            b.path.unlink()
            n += 1
        except OSError:
            pass
    return n
