"""Вложения заметок: файлы и фото.

Файлы лежат рядом с базой, в папке «attachments» (имя — случайное, расширение — как у оригинала),
а в базе — запись: к какой заметке, исходное имя, размер, тип. Синхронизация: записи едут вместе
с остальными данными, сами файлы — в папку «HabitTracker-sync/files» на Яндекс Диске
(каждый файл отправляется один раз; на другом устройстве скачивается, когда понадобится).
"""
from __future__ import annotations

import mimetypes
import os
import shutil
import uuid
from pathlib import Path

ATT_DIR = "attachments"
MAX_SIZE = 50 * 1024 * 1024          # 50 МБ на файл — чтобы синхронизация не вставала
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".heic", ".heif"}
TEXT_EXT = {".txt", ".md", ".csv", ".json", ".log", ".xml", ".ini", ".py", ".yaml", ".yml", ".html"}


class AttachmentError(Exception):
    pass


def folder(db) -> Path:
    return Path(db.store.path).parent / ATT_DIR


def path_of(db, stored: str) -> Path:
    return folder(db) / stored


def kind(name: str) -> str:
    ext = Path(name).suffix.lower()
    if ext in IMAGE_EXT:
        return "image"
    if ext == ".pdf":
        return "pdf"
    if ext in TEXT_EXT:
        return "text"
    return "file"


def human_size(n: int) -> str:
    for unit, k in (("ГБ", 1 << 30), ("МБ", 1 << 20), ("КБ", 1 << 10)):
        if n >= k:
            return f"{n / k:.1f} {unit}".replace(".0 ", " ").replace(".", ",")
    return f"{n} Б"


def add_file(db, note_id: int, src: str | Path, name: str | None = None) -> int:
    src = Path(src)
    size = src.stat().st_size
    if size > MAX_SIZE:
        raise AttachmentError(f"Файл «{src.name}» больше {MAX_SIZE >> 20} МБ — такие лучше хранить в облаке и вставить ссылку.")
    return add_bytes(db, note_id, src.read_bytes(), name or src.name)


def add_bytes(db, note_id: int, data: bytes, name: str) -> int:
    if len(data) > MAX_SIZE:
        raise AttachmentError(f"Файл больше {MAX_SIZE >> 20} МБ.")
    ext = Path(name).suffix.lower()[:10]
    stored = uuid.uuid4().hex + ext
    d = folder(db)
    d.mkdir(parents=True, exist_ok=True)
    tmp = d / (stored + ".part")
    tmp.write_bytes(data)
    os.replace(tmp, d / stored)
    mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
    return db.add_attachment(note_id, name, stored, len(data), mime)


def remove(db, att_id: int) -> None:
    att = db.get_attachment(att_id)
    db.delete_attachment(att_id)
    if att and not any(a.file == att.file for a in db.list_attachments()):
        try:
            path_of(db, att.file).unlink(missing_ok=True)
        except OSError:
            pass


def save_copy(db, att, dest: str | Path) -> None:
    shutil.copy2(path_of(db, att.file), dest)


def cleanup(db) -> int:
    """Удалить файлы, на которые больше нет записей (например, заметку удалили на телефоне)."""
    d = folder(db)
    if not d.is_dir():
        return 0
    wanted = {a.file for a in db.list_attachments()}
    n = 0
    for f in d.iterdir():
        if f.is_file() and f.name not in wanted and not f.name.endswith(".part"):
            try:
                f.unlink()
                n += 1
            except OSError:
                pass
    return n


def sync_files(dav, local_dir: Path, wanted: set[str]) -> tuple[int, int]:
    """Отправить свои новые файлы и скачать недостающие. Вызывается в фоне после синхронизации данных."""
    from .webdav import WebDav
    files = WebDav.__new__(WebDav)
    files.__dict__.update(dav.__dict__)
    files.folder = dav.folder + "/files"
    remote = {f.name for f in files.list()}
    if not remote:
        files.ensure_folder()
    up = down = 0
    local_dir.mkdir(parents=True, exist_ok=True)
    for name in sorted(wanted):
        p = local_dir / name
        if p.exists() and name not in remote:
            files.put(name, p.read_bytes())
            up += 1
        elif not p.exists() and name in remote:
            data = files.get(name)
            tmp = local_dir / (name + ".part")
            tmp.write_bytes(data)
            os.replace(tmp, p)
            down += 1
    return up, down
