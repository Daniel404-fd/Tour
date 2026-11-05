"""Синхронизация между устройствами (ПК, телефон). Без Qt.

Как это устроено
----------------
* У каждой записи есть постоянный глобальный номер `sync_uid` и время последнего изменения
  `sync_ts` (UTC, «2026-11-03T17:04:05.123Z» — строки сравниваются как время).
  Их ставят триггеры SQLite, поэтому обычный код программы о синхронизации не знает.
* Удаление оставляет «надгробие» в `sync_tombstones` — иначе другое устройство вернуло бы запись.
* Каждое устройство пишет в общую папку (Яндекс Диск) только СВОЙ файл со всеми записями,
  которые знает. Чужие файлы только читает. Поэтому два устройства никогда не перезаписывают
  друг друга, а слияние повторяемо: сколько ни сливай, результат тот же.
* Слияние по записям: побеждает более позднее изменение. Удаление побеждает, если оно позже
  последней правки записи.
* Ссылки между таблицами (задача → тема, шаг → цель…) в файле записаны через sync_uid,
  потому что числовые id на разных устройствах разные.

Формат файла (общий для ПК и Android): gzip(JSON)
  {"format": 1, "device": "<id>", "device_name": "...", "generated": "<ts>",
   "records": {"<таблица>": [{"uid": "...", "ts": "...", "data": {...}}]},
   "tombstones": [{"uid": "...", "table": "...", "ts": "..."}]}
"""
from __future__ import annotations

import gzip
import json
import sqlite3
import uuid
from datetime import datetime, timezone

FORMAT = 1
DEFAULT_CALENDAR_UID = "calendar-default"   # «Личное» — один и тот же на всех устройствах

NOW_SQL = "strftime('%Y-%m-%dT%H:%M:%fZ','now')"
UID_SQL = "lower(hex(randomblob(16)))"

# Таблица → (поля данных, ссылки {поле: таблица}). Порядок — сначала «родители».
TABLES: dict[str, tuple[list[str], dict[str, str]]] = {
    "topics": (["name", "color"], {}),
    "habits": (["name", "archived", "created_on"], {}),
    "habit_marks": (["habit_id", "day"], {"habit_id": "habits"}),
    "note_folders": (["name"], {}),
    "calendars": (["name", "color", "visible"], {}),
    "goals": (["title", "description", "target_date", "done", "archived", "created_on",
               "completed_on", "financial", "target_amount"], {}),
    "goal_steps": (["goal_id", "title", "done", "position"], {"goal_id": "goals"}),
    "goal_contributions": (["goal_id", "day", "amount", "note"], {"goal_id": "goals"}),
    "boards": (["name", "color", "position", "archived"], {}),
    "board_columns": (["board_id", "name", "position", "is_done"], {"board_id": "boards"}),
    "tasks": (["title", "description", "deadline", "priority", "done", "completed_on", "archived",
               "topic_id", "board_id", "column_id", "position"],
              {"topic_id": "topics", "board_id": "boards", "column_id": "board_columns"}),
    "task_subtasks": (["task_id", "title", "done", "position"], {"task_id": "tasks"}),
    "notes": (["title", "body", "pinned", "created_at", "updated_at", "folder_id", "board_id"],
              {"folder_id": "note_folders", "board_id": "boards"}),
    "events": (["title", "start", "end", "all_day", "calendar_id", "color", "description",
                "location", "freq", "interval", "weekdays", "until", "exdates", "reminder"],
               {"calendar_id": "calendars"}),
}
# Без какой ссылки запись не имеет смысла (иначе ссылка просто обнуляется).
REQUIRED_REFS = {("habit_marks", "habit_id"), ("goal_steps", "goal_id"),
                 ("goal_contributions", "goal_id"), ("events", "calendar_id"),
                 ("task_subtasks", "task_id"), ("board_columns", "board_id")}


def now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _q(name: str) -> str:
    return f'"{name}"'


# ---------------------------------------------------------------- схема

def install(conn: sqlite3.Connection) -> None:
    """Добавить колонки, надгробия и триггеры. Безопасно вызывать при каждом открытии."""
    conn.execute("CREATE TABLE IF NOT EXISTS sync_tombstones ("
                 " uid TEXT PRIMARY KEY, tbl TEXT NOT NULL, ts TEXT NOT NULL)")
    for table in TABLES:
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        if "sync_uid" not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN sync_uid TEXT")
        if "sync_ts" not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN sync_ts TEXT")
    # Общий для всех устройств календарь по умолчанию
    if not conn.execute("SELECT 1 FROM calendars WHERE sync_uid = ?", (DEFAULT_CALENDAR_UID,)).fetchone():
        first = conn.execute("SELECT id FROM calendars WHERE sync_uid IS NULL ORDER BY id LIMIT 1").fetchone()
        if first:
            conn.execute("UPDATE calendars SET sync_uid = ? WHERE id = ?", (DEFAULT_CALENDAR_UID, first[0]))
    # Проставить номера записям, созданным до синхронизации
    for table in TABLES:
        if table == "habit_marks":
            continue
        conn.execute(f"UPDATE {table} SET sync_uid = {UID_SQL} WHERE sync_uid IS NULL")
    conn.execute("UPDATE habit_marks SET sync_uid = (SELECT h.sync_uid FROM habits h WHERE h.id ="
                 " habit_marks.habit_id) || ':' || day WHERE sync_uid IS NULL")
    for table in TABLES:
        conn.execute(f"UPDATE {table} SET sync_ts = {NOW_SQL} WHERE sync_ts IS NULL")
        conn.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS {table}_sync_uid ON {table}(sync_uid)")
        _triggers(conn, table)


def _triggers(conn: sqlite3.Connection, table: str) -> None:
    if table == "habit_marks":
        # отметка привычки за день — естественный ключ: «uid привычки:дата»
        new_uid = ("COALESCE(NEW.sync_uid, (SELECT h.sync_uid FROM habits h WHERE h.id = NEW.habit_id)"
                   " || ':' || NEW.day)")
    else:
        new_uid = f"COALESCE(NEW.sync_uid, {UID_SQL})"
    conn.executescript(f"""
        CREATE TRIGGER IF NOT EXISTS {table}_sync_ins AFTER INSERT ON {table} BEGIN
            UPDATE {table} SET sync_uid = {new_uid}, sync_ts = COALESCE(NEW.sync_ts, {NOW_SQL})
             WHERE rowid = NEW.rowid;
            DELETE FROM sync_tombstones WHERE uid = (SELECT sync_uid FROM {table} WHERE rowid = NEW.rowid);
        END;
        CREATE TRIGGER IF NOT EXISTS {table}_sync_upd AFTER UPDATE ON {table}
        WHEN NEW.sync_ts IS OLD.sync_ts BEGIN
            UPDATE {table} SET sync_ts = {NOW_SQL} WHERE rowid = NEW.rowid;
        END;
        CREATE TRIGGER IF NOT EXISTS {table}_sync_del AFTER DELETE ON {table}
        WHEN OLD.sync_uid IS NOT NULL BEGIN
            INSERT OR REPLACE INTO sync_tombstones(uid, tbl, ts) VALUES (OLD.sync_uid, '{table}', {NOW_SQL});
        END;
    """)


# ---------------------------------------------------------------- экспорт

def export_payload(conn: sqlite3.Connection, device_id: str, device_name: str) -> dict:
    uid_of: dict[str, dict[int, str]] = {}
    records: dict[str, list] = {}
    for table, (fields, refs) in TABLES.items():
        rows = conn.execute(f"SELECT id, sync_uid, sync_ts, {', '.join(_q(f) for f in fields)} FROM {table}"
                            if table != "habit_marks" else
                            f"SELECT rowid, sync_uid, sync_ts, {', '.join(fields)} FROM {table}").fetchall()
        uid_of[table] = {r[0]: r[1] for r in rows}
        out = []
        for r in rows:
            data = dict(zip(fields, r[3:]))
            for f, ref_table in refs.items():
                if data[f] is not None:
                    data[f] = uid_of[ref_table].get(data[f])
            out.append({"uid": r[1], "ts": r[2], "data": data})
        records[table] = out
    tombs = [{"uid": u, "table": t, "ts": ts} for u, t, ts in
             conn.execute("SELECT uid, tbl, ts FROM sync_tombstones")]
    return {"format": FORMAT, "device": device_id, "device_name": device_name,
            "generated": now_ts(), "records": records, "tombstones": tombs}


def encode(payload: dict) -> bytes:
    return gzip.compress(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def decode(blob: bytes) -> dict:
    data = json.loads(gzip.decompress(blob).decode("utf-8"))
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        raise ValueError("Неизвестный формат файла синхронизации")
    return data


# ---------------------------------------------------------------- слияние

class MergeStats:
    def __init__(self):
        self.added = self.updated = self.deleted = 0

    @property
    def changed(self) -> bool:
        return bool(self.added or self.updated or self.deleted)

    def __repr__(self) -> str:
        return f"MergeStats(+{self.added} ~{self.updated} -{self.deleted})"


def _digest(data: dict) -> str:
    import hashlib
    return hashlib.sha1(json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)
                        .encode("utf-8")).hexdigest()


def _local_canon(conn: sqlite3.Connection, table: str, key: str, rid) -> dict:
    """Локальная запись в том же виде, что в файле синхронизации (ссылки — через uid)."""
    fields, refs = TABLES[table]
    row = conn.execute(f"SELECT {', '.join(_q(f) for f in fields)} FROM {table} WHERE {key} = ?",
                       (rid,)).fetchone()
    data = dict(zip(fields, row))
    for f, ref_table in refs.items():
        if data[f] is not None:
            r = conn.execute(f"SELECT sync_uid FROM {ref_table} WHERE id = ?", (data[f],)).fetchone()
            data[f] = r[0] if r else None
    return data


def merge(conn: sqlite3.Connection, payload: dict, stats: MergeStats | None = None) -> MergeStats:
    """Слить данные другого устройства в локальную базу. Коммит — на вызывающем."""
    stats = stats or MergeStats()
    tombs_local = {u: ts for u, ts in conn.execute("SELECT uid, ts FROM sync_tombstones")}
    remote_tombs = {t["uid"]: t for t in payload.get("tombstones", [])}

    for table, (fields, refs) in TABLES.items():
        key = "rowid" if table == "habit_marks" else "id"
        local = {r[0]: (r[1], r[2]) for r in
                 conn.execute(f"SELECT sync_uid, {key}, sync_ts FROM {table}")}
        for rec in payload.get("records", {}).get(table, []):
            uid, ts, data = rec["uid"], rec["ts"], dict(rec["data"])
            if uid in remote_tombs and remote_tombs[uid]["ts"] >= ts:
                continue
            if uid in tombs_local and tombs_local[uid] >= ts:
                continue          # у нас удалено позже, чем там изменено
            ok = True
            for f, ref_table in refs.items():
                if data.get(f) is None:
                    continue
                row = conn.execute(f"SELECT id FROM {ref_table} WHERE sync_uid = ?", (data[f],)).fetchone()
                if row is None:
                    if (table, f) in REQUIRED_REFS:
                        ok = False
                        break
                    data[f] = None
                else:
                    data[f] = row[0]
            if not ok:
                continue
            cur = local.get(uid)
            # поля, которых нет в файле (его записала прежняя версия программы), не трогаем:
            # при вставке берётся значение по умолчанию, при обновлении остаётся наше
            present = [f for f in fields if f in rec["data"]]
            values = [data.get(f) for f in present]
            if cur is None:
                if table == "habit_marks":
                    # та же отметка могла появиться независимо — естественный ключ
                    conn.execute("DELETE FROM habit_marks WHERE habit_id = ? AND day = ? AND sync_uid IS NOT ?",
                                 (data["habit_id"], data["day"], uid))
                cols = "".join(_q(f) + ", " for f in present)
                ph = "".join("?, " for _ in present)
                conn.execute(f"INSERT INTO {table} ({cols}sync_uid, sync_ts) VALUES ({ph}?, ?)",
                             (*values, uid, ts))
                stats.added += 1
            elif ts > (cur[1] or "") or (
                    ts == cur[1] and _digest(rec["data"]) > _digest(_local_canon(conn, table, key, cur[0]))):
                # при одинаковом времени побеждает одна и та же версия на всех устройствах
                sets = "".join(f"{_q(f)} = ?, " for f in present)
                conn.execute(f"UPDATE {table} SET {sets}sync_ts = ? WHERE {key} = ?", (*values, ts, cur[0]))
                stats.updated += 1

    # удаления (сначала «дети», чтобы не задеть каскадом лишнего)
    for table in reversed(list(TABLES)):
        key = "rowid" if table == "habit_marks" else "id"
        for t in (x for x in remote_tombs.values() if x["table"] == table):
            row = conn.execute(f"SELECT {key}, sync_ts FROM {table} WHERE sync_uid = ?", (t["uid"],)).fetchone()
            if row is not None and (row[1] or "") <= t["ts"]:
                conn.execute(f"DELETE FROM {table} WHERE {key} = ?", (row[0],))
                # триггер записал надгробие с текущим временем — ставим исходное время удаления
                conn.execute("UPDATE sync_tombstones SET ts = ? WHERE uid = ?", (t["ts"], t["uid"]))
                stats.deleted += 1
            elif row is None:
                conn.execute("INSERT INTO sync_tombstones(uid, tbl, ts) VALUES (?, ?, ?)"
                             " ON CONFLICT(uid) DO UPDATE SET ts = MAX(ts, excluded.ts)",
                             (t["uid"], table, t["ts"]))
    return stats


def new_device_id() -> str:
    return uuid.uuid4().hex[:12]
