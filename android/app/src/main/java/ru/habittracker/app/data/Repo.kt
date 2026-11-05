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

    /** Обычные задачи. Карточки досок — tasks(includeBoards = true) или boardTasks(). */
    fun tasks(includeBoards: Boolean = false): List<Task> = query("SELECT id, title, description, deadline, priority, done, completed_on, archived, topic_id, board_id, column_id, position FROM tasks" +
        if (includeBoards) "" else " WHERE board_id IS NULL") {
        Task(it.getLong(0), it.getString(1), it.getString(2), d(it.str(3)), it.getInt(4), it.bool(5), d(it.str(6)), it.bool(7), it.lng(8),
            it.lng(9), it.lng(10), if (it.isNull(11)) 0.0 else it.getDouble(11))
    }
    fun task(id: Long) = tasks(includeBoards = true).firstOrNull { it.id == id }
    fun boardTasks(boardId: Long) = tasks(includeBoards = true).filter { it.boardId == boardId }

    private fun taskValues(t: Task): ContentValues {
        val completed = if (t.done) (t.completedOn ?: LocalDate.now()) else null
        return cv("title" to t.title, "description" to t.description, "deadline" to t.deadline,
            "priority" to t.priority, "done" to t.done, "completed_on" to completed,
            "archived" to t.archived, "topic_id" to t.topicId, "board_id" to t.boardId, "column_id" to t.columnId,
            "position" to if (t.boardId != null) t.position else null)
    }
    fun addTask(t: Task) = insert("tasks", taskValues(t))
    fun updateTask(t: Task) { db.update("tasks", taskValues(t), "id = ?", arrayOf(t.id.toString())); changed() }
    fun deleteTask(id: Long) = exec("DELETE FROM tasks WHERE id = ?", id)

    // ---------------------------------------------------------------- доски (канбан), как на ПК
    fun boards(includeArchived: Boolean = false): List<Board> =
        query("SELECT id, name, color, position, archived FROM boards" + (if (includeArchived) "" else " WHERE archived = 0") + " ORDER BY position, id") {
            Board(it.getLong(0), it.getString(1), it.getString(2), it.getInt(3), it.bool(4))
        }
    fun addBoard(name: String, color: String): Long {
        val pos = query("SELECT COALESCE(MAX(position), -1) + 1 FROM boards") { it.getInt(0) }.first()
        db.beginTransaction()
        try {
            val id = db.insertOrThrow("boards", null, cv("name" to name, "color" to color, "position" to pos))
            listOf("К выполнению" to false, "В работе" to false, "Готово" to true).forEachIndexed { i, (n, done) ->
                db.insertOrThrow("board_columns", null, cv("board_id" to id, "name" to n, "position" to i, "is_done" to done))
            }
            db.setTransactionSuccessful()
            return id
        } finally { db.endTransaction(); changed() }
    }
    fun updateBoard(b: Board) = exec("UPDATE boards SET name = ?, color = ?, position = ?, archived = ? WHERE id = ?", b.name, b.color, b.position, b.archived, b.id)
    fun deleteBoard(id: Long) {
        db.beginTransaction()
        try {
            db.execSQL("DELETE FROM task_subtasks WHERE task_id IN (SELECT id FROM tasks WHERE board_id = ?)", arrayOf(id))
            db.execSQL("DELETE FROM tasks WHERE board_id = ?", arrayOf(id))
            db.execSQL("DELETE FROM notes WHERE board_id = ?", arrayOf(id))
            db.execSQL("DELETE FROM board_columns WHERE board_id = ?", arrayOf(id))
            db.execSQL("DELETE FROM boards WHERE id = ?", arrayOf(id))
            db.setTransactionSuccessful()
        } finally { db.endTransaction(); changed() }
    }
    fun columns(boardId: Long): List<BoardColumn> =
        query("SELECT id, board_id, name, position, is_done FROM board_columns WHERE board_id = ? ORDER BY position, id", arrayOf(boardId.toString())) {
            BoardColumn(it.getLong(0), it.getLong(1), it.getString(2), it.getInt(3), it.bool(4))
        }
    fun addColumn(boardId: Long, name: String): Long {
        val pos = query("SELECT COALESCE(MAX(position), -1) + 1 FROM board_columns WHERE board_id = ?", arrayOf(boardId.toString())) { it.getInt(0) }.first()
        return insert("board_columns", cv("board_id" to boardId, "name" to name, "position" to pos))
    }
    fun renameColumn(id: Long, name: String) = exec("UPDATE board_columns SET name = ? WHERE id = ?", name, id)
    fun cardsIn(columnId: Long) = tasks(includeBoards = true).filter { it.columnId == columnId }.sortedWith(compareBy({ it.position }, { it.id }))
    private fun columnDone(columnId: Long) = query("SELECT is_done FROM board_columns WHERE id = ?", arrayOf(columnId.toString())) { it.bool(0) }.firstOrNull() ?: false

    fun addCard(boardId: Long, columnId: Long, title: String, deadline: LocalDate? = null, priority: Int = PRIORITY_MEDIUM, topicId: Long? = null): Long {
        val pos = (cardsIn(columnId).maxOfOrNull { it.position } ?: 0.0) + 1.0
        return addTask(Task(title = title, deadline = deadline, priority = priority, topicId = topicId, boardId = boardId,
            columnId = columnId, position = pos, done = columnDone(columnId)))
    }

    /** Переложить карточку в колонку на место index (0 — сверху); «Готово» отмечает выполненной. */
    fun moveCard(taskId: Long, columnId: Long, index: Int) {
        val cards = cardsIn(columnId).filter { it.id != taskId }
        val i = index.coerceIn(0, cards.size)
        val before = if (i > 0) cards[i - 1].position else null
        val after = if (i < cards.size) cards[i].position else null
        var pos = when {
            before == null && after == null -> 1.0
            before == null -> after!! - 1.0
            after == null -> before + 1.0
            else -> (before + after) / 2
        }
        if (before != null && after != null && after - before < 1e-6) {
            cards.forEachIndexed { k, c -> db.execSQL("UPDATE tasks SET position = ? WHERE id = ?", arrayOf<Any>((k + 1).toDouble(), c.id)) }
            pos = i + 0.5
        }
        val t = task(taskId) ?: return
        val done = columnDone(columnId)
        updateTask(t.copy(columnId = columnId, position = pos, done = done, completedOn = if (done) t.completedOn ?: LocalDate.now() else null))
    }

    /** Выполнено: карточка доски переезжает в «Готово» (или обратно в первую колонку). */
    fun completeTask(taskId: Long, done: Boolean = true) {
        val t = task(taskId) ?: return
        if (t.boardId != null) {
            val cols = columns(t.boardId)
            val target = if (done) cols.firstOrNull { it.isDone } else cols.firstOrNull { !it.isDone }
            if (target != null) { moveCard(taskId, target.id, if (done) 0 else cardsIn(target.id).size); return }
        }
        updateTask(t.copy(done = done, completedOn = null))
    }

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

    // ---------------------------------------------------------------- подзадачи
    fun allSubtasks(): Map<Long, List<Subtask>> =
        query("SELECT id, task_id, title, done, position FROM task_subtasks ORDER BY position, id") {
            Subtask(it.getLong(0), it.getLong(1), it.getString(2), it.bool(3), it.getInt(4))
        }.groupBy { it.taskId }
    fun subtasks(taskId: Long): List<Subtask> = allSubtasks()[taskId] ?: emptyList()
    fun addSubtask(taskId: Long, title: String): Long {
        val pos = query("SELECT COALESCE(MAX(position), -1) + 1 FROM task_subtasks WHERE task_id = ?", arrayOf(taskId.toString())) { it.getInt(0) }.first()
        return insert("task_subtasks", cv("task_id" to taskId, "title" to title, "position" to pos))
    }
    fun setSubtaskDone(id: Long, done: Boolean) = exec("UPDATE task_subtasks SET done = ? WHERE id = ?", done, id)
    fun deleteSubtask(id: Long) = exec("DELETE FROM task_subtasks WHERE id = ?", id)

    /** Привести подзадачи к списку из редактора (новые, удалённые, переименованные, порядок) — одной транзакцией. */
    fun applySubtasks(taskId: Long, drafts: List<SubtaskDraft>) {
        val existing = subtasks(taskId).associateBy { it.id }
        val keep = drafts.filter { it.id != 0L }.map { it.id }.toSet()
        db.beginTransaction()
        try {
            for (id in existing.keys) if (id !in keep) db.execSQL("DELETE FROM task_subtasks WHERE id = ?", arrayOf(id))
            drafts.forEachIndexed { pos, d ->
                val cur = existing[d.id]
                if (cur != null) {
                    if (cur.title != d.title || cur.done != d.done || cur.position != pos)
                        db.execSQL("UPDATE task_subtasks SET title = ?, done = ?, position = ? WHERE id = ?",
                            arrayOf<Any>(d.title, if (d.done) 1 else 0, pos, d.id))
                } else db.insertOrThrow("task_subtasks", null, cv("task_id" to taskId, "title" to d.title, "done" to d.done, "position" to pos))
            }
            db.setTransactionSuccessful()
        } finally { db.endTransaction() }
        changed()
    }

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

    private fun allNotes(): List<Note> = query("SELECT id, title, body, pinned, created_at, updated_at, folder_id, board_id FROM notes") {
        Note(it.getLong(0), it.getString(1), it.getString(2), it.bool(3), it.getString(4), it.getString(5), it.lng(6), it.lng(7))
    }
    /** Обычные заметки; заметки досок — boardNotes(). */
    fun notes(): List<Note> = allNotes().filter { it.boardId == null }
    fun boardNotes(boardId: Long): List<Note> = allNotes().filter { it.boardId == boardId }
    fun note(id: Long) = allNotes().firstOrNull { it.id == id }
    fun addNote(folderId: Long? = null, boardId: Long? = null): Long { val n = nowIso(); return insert("notes", cv("title" to "", "body" to "", "created_at" to n, "updated_at" to n, "folder_id" to folderId, "board_id" to boardId)) }
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
