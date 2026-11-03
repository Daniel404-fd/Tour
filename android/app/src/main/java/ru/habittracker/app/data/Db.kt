package ru.habittracker.app.data

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import android.database.sqlite.SQLiteOpenHelper

/**
 * Та же схема, что у программы для ПК (desktop/tracker/db.py), плюс колонки синхронизации
 * (desktop/tracker/sync.py). Любое изменение схемы делается одинаково в обоих местах.
 */
class Db(context: Context, name: String? = "tracker.sqlite3") :
    SQLiteOpenHelper(context, name, null, 1) {

    override fun onConfigure(db: SQLiteDatabase) {
        db.setForeignKeyConstraintsEnabled(true)
    }

    override fun onCreate(db: SQLiteDatabase) {
        SCHEMA.split(";").map { it.trim() }.filter { it.isNotEmpty() }.forEach { db.execSQL(it) }
    }

    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {}

    override fun onOpen(db: SQLiteDatabase) {
        super.onOpen(db)
        if (!db.isReadOnly) {
            db.beginTransaction()
            try {
                val c = db.rawQuery("SELECT 1 FROM calendars LIMIT 1", null)
                val has = c.moveToFirst(); c.close()
                if (!has) db.execSQL("INSERT INTO calendars(name, color) VALUES ('Личное', '#0B6E69')")
                SyncSchema.install(db)
                db.setTransactionSuccessful()
            } finally {
                db.endTransaction()
            }
        }
    }

    companion object {
        val SCHEMA = """
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
    "end"       TEXT    NOT NULL,
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
)
"""
    }
}

/** Колонки sync_uid / sync_ts, надгробия и триггеры — один в один как desktop/tracker/sync.py. */
object SyncSchema {
    const val DEFAULT_CALENDAR_UID = "calendar-default"
    const val NOW_SQL = "strftime('%Y-%m-%dT%H:%M:%fZ','now')"
    const val UID_SQL = "lower(hex(randomblob(16)))"

    /** Таблица → (поля данных, ссылки поле→таблица). Порядок: сначала «родители». */
    val TABLES: LinkedHashMap<String, Pair<List<String>, Map<String, String>>> = linkedMapOf(
        "topics" to (listOf("name", "color") to emptyMap()),
        "habits" to (listOf("name", "archived", "created_on") to emptyMap()),
        "habit_marks" to (listOf("habit_id", "day") to mapOf("habit_id" to "habits")),
        "note_folders" to (listOf("name") to emptyMap()),
        "calendars" to (listOf("name", "color", "visible") to emptyMap()),
        "goals" to (listOf("title", "description", "target_date", "done", "archived", "created_on",
            "completed_on", "financial", "target_amount") to emptyMap()),
        "goal_steps" to (listOf("goal_id", "title", "done", "position") to mapOf("goal_id" to "goals")),
        "goal_contributions" to (listOf("goal_id", "day", "amount", "note") to mapOf("goal_id" to "goals")),
        "tasks" to (listOf("title", "description", "deadline", "priority", "done", "completed_on",
            "archived", "topic_id") to mapOf("topic_id" to "topics")),
        "notes" to (listOf("title", "body", "pinned", "created_at", "updated_at", "folder_id") to
            mapOf("folder_id" to "note_folders")),
        "events" to (listOf("title", "start", "end", "all_day", "calendar_id", "color", "description",
            "location", "freq", "interval", "weekdays", "until", "exdates", "reminder") to
            mapOf("calendar_id" to "calendars")),
    )
    val REQUIRED_REFS = setOf("habit_marks.habit_id", "goal_steps.goal_id",
        "goal_contributions.goal_id", "events.calendar_id")

    fun install(db: SQLiteDatabase) {
        db.execSQL("CREATE TABLE IF NOT EXISTS sync_tombstones (uid TEXT PRIMARY KEY, tbl TEXT NOT NULL, ts TEXT NOT NULL)")
        for (table in TABLES.keys) {
            val cols = mutableSetOf<String>()
            db.rawQuery("PRAGMA table_info($table)", null).use { c -> while (c.moveToNext()) cols += c.getString(1) }
            if ("sync_uid" !in cols) db.execSQL("ALTER TABLE $table ADD COLUMN sync_uid TEXT")
            if ("sync_ts" !in cols) db.execSQL("ALTER TABLE $table ADD COLUMN sync_ts TEXT")
        }
        val hasDefault = db.rawQuery("SELECT 1 FROM calendars WHERE sync_uid = ?", arrayOf(DEFAULT_CALENDAR_UID))
            .use { it.moveToFirst() }
        if (!hasDefault) {
            db.rawQuery("SELECT id FROM calendars WHERE sync_uid IS NULL ORDER BY id LIMIT 1", null).use { c ->
                if (c.moveToFirst()) db.execSQL("UPDATE calendars SET sync_uid = ? WHERE id = ?",
                    arrayOf<Any>(DEFAULT_CALENDAR_UID, c.getLong(0)))
            }
        }
        for (table in TABLES.keys) {
            if (table == "habit_marks") continue
            db.execSQL("UPDATE $table SET sync_uid = $UID_SQL WHERE sync_uid IS NULL")
        }
        db.execSQL("UPDATE habit_marks SET sync_uid = (SELECT h.sync_uid FROM habits h WHERE h.id = " +
            "habit_marks.habit_id) || ':' || day WHERE sync_uid IS NULL")
        for (table in TABLES.keys) {
            db.execSQL("UPDATE $table SET sync_ts = $NOW_SQL WHERE sync_ts IS NULL")
            db.execSQL("CREATE UNIQUE INDEX IF NOT EXISTS ${table}_sync_uid ON $table(sync_uid)")
            triggers(db, table)
        }
    }

    private fun triggers(db: SQLiteDatabase, table: String) {
        val newUid = if (table == "habit_marks")
            "COALESCE(NEW.sync_uid, (SELECT h.sync_uid FROM habits h WHERE h.id = NEW.habit_id) || ':' || NEW.day)"
        else "COALESCE(NEW.sync_uid, $UID_SQL)"
        db.execSQL("""CREATE TRIGGER IF NOT EXISTS ${table}_sync_ins AFTER INSERT ON $table BEGIN
            UPDATE $table SET sync_uid = $newUid, sync_ts = COALESCE(NEW.sync_ts, $NOW_SQL) WHERE rowid = NEW.rowid;
            DELETE FROM sync_tombstones WHERE uid = (SELECT sync_uid FROM $table WHERE rowid = NEW.rowid);
            END""")
        db.execSQL("""CREATE TRIGGER IF NOT EXISTS ${table}_sync_upd AFTER UPDATE ON $table
            WHEN NEW.sync_ts IS OLD.sync_ts BEGIN
            UPDATE $table SET sync_ts = $NOW_SQL WHERE rowid = NEW.rowid;
            END""")
        db.execSQL("""CREATE TRIGGER IF NOT EXISTS ${table}_sync_del AFTER DELETE ON $table
            WHEN OLD.sync_uid IS NOT NULL BEGIN
            INSERT OR REPLACE INTO sync_tombstones(uid, tbl, ts) VALUES (OLD.sync_uid, '$table', $NOW_SQL);
            END""")
    }
}
