"""Схема SQLite и запросы. Без Qt."""
from __future__ import annotations

import os
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

from .logic import Contribution, Goal, GoalStep, Habit, Note, NoteFolder, Task, Topic
from .cal import EVENT_COLORS, CalendarInfo, Event
from . import sync
from .storage import PlainStore

APP_DIR_NAME = "HabitTracker"
DB_FILE_NAME = "tracker.sqlite3"

SCHEMA = """
CREATE TABLE IF NOT EXISTS habits (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL,
    archived   INTEGER NOT NULL DEFAULT 0,
    created_on TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS habit_marks (
    habit_id INTEGER NOT NULL REFERENCES habits(id) ON DELETE CASCADE,
    day      TEXT    NOT NULL,
    PRIMARY KEY (habit_id, day)
);
CREATE TABLE IF NOT EXISTS tasks (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT    NOT NULL,
    description  TEXT    NOT NULL DEFAULT '',
    deadline     TEXT,
    priority     INTEGER NOT NULL DEFAULT 1,
    done         INTEGER NOT NULL DEFAULT 0,
    completed_on TEXT,
    archived     INTEGER NOT NULL DEFAULT 0,
    topic_id     INTEGER REFERENCES topics(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS topics (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT NOT NULL,
    color TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS goals (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT    NOT NULL,
    description  TEXT    NOT NULL DEFAULT '',
    target_date  TEXT,
    done         INTEGER NOT NULL DEFAULT 0,
    archived     INTEGER NOT NULL DEFAULT 0,
    created_on   TEXT    NOT NULL,
    completed_on TEXT,
    financial    INTEGER NOT NULL DEFAULT 0,
    target_amount REAL   NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS goal_steps (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id  INTEGER NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    title    TEXT    NOT NULL,
    done     INTEGER NOT NULL DEFAULT 0,
    position INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS goal_contributions (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    goal_id INTEGER NOT NULL REFERENCES goals(id) ON DELETE CASCADE,
    day     TEXT    NOT NULL,
    amount  REAL    NOT NULL,
    note    TEXT    NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS note_folders (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS calendars (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT    NOT NULL,
    color   TEXT    NOT NULL,
    visible INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT    NOT NULL,
    start       TEXT    NOT NULL,
    end         TEXT    NOT NULL,
    all_day     INTEGER NOT NULL DEFAULT 0,
    calendar_id INTEGER REFERENCES calendars(id) ON DELETE CASCADE,
    color       TEXT,
    description TEXT    NOT NULL DEFAULT '',
    location    TEXT    NOT NULL DEFAULT '',
    freq        TEXT    NOT NULL DEFAULT '',
    interval    INTEGER NOT NULL DEFAULT 1,
    weekdays    TEXT    NOT NULL DEFAULT '',
    until       TEXT,
    exdates     TEXT    NOT NULL DEFAULT '',
    reminder    INTEGER
);
CREATE TABLE IF NOT EXISTS prefs (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT    NOT NULL DEFAULT '',
    body       TEXT    NOT NULL DEFAULT '',
    pinned     INTEGER NOT NULL DEFAULT 0,
    created_at TEXT    NOT NULL,
    updated_at TEXT    NOT NULL,
    folder_id  INTEGER REFERENCES note_folders(id) ON DELETE SET NULL
);
"""


class CorruptDatabase(Exception):
    """Файл не является целой базой SQLite."""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def default_data_dir() -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path.home() / ".local" / "share"
    return base / APP_DIR_NAME


def default_db_path() -> Path:
    return default_data_dir() / DB_FILE_NAME


def _d(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


class Database:
    """База целиком в памяти; после каждого изменения атомарно сохраняется через хранилище.

    Database(path)            — обычный файл (как раньше, так работают тесты);
    Database(store=...)       — любое хранилище, в том числе зашифрованное;
    Database(store=..., data=...) — уже прочитанные и расшифрованные байты.
    """

    def __init__(self, path: str | Path | None = None, *, store=None, data: bytes | None = None,
                 on_save_error=None):
        if store is None:
            store = PlainStore(Path(path))
        self.store = store
        self.on_save_error = on_save_error
        self.on_commit = None          # вызывается после каждого изменения (автосинхронизация)
        self.conn = sqlite3.connect(":memory:")
        blob = store.load() if data is None else data
        self._open(blob)

    def _open(self, blob: bytes | None) -> None:
        if blob:
            try:
                self.conn.deserialize(blob)
            except sqlite3.DatabaseError as e:
                raise CorruptDatabase(str(e)) from e
        self.conn.execute("PRAGMA foreign_keys = ON")
        try:
            self.conn.executescript(SCHEMA)
            self._migrate()
        except sqlite3.DatabaseError as e:
            raise CorruptDatabase(str(e)) from e
        self._commit()

    # ---- сохранение ----

    def _commit(self) -> None:
        self.conn.commit()
        self.save()
        if self.on_commit is not None:
            self.on_commit()

    def save(self) -> None:
        try:
            self.store.save(self.snapshot())
        except OSError as e:
            if self.on_save_error is None:
                raise
            self.on_save_error(e)

    def snapshot(self) -> bytes:
        """Согласованный снимок всей базы в формате файла SQLite."""
        return bytes(self.conn.serialize())

    def replace_content(self, blob: bytes) -> None:
        """Заменить все данные (восстановление из копии) и сразу сохранить."""
        self.conn.close()
        self.conn = sqlite3.connect(":memory:")
        self._open(blob)

    def set_store(self, store) -> None:
        """Сменить хранилище (включение/выключение пароля) и записать данные в новое."""
        self.store = store
        self.store.save(self.snapshot())

    def quick_check(self) -> bool:
        try:
            return self.conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        except sqlite3.DatabaseError:
            return False

    def _migrate(self) -> None:
        """Добавляет колонки, которых нет в базах, созданных старой версией."""
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(tasks)")}
        if "archived" not in cols:
            self.conn.execute("ALTER TABLE tasks ADD COLUMN archived INTEGER NOT NULL DEFAULT 0")
        if "topic_id" not in cols:
            self.conn.execute("ALTER TABLE tasks ADD COLUMN topic_id INTEGER"
                              " REFERENCES topics(id) ON DELETE SET NULL")
        gcols = {r[1] for r in self.conn.execute("PRAGMA table_info(goals)")}
        if "financial" not in gcols:
            self.conn.execute("ALTER TABLE goals ADD COLUMN financial INTEGER NOT NULL DEFAULT 0")
        if "target_amount" not in gcols:
            self.conn.execute("ALTER TABLE goals ADD COLUMN target_amount REAL NOT NULL DEFAULT 0")
        ncols = {r[1] for r in self.conn.execute("PRAGMA table_info(notes)")}
        if "folder_id" not in ncols:
            self.conn.execute("ALTER TABLE notes ADD COLUMN folder_id INTEGER"
                              " REFERENCES note_folders(id) ON DELETE SET NULL")
        if not self.conn.execute("SELECT 1 FROM calendars LIMIT 1").fetchone():
            self.conn.execute("INSERT INTO calendars(name, color) VALUES ('Личное', ?)",
                              (EVENT_COLORS[0][0],))
        sync.install(self.conn)

    def close(self) -> None:
        self.conn.close()

    # ----- привычки -----

    def add_habit(self, name: str, created_on: date | None = None) -> int:
        created_on = created_on or date.today()
        cur = self.conn.execute(
            "INSERT INTO habits(name, created_on) VALUES (?, ?)", (name, created_on.isoformat())
        )
        self._commit()
        return cur.lastrowid

    def rename_habit(self, habit_id: int, name: str) -> None:
        self.conn.execute("UPDATE habits SET name = ? WHERE id = ?", (name, habit_id))
        self._commit()

    def archive_habit(self, habit_id: int, archived: bool = True) -> None:
        self.conn.execute("UPDATE habits SET archived = ? WHERE id = ?", (int(archived), habit_id))
        self._commit()

    def delete_habit(self, habit_id: int) -> None:
        self.conn.execute("DELETE FROM habits WHERE id = ?", (habit_id,))
        self._commit()

    def list_habits(self, include_archived: bool = False) -> list[Habit]:
        sql = "SELECT id, name, archived, created_on FROM habits"
        if not include_archived:
            sql += " WHERE archived = 0"
        sql += " ORDER BY id"
        return [Habit(r[0], r[1], bool(r[2]), date.fromisoformat(r[3]))
                for r in self.conn.execute(sql)]

    def set_mark(self, habit_id: int, day: date, done: bool) -> None:
        if done:
            self.conn.execute(
                "INSERT OR IGNORE INTO habit_marks(habit_id, day) VALUES (?, ?)",
                (habit_id, day.isoformat()),
            )
        else:
            self.conn.execute(
                "DELETE FROM habit_marks WHERE habit_id = ? AND day = ?",
                (habit_id, day.isoformat()),
            )
        self._commit()

    def marks(self, habit_id: int) -> set[date]:
        rows = self.conn.execute("SELECT day FROM habit_marks WHERE habit_id = ?", (habit_id,))
        return {date.fromisoformat(r[0]) for r in rows}

    def all_marks(self) -> dict[int, set[date]]:
        result: dict[int, set[date]] = {}
        for habit_id, day in self.conn.execute("SELECT habit_id, day FROM habit_marks"):
            result.setdefault(habit_id, set()).add(date.fromisoformat(day))
        return result

    # ----- задачи -----

    def add_task(self, task: Task) -> int:
        cur = self.conn.execute(
            "INSERT INTO tasks(title, description, deadline, priority, done, completed_on, archived,"
            " topic_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            self._task_values(task),
        )
        self._commit()
        return cur.lastrowid

    def update_task(self, task: Task) -> None:
        self.conn.execute(
            "UPDATE tasks SET title = ?, description = ?, deadline = ?, priority = ?,"
            " done = ?, completed_on = ?, archived = ?, topic_id = ? WHERE id = ?",
            (*self._task_values(task), task.id),
        )
        self._commit()

    @staticmethod
    def _task_values(task: Task) -> tuple:
        completed = task.completed_on if task.done else None
        if task.done and completed is None:
            completed = date.today()
        return (
            task.title,
            task.description or "",
            task.deadline.isoformat() if task.deadline else None,
            task.priority,
            int(task.done),
            completed.isoformat() if completed else None,
            int(task.archived),
            task.topic_id,
        )

    def delete_task(self, task_id: int) -> None:
        self.conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        self._commit()

    def set_task_archived(self, task_id: int, archived: bool) -> None:
        self.conn.execute("UPDATE tasks SET archived = ? WHERE id = ?", (int(archived), task_id))
        self._commit()

    def list_tasks(self) -> list[Task]:
        rows = self.conn.execute(
            "SELECT id, title, description, deadline, priority, done, completed_on, archived,"
            " topic_id FROM tasks"
        )
        return [Task(r[0], r[1], r[2], _d(r[3]), r[4], bool(r[5]), _d(r[6]), bool(r[7]), r[8])
                for r in rows]

    def get_task(self, task_id: int) -> Task | None:
        return next((t for t in self.list_tasks() if t.id == task_id), None)

    # ----- темы -----

    def add_topic(self, name: str, color: str) -> int:
        cur = self.conn.execute("INSERT INTO topics(name, color) VALUES (?, ?)", (name, color))
        self._commit()
        return cur.lastrowid

    def update_topic(self, topic: Topic) -> None:
        self.conn.execute("UPDATE topics SET name = ?, color = ? WHERE id = ?",
                          (topic.name, topic.color, topic.id))
        self._commit()

    def delete_topic(self, topic_id: int) -> None:
        """Задачи темы не удаляются — остаются «без темы»."""
        self.conn.execute("UPDATE tasks SET topic_id = NULL WHERE topic_id = ?", (topic_id,))
        self.conn.execute("DELETE FROM topics WHERE id = ?", (topic_id,))
        self._commit()

    def list_topics(self) -> list[Topic]:
        topics = [Topic(*r) for r in self.conn.execute("SELECT id, name, color FROM topics")]
        return sorted(topics, key=lambda t: (t.name.casefold(), t.id))

    # ----- цели -----

    def add_goal(self, goal: Goal) -> int:
        cur = self.conn.execute(
            "INSERT INTO goals(title, description, target_date, done, archived, created_on,"
            " completed_on, financial, target_amount) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (goal.title, goal.description or "",
             goal.target_date.isoformat() if goal.target_date else None,
             int(goal.done), int(goal.archived),
             (goal.created_on or date.today()).isoformat(),
             goal.completed_on.isoformat() if goal.completed_on else None,
             int(goal.financial), float(goal.target_amount or 0)))
        self._commit()
        return cur.lastrowid

    def update_goal(self, goal: Goal) -> None:
        completed = goal.completed_on if goal.done else None
        if goal.done and completed is None:
            completed = date.today()
        self.conn.execute(
            "UPDATE goals SET title = ?, description = ?, target_date = ?, done = ?, archived = ?,"
            " completed_on = ?, financial = ?, target_amount = ? WHERE id = ?",
            (goal.title, goal.description or "",
             goal.target_date.isoformat() if goal.target_date else None,
             int(goal.done), int(goal.archived),
             completed.isoformat() if completed else None,
             int(goal.financial), float(goal.target_amount or 0), goal.id))
        self._commit()

    def delete_goal(self, goal_id: int) -> None:
        self.conn.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
        self._commit()

    def list_goals(self) -> list[Goal]:
        rows = self.conn.execute(
            "SELECT id, title, description, target_date, done, archived, created_on, completed_on,"
            " financial, target_amount FROM goals")
        return [Goal(r[0], r[1], r[2], _d(r[3]), bool(r[4]), bool(r[5]), _d(r[6]), _d(r[7]),
                     bool(r[8]), float(r[9] or 0)) for r in rows]

    # взносы
    def add_contribution(self, goal_id: int, amount: float, day: date | None = None,
                         note: str = "") -> int:
        cur = self.conn.execute(
            "INSERT INTO goal_contributions(goal_id, day, amount, note) VALUES (?, ?, ?, ?)",
            (goal_id, (day or date.today()).isoformat(), float(amount), note))
        self._commit()
        return cur.lastrowid

    def delete_contribution(self, cid: int) -> None:
        self.conn.execute("DELETE FROM goal_contributions WHERE id = ?", (cid,))
        self._commit()

    def contributions(self, goal_id: int) -> list[Contribution]:
        rows = self.conn.execute(
            "SELECT id, goal_id, day, amount, note FROM goal_contributions WHERE goal_id = ?"
            " ORDER BY day DESC, id DESC", (goal_id,))
        return [Contribution(r[0], r[1], date.fromisoformat(r[2]), r[3], r[4]) for r in rows]

    def saved_amounts(self) -> dict[int, float]:
        return {r[0]: r[1] for r in self.conn.execute(
            "SELECT goal_id, SUM(amount) FROM goal_contributions GROUP BY goal_id")}

    def get_goal(self, goal_id: int) -> Goal | None:
        return next((g for g in self.list_goals() if g.id == goal_id), None)

    def add_step(self, goal_id: int, title: str) -> int:
        pos = self.conn.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM goal_steps"
                                " WHERE goal_id = ?", (goal_id,)).fetchone()[0]
        cur = self.conn.execute(
            "INSERT INTO goal_steps(goal_id, title, position) VALUES (?, ?, ?)",
            (goal_id, title, pos))
        self._commit()
        return cur.lastrowid

    def set_step_done(self, step_id: int, done: bool) -> None:
        self.conn.execute("UPDATE goal_steps SET done = ? WHERE id = ?", (int(done), step_id))
        self._commit()

    def rename_step(self, step_id: int, title: str) -> None:
        self.conn.execute("UPDATE goal_steps SET title = ? WHERE id = ?", (title, step_id))
        self._commit()

    def delete_step(self, step_id: int) -> None:
        self.conn.execute("DELETE FROM goal_steps WHERE id = ?", (step_id,))
        self._commit()

    def steps(self, goal_id: int) -> list[GoalStep]:
        rows = self.conn.execute(
            "SELECT id, goal_id, title, done, position FROM goal_steps WHERE goal_id = ?"
            " ORDER BY position, id", (goal_id,))
        return [GoalStep(r[0], r[1], r[2], bool(r[3]), r[4]) for r in rows]

    def all_steps(self) -> dict[int, list[GoalStep]]:
        result: dict[int, list[GoalStep]] = {}
        for r in self.conn.execute("SELECT id, goal_id, title, done, position FROM goal_steps"
                                   " ORDER BY position, id"):
            result.setdefault(r[1], []).append(GoalStep(r[0], r[1], r[2], bool(r[3]), r[4]))
        return result

    # ----- заметки -----

    def add_note(self, title: str = "", body: str = "", folder_id: int | None = None) -> int:
        now = _now()
        cur = self.conn.execute(
            "INSERT INTO notes(title, body, created_at, updated_at, folder_id) VALUES (?, ?, ?, ?, ?)",
            (title, body, now, now, folder_id))
        self._commit()
        return cur.lastrowid

    def update_note(self, note_id: int, title: str, body: str) -> None:
        self.conn.execute("UPDATE notes SET title = ?, body = ?, updated_at = ? WHERE id = ?",
                          (title, body, _now(), note_id))
        self._commit()

    def set_note_pinned(self, note_id: int, pinned: bool) -> None:
        self.conn.execute("UPDATE notes SET pinned = ? WHERE id = ?", (int(pinned), note_id))
        self._commit()

    def move_note(self, note_id: int, folder_id: int | None) -> None:
        self.conn.execute("UPDATE notes SET folder_id = ? WHERE id = ?", (folder_id, note_id))
        self._commit()

    def delete_note(self, note_id: int) -> None:
        self.conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        self._commit()

    _NOTE_COLS = "id, title, body, pinned, created_at, updated_at, folder_id"

    def list_notes(self) -> list[Note]:
        rows = self.conn.execute(f"SELECT {self._NOTE_COLS} FROM notes")
        return [Note(r[0], r[1], r[2], bool(r[3]), r[4], r[5], r[6]) for r in rows]

    def get_note(self, note_id: int) -> Note | None:
        r = self.conn.execute(f"SELECT {self._NOTE_COLS} FROM notes WHERE id = ?",
                              (note_id,)).fetchone()
        return Note(r[0], r[1], r[2], bool(r[3]), r[4], r[5], r[6]) if r else None

    # папки заметок
    def add_folder(self, name: str) -> int:
        cur = self.conn.execute("INSERT INTO note_folders(name) VALUES (?)", (name,))
        self._commit()
        return cur.lastrowid

    def rename_folder(self, folder_id: int, name: str) -> None:
        self.conn.execute("UPDATE note_folders SET name = ? WHERE id = ?", (name, folder_id))
        self._commit()

    def delete_folder(self, folder_id: int) -> None:
        """Заметки из папки не удаляются — переходят в «Без папки»."""
        self.conn.execute("UPDATE notes SET folder_id = NULL WHERE folder_id = ?", (folder_id,))
        self.conn.execute("DELETE FROM note_folders WHERE id = ?", (folder_id,))
        self._commit()

    def list_folders(self) -> list[NoteFolder]:
        folders = [NoteFolder(*r) for r in self.conn.execute("SELECT id, name FROM note_folders")]
        return sorted(folders, key=lambda f: (f.name.casefold(), f.id))  # NOCASE не знает кириллицу

    # ----- календарь -----

    def list_calendars(self) -> list[CalendarInfo]:
        return [CalendarInfo(r[0], r[1], r[2], bool(r[3])) for r in self.conn.execute(
            "SELECT id, name, color, visible FROM calendars ORDER BY id")]

    def add_calendar(self, name: str, color: str) -> int:
        cur = self.conn.execute("INSERT INTO calendars(name, color) VALUES (?, ?)", (name, color))
        self._commit()
        return cur.lastrowid

    def update_calendar(self, c: CalendarInfo) -> None:
        self.conn.execute("UPDATE calendars SET name = ?, color = ?, visible = ? WHERE id = ?",
                          (c.name, c.color, int(c.visible), c.id))
        self._commit()

    def delete_calendar(self, calendar_id: int) -> None:
        """Удаляет календарь вместе с его событиями."""
        self.conn.execute("DELETE FROM events WHERE calendar_id = ?", (calendar_id,))
        self.conn.execute("DELETE FROM calendars WHERE id = ?", (calendar_id,))
        self._commit()

    _EV_COLS = ("id, title, start, end, all_day, calendar_id, color, description, location, freq,"
                " interval, weekdays, until, exdates, reminder")

    @staticmethod
    def _ev_values(e: Event) -> tuple:
        return (e.title, e.start.isoformat(timespec="minutes"), e.end.isoformat(timespec="minutes"),
                int(e.all_day), e.calendar_id, e.color, e.description or "", e.location or "",
                e.freq, max(1, int(e.interval)), ",".join(str(d) for d in sorted(e.weekdays)),
                e.until.isoformat() if e.until else None,
                ",".join(d.isoformat() for d in sorted(set(e.exdates))), e.reminder)

    @staticmethod
    def _ev_row(r) -> Event:
        return Event(
            id=r[0], title=r[1], start=datetime.fromisoformat(r[2]), end=datetime.fromisoformat(r[3]),
            all_day=bool(r[4]), calendar_id=r[5], color=r[6], description=r[7], location=r[8],
            freq=r[9], interval=r[10], weekdays=[int(x) for x in r[11].split(",") if x],
            until=_d(r[12]), exdates=[date.fromisoformat(x) for x in r[13].split(",") if x],
            reminder=r[14])

    def add_event(self, e: Event) -> int:
        cur = self.conn.execute(
            "INSERT INTO events(title, start, end, all_day, calendar_id, color, description,"
            " location, freq, interval, weekdays, until, exdates, reminder)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", self._ev_values(e))
        self._commit()
        return cur.lastrowid

    def update_event(self, e: Event) -> None:
        self.conn.execute(
            "UPDATE events SET title = ?, start = ?, end = ?, all_day = ?, calendar_id = ?,"
            " color = ?, description = ?, location = ?, freq = ?, interval = ?, weekdays = ?,"
            " until = ?, exdates = ?, reminder = ? WHERE id = ?", (*self._ev_values(e), e.id))
        self._commit()

    def delete_event(self, event_id: int) -> None:
        self.conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
        self._commit()

    def list_events(self) -> list[Event]:
        return [self._ev_row(r) for r in self.conn.execute(f"SELECT {self._EV_COLS} FROM events")]

    def get_event(self, event_id: int) -> Event | None:
        r = self.conn.execute(f"SELECT {self._EV_COLS} FROM events WHERE id = ?",
                              (event_id,)).fetchone()
        return self._ev_row(r) if r else None

    # ----- настройки интерфейса (хранятся вместе с данными и попадают в копии) -----

    def get_pref(self, key: str, default: str | None = None) -> str | None:
        r = self.conn.execute("SELECT value FROM prefs WHERE key = ?", (key,)).fetchone()
        return r[0] if r else default

    def set_pref(self, key: str, value: str) -> None:
        self.conn.execute("INSERT INTO prefs(key, value) VALUES (?, ?) ON CONFLICT(key)"
                          " DO UPDATE SET value = excluded.value", (key, value))
        self._commit()

    # ----- синхронизация -----

    def device_id(self) -> str:
        did = self.get_pref("sync_device_id")
        if not did:
            did = sync.new_device_id()
            self.set_pref("sync_device_id", did)
        return did

    def sync_export(self, device_name: str) -> bytes:
        return sync.encode(sync.export_payload(self.conn, self.device_id(), device_name))

    def sync_merge(self, payloads: list[dict]) -> "sync.MergeStats":
        """Слить данные других устройств одним изменением (одна запись на диск)."""
        stats = sync.MergeStats()
        try:
            for p in payloads:
                if p.get("device") != self.device_id():
                    sync.merge(self.conn, p, stats)
        except Exception:
            self.conn.rollback()
            raise
        self._commit()
        return stats
