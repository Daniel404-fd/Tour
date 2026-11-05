package ru.habittracker.app.data

import java.time.LocalDate
import java.time.LocalDateTime
import java.time.temporal.ChronoUnit
import kotlin.math.abs
import kotlin.math.roundToLong

const val PRIORITY_HIGH = 0
const val PRIORITY_MEDIUM = 1
const val PRIORITY_LOW = 2
val PRIORITY_NAMES = mapOf(PRIORITY_HIGH to "Высокий", PRIORITY_MEDIUM to "Средний", PRIORITY_LOW to "Низкий")
const val EDITABLE_DAYS = 7

data class Habit(val id: Long, val name: String, val archived: Boolean, val createdOn: LocalDate)

data class Topic(val id: Long, val name: String, val color: String)

data class Task(
    val id: Long = 0, val title: String, val description: String = "", val deadline: LocalDate? = null,
    val priority: Int = PRIORITY_MEDIUM, val done: Boolean = false, val completedOn: LocalDate? = null,
    val archived: Boolean = false, val topicId: Long? = null,
    /** Карточка доски (канбан): в обычном списке задач её нет. */
    val boardId: Long? = null, val columnId: Long? = null, val position: Double = 0.0,
)

data class Board(val id: Long, val name: String, val color: String, val position: Int = 0, val archived: Boolean = false)
data class BoardColumn(val id: Long, val boardId: Long, val name: String, val position: Int, val isDone: Boolean)

data class Goal(
    val id: Long = 0, val title: String, val description: String = "", val targetDate: LocalDate? = null,
    val done: Boolean = false, val archived: Boolean = false, val createdOn: LocalDate? = null,
    val completedOn: LocalDate? = null, val financial: Boolean = false, val targetAmount: Double = 0.0,
)

data class Subtask(val id: Long, val taskId: Long, val title: String, val done: Boolean, val position: Int)

/** Строка редактора подзадач: id = 0 — новая, ещё не сохранённая. */
data class SubtaskDraft(val id: Long, val title: String, val done: Boolean)

data class GoalStep(val id: Long, val goalId: Long, val title: String, val done: Boolean, val position: Int)

data class Contribution(val id: Long, val goalId: Long, val day: LocalDate, val amount: Double, val note: String)

data class NoteFolder(val id: Long, val name: String)

data class Note(
    val id: Long, val title: String, val body: String, val pinned: Boolean, val createdAt: String,
    val updatedAt: String, val folderId: Long?, val boardId: Long? = null,
) {
    val displayTitle: String
        get() = title.trim().ifEmpty { body.lines().map { it.trim() }.firstOrNull { it.isNotEmpty() }?.take(60) ?: "Без названия" }
}

data class CalendarInfo(val id: Long, val name: String, val color: String, val visible: Boolean)

const val FREQ_NONE = ""
const val FREQ_DAILY = "daily"
const val FREQ_WEEKLY = "weekly"
const val FREQ_MONTHLY = "monthly"
const val FREQ_YEARLY = "yearly"
val FREQ_NAMES = linkedMapOf(FREQ_NONE to "Не повторять", FREQ_DAILY to "Каждый день",
    FREQ_WEEKLY to "Каждую неделю", FREQ_MONTHLY to "Каждый месяц", FREQ_YEARLY to "Каждый год")

data class Event(
    val id: Long = 0, val title: String, val start: LocalDateTime, val end: LocalDateTime,
    val allDay: Boolean = false, val calendarId: Long? = null, val color: String? = null,
    val description: String = "", val location: String = "", val freq: String = FREQ_NONE,
    val interval: Int = 1, val weekdays: List<Int> = emptyList(), val until: LocalDate? = null,
    val exdates: List<LocalDate> = emptyList(), val reminder: Int? = null,
) {
    val recurring get() = freq != FREQ_NONE
}

/** Цвета событий — как на ПК (белый текст на каждом читается, контраст ≥ 4.5). */
val EVENT_COLORS = listOf("#0B6E69" to "Бирюзовый", "#3F51B5" to "Черничный", "#7B1FA2" to "Виноградный",
    "#C2185B" to "Фламинго", "#C62828" to "Томатный", "#B4530A" to "Мандариновый",
    "#2E7D32" to "Базилик", "#455A64" to "Графит")
val TOPIC_COLORS = listOf("#008000", "#000080", "#800000", "#C05800", "#800080", "#008080", "#808000", "#505050")
val REMINDER_CHOICES = listOf<Pair<Int?, String>>(null to "Без напоминания", 0 to "В момент начала",
    5 to "За 5 минут", 10 to "За 10 минут", 15 to "За 15 минут", 30 to "За 30 минут", 60 to "За 1 час",
    120 to "За 2 часа", 1440 to "За 1 день")

// ---------------------------------------------------------------- логика (как desktop/tracker/logic.py)

object Logic {
    fun lastDays(today: LocalDate, n: Int): List<LocalDate> = (n - 1 downTo 0).map { today.minusDays(it.toLong()) }

    fun canMark(day: LocalDate, today: LocalDate) = !day.isAfter(today) && !day.isBefore(today.minusDays(EDITABLE_DAYS - 1L))

    fun currentStreak(marks: Set<LocalDate>, today: LocalDate): Int {
        var day = if (today in marks) today else today.minusDays(1)
        var n = 0
        while (day in marks) { n++; day = day.minusDays(1) }
        return n
    }

    fun bestStreak(marks: Set<LocalDate>): Int {
        var best = 0; var run = 0; var prev: LocalDate? = null
        for (d in marks.sorted()) {
            run = if (prev != null && prev.plusDays(1) == d) run + 1 else 1
            best = maxOf(best, run); prev = d
        }
        return best
    }

    fun completionByDay(habits: List<Habit>, marks: Map<Long, Set<LocalDate>>, today: LocalDate, days: Int): List<Pair<LocalDate, Double>> {
        val active = habits.filter { !it.archived }
        return lastDays(today, days).map { day ->
            val existing = active.filter { !it.createdOn.isAfter(day) }
            if (existing.isEmpty()) day to 0.0
            else day to 100.0 * existing.count { day in (marks[it.id] ?: emptySet()) } / existing.size
        }
    }

    fun isOverdue(t: Task, today: LocalDate) = !t.done && !t.archived && t.deadline != null && t.deadline.isBefore(today)
    fun isDueToday(t: Task, today: LocalDate) = !t.done && !t.archived && t.deadline == today

    fun sortTasks(tasks: List<Task>) = tasks.sortedWith(compareBy<Task>({ it.deadline == null }, { it.deadline ?: LocalDate.MAX }, { it.priority }, { it.id }))

    fun upcoming(tasks: List<Task>, today: LocalDate, days: Int): List<Task> {
        val limit = today.plusDays(days.toLong())
        return sortTasks(tasks.filter { !it.done && !it.archived && it.deadline != null && !it.deadline.isAfter(limit) })
    }

    fun plural(n: Long, one: String, few: String, many: String): String {
        val a = abs(n)
        return when {
            a % 10 == 1L && a % 100 != 11L -> one
            a % 10 in 2..4 && a % 100 !in 12..14 -> few
            else -> many
        }
    }
    fun plural(n: Int, one: String, few: String, many: String) = plural(n.toLong(), one, few, many)

    fun dueText(deadline: LocalDate, today: LocalDate): String {
        val delta = ChronoUnit.DAYS.between(today, deadline)
        return when {
            delta == 0L -> "сегодня"
            delta == 1L -> "завтра"
            delta > 1 -> "через $delta ${plural(delta, "день", "дня", "дней")}"
            else -> "просрочено на ${-delta} ${plural(-delta, "день", "дня", "дней")}"
        }
    }

    fun moneyProgress(g: Goal, saved: Double): Double =
        if (!g.financial || g.targetAmount <= 0) 0.0 else (saved / g.targetAmount).coerceIn(0.0, 1.0)

    /** Как на ПК: обычная — по шагам; финансовая — по деньгам, а с шагами — поровну. */
    fun goalProgress(g: Goal, steps: List<GoalStep>, saved: Double): Double {
        if (g.done) return 1.0
        val stepsPart = if (steps.isEmpty()) null else steps.count { it.done }.toDouble() / steps.size
        if (g.financial && g.targetAmount > 0) {
            val m = moneyProgress(g, saved)
            return if (stepsPart == null) m else (m + stepsPart) / 2
        }
        return stepsPart ?: 0.0
    }

    fun formatMoney(amount: Double): String {
        val neg = amount < 0
        val cents = (abs(amount) * 100).roundToLong()
        val whole = cents / 100
        val frac = cents % 100
        val s = whole.toString().reversed().chunked(3).joinToString(" ").reversed()
        return (if (neg) "−" else "") + s + (if (frac != 0L) ",%02d".format(frac) else "") + " ₽"
    }

    fun parseMoney(text: String): Double? {
        var t = text.replace(" ", "").replace(" ", "").replace("₽", "").replace(",", ".").trim()
        if (t.startsWith("−")) t = "-" + t.substring(1)
        return t.toDoubleOrNull()?.let { Math.round(it * 100) / 100.0 }
    }

    val MONTHS_GEN = listOf("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
        "сентября", "октября", "ноября", "декабря")
    val MONTHS = listOf("Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь",
        "Октябрь", "Ноябрь", "Декабрь")
    val WEEKDAYS_FULL = listOf("Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье")
    val WD = listOf("пн", "вт", "ср", "чт", "пт", "сб", "вс")

    fun humanDate(d: LocalDate, today: LocalDate = LocalDate.now()): String {
        val s = "${d.dayOfMonth} ${MONTHS_GEN[d.monthValue - 1]}"
        return if (d.year == today.year) s else "$s ${d.year}"
    }
}

// ---------------------------------------------------------------- быстрое добавление (как logic.parse_quick_task)

data class QuickTask(val title: String, val deadline: LocalDate?, val topicId: Long?, val priority: Int, val hints: List<String>)

object Quick {
    private val WEEKDAYS = mapOf("пн" to 0, "понедельник" to 0, "вт" to 1, "вторник" to 1, "ср" to 2, "среда" to 2, "среду" to 2,
        "чт" to 3, "четверг" to 3, "пт" to 4, "пятница" to 4, "пятницу" to 4, "сб" to 5, "суббота" to 5, "субботу" to 5,
        "вс" to 6, "воскресенье" to 6)
    private val REL = mapOf("сегодня" to 0L, "завтра" to 1L, "послезавтра" to 2L)
    private val DATE = Regex("""(\d{1,2})\.(\d{1,2})(?:\.(\d{2}|\d{4}))?""")

    private fun nextWeekday(today: LocalDate, wd: Int): LocalDate {
        val delta = ((wd - (today.dayOfWeek.value - 1)) % 7 + 7) % 7
        return today.plusDays(if (delta == 0) 7L else delta.toLong())
    }

    private fun parseDate(word: String, today: LocalDate): LocalDate? {
        val m = DATE.matchEntire(word) ?: return null
        val d = m.groupValues[1].toInt(); val mo = m.groupValues[2].toInt(); val y = m.groupValues[3]
        val year = if (y.isEmpty()) today.year else if (y.length == 2) 2000 + y.toInt() else y.toInt()
        fun mk(yy: Int) = try { LocalDate.of(yy, mo, d) } catch (e: java.time.DateTimeException) { null }
        var res = mk(year) ?: return null
        if (y.isEmpty() && res.isBefore(today)) res = mk(year + 1) ?: return null
        return res
    }

    fun parse(text: String, topics: List<Topic>, today: LocalDate, defaultTopic: Long? = null): QuickTask {
        val words = text.split(Regex("\\s+")).filter { it.isNotEmpty() }
        val keep = mutableListOf<String>()
        var deadline: LocalDate? = null
        var topicId = defaultTopic
        var priority = PRIORITY_MEDIUM
        var i = 0
        while (i < words.size) {
            val raw = words[i]
            val low = raw.lowercase().trim(',', '.')
            val next = if (i + 1 < words.size) words[i + 1].lowercase().trim(',', '.') else ""
            when {
                raw == "!" || raw == "!!" || raw == "!!!" -> priority = PRIORITY_HIGH
                low in REL && deadline == null -> deadline = today.plusDays(REL.getValue(low))
                (low == "в" || low == "во") && next in WEEKDAYS && deadline == null -> { deadline = nextWeekday(today, WEEKDAYS.getValue(next)); i++ }
                low in WEEKDAYS && deadline == null -> deadline = nextWeekday(today, WEEKDAYS.getValue(low))
                raw.startsWith("#") && raw.length > 1 -> {
                    val name = raw.substring(1).lowercase()
                    val hit = topics.firstOrNull { it.name.lowercase().replace(" ", "") == name }
                        ?: topics.firstOrNull { it.name.lowercase().startsWith(name) }
                    if (hit != null) topicId = hit.id else keep += raw
                }
                deadline == null && parseDate(raw.trim(','), today) != null -> deadline = parseDate(raw.trim(','), today)
                else -> keep += raw
            }
            i++
        }
        val hints = mutableListOf<String>()
        deadline?.let { d ->
            hints += "срок: ${Logic.WD[d.dayOfWeek.value - 1]}, ${d.dayOfMonth} ${Logic.MONTHS_GEN[d.monthValue - 1]}" +
                (if (d.year != today.year) " ${d.year}" else "") + " (${Logic.dueText(d, today)})"
        }
        topicId?.let { id -> topics.firstOrNull { it.id == id }?.let { hints += "тема: ${it.name}" } }
        if (priority == PRIORITY_HIGH) hints += "высокий приоритет"
        return QuickTask(keep.joinToString(" ").trim(), deadline, topicId, priority, hints)
    }
}
