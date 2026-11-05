"""Своя папка для данных: например, на другом диске или в папке облака.

Где лежат данные, записано в маленьком файле location.json в обычной папке программы
(%APPDATA%\\HabitTracker). Без него — всё по-старому. Перенос копирует файлы и проверяет копию;
старые файлы остаются на месте как запасная копия.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from .backup import SETTINGS_NAME
from .storage import ENCRYPTED_NAME, PLAIN_NAME

APP_DIR_NAME = "HabitTracker"
LOCATION_NAME = "location.json"
MOVED_FILES = [PLAIN_NAME, ENCRYPTED_NAME, SETTINGS_NAME, "sidebar.png"]
MOVED_DIRS = ["backups"]


def home_dir() -> Path:
    """Обычная папка программы — тут всегда лежит location.json."""
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path.home() / ".local" / "share"
    return base / APP_DIR_NAME


def configured_dir(home: Path | None = None) -> Path:
    home = home or home_dir()
    try:
        data = json.loads((home / LOCATION_NAME).read_text(encoding="utf-8"))
        p = Path(data["data_dir"])
        if p.is_dir():
            return p
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return home


def has_data(folder: Path) -> bool:
    return (folder / PLAIN_NAME).exists() or (folder / ENCRYPTED_NAME).exists()


def set_location(folder: Path | None, home: Path | None = None) -> None:
    home = home or home_dir()
    home.mkdir(parents=True, exist_ok=True)
    loc = home / LOCATION_NAME
    if folder is None or Path(folder).resolve() == home.resolve():
        loc.unlink(missing_ok=True)
        return
    tmp = loc.with_suffix(".tmp")
    tmp.write_text(json.dumps({"data_dir": str(Path(folder).resolve())}, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, loc)


def copy_data(src: Path, dst: Path) -> list[str]:
    """Скопировать данные программы из src в dst и проверить копию. Возвращает скопированное."""
    src, dst = Path(src), Path(dst)
    if src.resolve() == dst.resolve():
        raise ValueError("Это та же самая папка.")
    try:
        Path(dst.resolve()).relative_to(src.resolve() / "backups")
        raise ValueError("Нельзя выбрать папку внутри папки резервных копий.")
    except ValueError as e:
        if "Нельзя" in str(e):
            raise
    dst.mkdir(parents=True, exist_ok=True)
    probe = dst / ".habittracker-write-test"
    probe.write_bytes(b"ok")          # нет прав на запись — узнаем сразу, до копирования
    probe.unlink()
    done = []
    for name in MOVED_FILES:
        f = src / name
        if f.exists():
            shutil.copy2(f, dst / name)
            if (dst / name).read_bytes() != f.read_bytes():
                raise OSError(f"Копия файла {name} не совпала с оригиналом.")
            done.append(name)
    for name in MOVED_DIRS:
        d = src / name
        if d.is_dir():
            shutil.copytree(d, dst / name, dirs_exist_ok=True)
            done.append(name + "/")
    return done
