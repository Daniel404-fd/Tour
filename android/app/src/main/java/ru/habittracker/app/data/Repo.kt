package ru.habittracker.app.data

import android.content.ContentValues
import android.database.Cursor
import android.database.sqlite.SQLiteDatabase
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter

/** Все запросы к базе. Повторяет desktop/tracker/db.py. */
class Repo(val helper: Db) {
    val db: SQLiteDatabase get() = helper.writableDatabase

    /** Вызывается после каждого изменения: перерисовка экранов, напоминания, автосинхронизация. */
    var onChange: (() -> Unit)? = null
    private fun changed() { onChange?.invoke() }

    // ---------------------------------------------------------------- утилиты
    private fun Cursor.str(i: Int): String? = if (isNull(i)) null else getString(i)
    private fun Cursor.lng(i: Int): Long? = if (isNull(i)) null else getLong(i)
    private fun Cursor.bool(i: Int) = getInt(i) != 0
    private fun d(s: String?) = s?.let { LocalDate.parse(it) }
    private fun <T> query(sql: String, args: Array<String>? = null, map: (Cursor) -> T): List<T> =
        db.rawQuery(sql, args).use { c -> buildList { while (c.moveToNext()) add(map(c)) } }

    private fun exec(sql: String, vararg args: Any?) {
        db.execSQL(sql, args.map { a -> when (a) { is Boolean -> if (a) 1 else 0; is LocalDate -> a.toString(); else -> a } }.toTypedArray())
        changed()
    }

    private fun insert(table: String, cv: ContentValues): Long { val id = db.insertOrThrow(table, null, cv); changed(); return id }

    private fun cv(vararg pairs: Pair<String, Any?>) = ContentValues().apply {
        for ((k, v) in pairs) when (v) {
            null -> putNull(k)
            is Boolean -> put(k, if (v) 1 else 0)
            is Int -> put(k, v)
            is Long -> put(k, v)
            is Double -> put(k, v)
            is LocalDate -> put(k, v.toString())
            else -> put(k, v.toString())
        }
    }

    // ---------------------------------------------------------------- привычки
    fun habits(includeArchived: Boolean = false): List<Habit> =
        query("SELECT id, name, archived, created_on FROM habits" + (if (includeArchived) "" else " WHERE archived = 0") + " ORDER BY id") {
            Habit(it.getLong(0), it.getString(1), it.bool(2), LocalDate.parse(it.getString(3)))
        }

    fun addHabit(name: String) = insert("habits", cv("name" to name, "created_on" to LocalDate.now()))
    fun renameHabit(id: Long, name: String) = exec("UPDATE habits SET name = ? WHERE id = ?", name, id)
    fun archiveHabit(id: Long, archived: Boolean) = exec("UPDATE habits SET archived = ? WHERE id = ?", archived, id)
    fun deleteHabit(id: Long) = exec("DELETE FROM habits WHERE id = ?", id)

    fun setMark(habitId: Long, day: LocalDate, done: Boolean) {
        if (done) exec("INSERT OR IGNORE INTO habit_marks(habit_id, day) VALUES (?, ?)", habitId, day)
        else exec("DELETE FROM habit_marks WHERE habit_id = ? AND day = ?", habitId, day)
    }

    fun allMarks(): Map<Long, Set<LocalDate>> {
        val m = mutableMapOf<Long, MutableSet<LocalDate>>()
        query("SELECT habit_id, day FROM habit_marks") { m.getOrPut(it.getLong(0)) { mutableSetOf() } += LocalDate.parse(it.getString(1)) }
        return m
    }

    // ---------------------------------------------------------------- темы и задачи
    fun topics(): List<Topic> = query("SELECT id, name, color FROM topics") { Topic(it.getLong(0), it.getString(1), it.getString(2)) }
        .sortedBy { it.name.lowercase() }
    fun addTopic(name: String, color: String) = insert("topics", cv("name" to name, "color" to color))
    fun updateTopic(t: Topic) = exec("UPDATE topics SET name = ?, color = ? WHERE id = ?", t.name, t.color, t.id)
    fun deleteTopic(id: Long) {
        db.execSQL("UPDATE tasks SET topic_id = NULL WHERE topic_id = ?", arrayOf(id))
        exec("DELETE FROM topics WHERE id = ?", id)
    }

    fun tasks(): List<Task> = query("SELECT id, title, description, deadline, priority, done, completed_on, archived, topic_id FROM tasks") {
        Task(it.getLong(0), it.getString(1), it.getString(2), d(it.str(3)), it.getInt(4), it.bool(5), d(it.str(6)), it.bool(7), it.lng(8))
    }
    fun task(id: Long) = tasks().firstOrNull { it.id == id }

    private fun taskValues(t: Task): ContentValues {
        val completed = if (t.done) (t.completedOn ?: LocalDate.now()) else null
        return cv("title" to t.title, "description" to t.description, "deadline" to t.deadline,
            "priority" to t.priority, "done" to t.done, "completed_on" to completed,
            "archived" to t.archived, "topic_id" to t.topicId)
    }
    fun addTask(t: Task) = insert("tasks", taskValues(t))
    fun updateTask(t: Task) { db.update("tasks", taskValues(t), "id = ?", arrayOf(t.id.toString())); changed() }
    fun deleteTask(id: Long) = exec("DELETE FROM tasks WHERE id = ?", id)

    // ---------------------------------------------------------------- цели
    fun goals(): List<Goal> = query("SELECT id, title, description, target_date, done, archived, created_on, completed_on, financial, target_amount FROM goals") {
        Goal(it.getLong(0), it.getString(1), it.getString(2), d(it.str(3)), it.bool(4), it.bool(5), d(it.str(6)), d(it.str(7)), it.bool(8), it.getDouble(9))
    }
    fun goal(id: Long) = goals().firstOrNull { it.id == id }

    private fun goalValues(g: Goal): ContentValues {
        val completed = if (g.done) (g.completedOn ?: LocalDate.now()) else null
        return cv("title" to g.title, "description" to g.description, "target_date" to g.targetDate,
            "done" to g.done, "archived" to g.archived, "created_on" to (g.createdOn ?: LocalDate.now()),
            "completed_on" to completed, "financial" to g.financial, "target_amount" to g.targetAmount)
    }
    fun addGoal(g: Goal) = insert("goals", goalValues(g))
    fun updateGoal(g: Goal) { db.update("goals", goalValues(g), "id = ?", arrayOf(g.id.toString())); changed() }
    fun deleteGoal(id: Long) = exec("DELETE FROM goals WHERE id = ?", id)

    fun allSteps(): Map<Long, List<GoalStep>> =
        query("SELECT id, goal_id, title, done, position FROM goal_steps ORDER BY position, id") {
            GoalStep(it.getLong(0), it.getLong(1), it.getString(2), it.bool(3), it.getInt(4))
        }.groupBy { it.goalId }
    fun addStep(goalId: Long, title: String): Long {
        val pos = query("SELECT COALESCE(MAX(position), -1) + 1 FROM goal_steps WHERE goal_id = ?", arrayOf(goalId.toString())) { it.getInt(0) }.first()
        return insert("goal_steps", cv("goal_id" to goalId, "title" to title, "position" to pos))
    }
    fun setStepDone(id: Long, done: Boolean) = exec("UPDATE goal_steps SET done = ? WHERE id = ?", done, id)
    fun renameStep(id: Long, title: String) = exec("UPDATE goal_steps SET title = ? WHERE id = ?", title, id)
    fun deleteStep(id: Long) = exec("DELETE FROM goal_steps WHERE id = ?", id)

    fun addContribution(goalId: Long, amount: Double, day: LocalDate = LocalDate.now(), note: String = "") =
        insert("goal_contributions", cv("goal_id" to goalId, "day" to day, "amount" to amount, "note" to note))
    fun deleteContribution(id: Long) = exec("DELETE FROM goal_contributions WHERE id = ?", id)
    fun contributions(goalId: Long): List<Contribution> =
        query("SELECT id, goal_id, day, amount, note FROM goal_contributions WHERE goal_id = ? ORDER BY day DESC, id DESC", arrayOf(goalId.toString())) {
            Contribution(it.getLong(0), it.getLong(1), LocalDate.parse(it.getString(2)), it.getDouble(3), it.getString(4))
        }
    fun savedAmounts(): Map<Long, Double> =
        query("SELECT goal_id, SUM(amount) FROM goal_contributions GROUP BY goal_id") { it.getLong(0) to it.getDouble(1) }.toMap()

    // ---------------------------------------------------------------- заметки
    private val nowFmt = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss")
    private fun nowIso() = LocalDateTime.now().format(nowFmt)

    fun notes(): List<Note> = query("SELECT id, title, body, pinned, created_at, updated_at, folder_id FROM notes") {
        Note(it.getLong(0), it.getString(1), it.getString(2), it.bool(3), it.getString(4), it.getString(5), it.lng(6))
    }
    fun note(id: Long) = notes().firstOrNull { it.id == id }
    fun addNote(folderId: Long? = null): Long { val n = nowIso(); return insert("notes", cv("title" to "", "body" to "", "created_at" to n, "updated_at" to n, "folder_id" to folderId)) }
    fun updateNote(id: Long, title: String, body: String) = exec("UPDATE notes SET title = ?, body = ?, updated_at = ? WHERE id = ?", title, body, nowIso(), id)
    fun setNotePinned(id: Long, pinned: Boolean) = exec("UPDATE notes SET pinned = ? WHERE id = ?", pinned, id)
    fun moveNote(id: Long, folderId: Long?) = exec("UPDATE notes SET folder_id = ? WHERE id = ?", folderId, id)
    fun deleteNote(id: Long) = exec("DELETE FROM notes WHERE id = ?", id)

    fun folders(): List<NoteFolder> = query("SELECT id, name FROM note_folders") { NoteFolder(it.getLong(0), it.getString(1)) }.sortedBy { it.name.lowercase() }
    fun addFolder(name: String) = insert("note_folders", cv("name" to name))
    fun renameFolder(id: Long, name: String) = exec("UPDATE note_folders SET name = ? WHERE id = ?", name, id)
    fun deleteFolder(id: Long) {
        db.execSQL("UPDATE notes SET folder_id = NULL WHERE folder_id = ?", arrayOf(id))
        exec("DELETE FROM note_folders WHERE id = ?", id)
    }

    // ---------------------------------------------------------------- календарь
    fun calendars(): List<CalendarInfo> = query("SELECT id, name, color, visible FROM calendars ORDER BY id") {
        CalendarInfo(it.getLong(0), it.getString(1), it.getString(2), it.bool(3))
    }
    fun addCalendar(name: String, color: String) = insert("calendars", cv("name" to name, "color" to color))
    fun updateCalendar(c: CalendarInfo) = exec("UPDATE calendars SET name = ?, color = ?, visible = ? WHERE id = ?", c.name, c.color, c.visible, c.id)
    fun deleteCalendar(id: Long) {
        db.execSQL("DELETE FROM events WHERE calendar_id = ?", arrayOf(id))
        exec("DELETE FROM calendars WHERE id = ?", id)
    }

    private val minuteFmt = DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm")
    private fun evValues(e: Event) = cv("title" to e.title, "start" to e.start.format(minuteFmt), "end" to e.end.format(minuteFmt),
        "all_day" to e.allDay, "calendar_id" to e.calendarId, "color" to e.color, "description" to e.description,
        "location" to e.location, "freq" to e.freq, "interval" to maxOf(1, e.interval),
        "weekdays" to e.weekdays.sorted().joinToString(","), "until" to e.until,
        "exdates" to e.exdates.toSortedSet().joinToString(","), "reminder" to e.reminder)

    fun events(): List<Event> = query("SELECT id, title, start, \"end\", all_day, calendar_id, color, description, location, freq, interval, weekdays, until, exdates, reminder FROM events") {
        Event(it.getLong(0), it.getString(1), LocalDateTime.parse(it.getString(2)), LocalDateTime.parse(it.getString(3)),
            it.bool(4), it.lng(5), it.str(6), it.getString(7), it.getString(8), it.getString(9), it.getInt(10),
            it.getString(11).split(",").filter { s -> s.isNotBlank() }.map { s -> s.trim().toInt() }, d(it.str(12)),
            it.getString(13).split(",").filter { s -> s.isNotBlank() }.map { s -> LocalDate.parse(s.trim()) },
            if (it.isNull(14)) null else it.getInt(14))
    }
    fun event(id: Long) = events().firstOrNull { it.id == id }
    fun addEvent(e: Event) = insert("events", evValues(e))
    fun updateEvent(e: Event) { db.update("events", evValues(e), "id = ?", arrayOf(e.id.toString())); changed() }
    fun deleteEvent(id: Long) = exec("DELETE FROM events WHERE id = ?", id)

    // ---------------------------------------------------------------- настройки
    fun pref(key: String, default: String? = null): String? =
        query("SELECT value FROM prefs WHERE key = ?", arrayOf(key)) { it.getString(0) }.firstOrNull() ?: default
    fun setPref(key: String, value: String) { db.execSQL("INSERT OR REPLACE INTO prefs(key, value) VALUES (?, ?)", arrayOf(key, value)) }

    fun deviceId(): String = pref("sync_device_id") ?: java.util.UUID.randomUUID().toString().replace("-", "").take(12).also { setPref("sync_device_id", it) }
}
