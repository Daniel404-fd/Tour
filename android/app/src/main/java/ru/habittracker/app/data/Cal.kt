package ru.habittracker.app.data

import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.YearMonth
import java.time.temporal.ChronoUnit

data class Occurrence(val event: Event, val start: LocalDateTime, val end: LocalDateTime) {
    val key get() = "${event.id}@$start"
}

/** Повторы и раскладка — как desktop/tracker/cal.py. */
object Cal {
    private fun addMonths(d: LocalDate, months: Long): LocalDate? {
        val ym = YearMonth.from(d).plusMonths(months)
        return if (d.dayOfMonth > ym.lengthOfMonth()) null else ym.atDay(d.dayOfMonth)   // 31-е пропускается, как в Google
    }

    private fun startDates(ev: Event, until: LocalDate): Sequence<LocalDate> = sequence {
        val first = ev.start.toLocalDate()
        val limit = if (ev.until != null && ev.until.isBefore(until)) ev.until else until
        val step = maxOf(1, ev.interval).toLong()
        when (ev.freq) {
            FREQ_NONE -> if (!first.isAfter(limit)) yield(first)
            FREQ_DAILY -> { var d = first; while (!d.isAfter(limit)) { yield(d); d = d.plusDays(step) } }
            FREQ_WEEKLY -> {
                val days = ev.weekdays.toSortedSet().ifEmpty { sortedSetOf(first.dayOfWeek.value - 1) }
                val week0 = first.minusDays((first.dayOfWeek.value - 1).toLong())
                var k = 0L
                while (true) {
                    val ws = week0.plusWeeks(k * step)
                    if (ws.isAfter(limit)) break
                    for (wd in days) { val d = ws.plusDays(wd.toLong()); if (!d.isBefore(first) && !d.isAfter(limit)) yield(d) }
                    k++
                }
            }
            FREQ_MONTHLY, FREQ_YEARLY -> {
                val months = if (ev.freq == FREQ_MONTHLY) step else 12 * step
                var k = 0L
                while (k < 2400) {
                    val d = addMonths(first, k * months); k++
                    if (d == null) continue
                    if (d.isAfter(limit)) break
                    yield(d)
                }
            }
        }
    }

    fun occurrences(events: List<Event>, start: LocalDateTime, end: LocalDateTime): List<Occurrence> {
        val out = mutableListOf<Occurrence>()
        for (ev in events) {
            val dur = ChronoUnit.MINUTES.between(ev.start, ev.end)
            val lookback = start.toLocalDate().minusDays(maxOf(0L, dur / 1440) + 1)
            for (d in startDates(ev, end.minusNanos(1).toLocalDate())) {
                if (d.isBefore(lookback) || d in ev.exdates) continue
                val s = LocalDateTime.of(d, ev.start.toLocalTime())
                val e = s.plusMinutes(dur)
                if ((e.isAfter(start) && s.isBefore(end)) || (dur == 0L && !s.isBefore(start) && s.isBefore(end))) out += Occurrence(ev, s, e)
            }
        }
        return out.sortedWith(compareBy<Occurrence>({ !it.event.allDay }, { it.start }, { -ChronoUnit.MINUTES.between(it.start, it.end) }, { it.event.id }))
    }

    fun onDay(occs: List<Occurrence>, day: LocalDate): List<Occurrence> {
        val s = day.atStartOfDay(); val e = s.plusDays(1)
        return occs.filter { (it.end.isAfter(s) && it.start.isBefore(e)) || (it.start == it.end && !it.start.isBefore(s) && it.start.isBefore(e)) }
    }

    /** Пересекающиеся события делят ширину: (колонка, всего колонок). */
    fun layoutColumns(items: List<Pair<Double, Double>>): List<Pair<Int, Int>> {
        val order = items.indices.sortedWith(compareBy<Int>({ items[it].first }, { -items[it].second }))
        val result = MutableList(items.size) { 0 to 1 }
        var cluster = mutableListOf<Int>(); var colEnd = mutableListOf<Double>(); var clusterEnd = Double.NEGATIVE_INFINITY
        fun close() { val n = colEnd.size; for (i in cluster) result[i] = result[i].first to n }
        for (i in order) {
            val s = items[i].first; val e = maxOf(items[i].second, s + 0.25)
            if (s >= clusterEnd && cluster.isNotEmpty()) { close(); cluster = mutableListOf(); colEnd = mutableListOf() }
            var c = colEnd.indexOfFirst { it <= s }
            if (c >= 0) colEnd[c] = e else { c = colEnd.size; colEnd += e }
            result[i] = c to 0; cluster += i; clusterEnd = maxOf(clusterEnd, e)
        }
        if (cluster.isNotEmpty()) close()
        return result
    }

    fun weekStart(d: LocalDate): LocalDate = d.minusDays((d.dayOfWeek.value - 1).toLong())

    fun monthGrid(year: Int, month: Int): List<List<LocalDate>> {
        val start = weekStart(LocalDate.of(year, month, 1))
        return (0 until 6).map { w -> (0 until 7).map { start.plusDays((w * 7 + it).toLong()) } }
    }

    fun recurrenceText(ev: Event): String {
        if (!ev.recurring) return ""
        val n = ev.interval
        var base = when (ev.freq) {
            FREQ_DAILY -> if (n == 1) "каждый день" else "каждые $n дн."
            FREQ_WEEKLY -> if (n == 1) "каждую неделю" else "каждые $n нед."
            FREQ_MONTHLY -> if (n == 1) "каждый месяц, ${ev.start.dayOfMonth}-го" else "каждые $n мес."
            else -> if (n == 1) "каждый год" else "каждые $n г."
        }
        if (ev.freq == FREQ_WEEKLY && ev.weekdays.isNotEmpty()) base += ": " + ev.weekdays.sorted().joinToString(", ") { Logic.WD[it] }
        if (ev.until != null) base += ", до ${ev.until}"
        return base.replaceFirstChar { it.uppercase() }
    }

    fun timeOf(minutes: Int): LocalTime = LocalTime.of(minutes / 60 % 24, minutes % 60)
}
