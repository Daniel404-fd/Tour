package ru.habittracker.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import ru.habittracker.app.App
import ru.habittracker.app.Nav
import ru.habittracker.app.data.Cal
import ru.habittracker.app.data.Logic
import ru.habittracker.app.data.PRIORITY_HIGH
import ru.habittracker.app.useData
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime

private val PERIODS = listOf(4 to "4 дня", 7 to "Неделя", 14 to "Две недели")

@Composable
fun HomeScreen(nav: Nav) {
    val repo = App.instance.repo
    val today = LocalDate.now()
    val habits = useData { repo.habits() }
    val marks = useData { repo.allMarks() }
    val tasks = useData { repo.tasks() }
    val topics = useData { repo.topics().associateBy { it.id } }
    val calendars = useData { repo.calendars().associateBy { it.id } }
    val occs = useData {
        val visible = calendars.values.filter { it.visible }.map { it.id }.toSet()
        Cal.occurrences(repo.events().filter { it.calendarId in visible }, today.atStartOfDay(), today.plusDays(1).atStartOfDay())
    }
    val goals = useData { repo.goals().filter { !it.done && !it.archived }.sortedWith(compareBy({ it.targetDate == null }, { it.targetDate ?: LocalDate.MAX })) }
    val steps = useData { repo.allSteps() }
    val saved = useData { repo.savedAmounts() }
    val subs = useData { repo.allSubtasks() }
    var period by remember { mutableStateOf(repo.pref("upcoming_days", "4")!!.toIntOrNull() ?: 4) }
    val t = tok

    LazyColumn(Modifier.fillMaxWidth().padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        item {
            Spacer(Modifier.height(12.dp))
            Text("${Logic.WEEKDAYS_FULL[today.dayOfWeek.value - 1]}, ${Logic.humanDate(today, today)}", style = Header, color = t.text)
            val left = habits.count { today !in (marks[it.id] ?: emptySet()) }
            val overdue = tasks.count { Logic.isOverdue(it, today) }
            val h = LocalTime.now().hour
            val hello = when (h) { in 5..11 -> "Доброе утро."; in 12..17 -> "Добрый день."; in 18..22 -> "Добрый вечер."; else -> "Доброй ночи." }
            val parts = listOfNotNull(hello,
                if (habits.isEmpty()) null else if (left == 0) "Все привычки отмечены." else "Осталось отметить $left ${Logic.plural(left, "привычку", "привычки", "привычек")}.",
                if (overdue > 0) "$overdue ${Logic.plural(overdue, "задача просрочена", "задачи просрочены", "задач просрочено")}." else null)
            Secondary(parts.joinToString(" "))
        }
        // ---- календарь на сегодня
        item {
            Card("Сегодня в календаре", action = { TextButton(onClick = { nav.calendarDay = today; nav.go("calendar") }) { Text("Календарь") } }) {
                if (occs.isEmpty()) Secondary("На сегодня событий нет.")
                val now = LocalDateTime.now()
                occs.take(6).forEach { o ->
                    val color = hex(o.event.color ?: calendars[o.event.calendarId]?.color ?: "#0B6E69")
                    Row(Modifier.fillMaxWidth().clickable { nav.calendarDay = today; nav.go("calendar") }.padding(vertical = 4.dp),
                        verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.width(4.dp).height(34.dp).clip(RoundedCornerShape(2.dp)).background(color))
                        Spacer(Modifier.width(10.dp))
                        Column {
                            Text(o.event.title.ifEmpty { "(без названия)" }, color = if (!o.event.allDay && !o.end.isAfter(now)) t.text2 else t.text)
                            var w = if (o.event.allDay) "Весь день" else "%02d:%02d–%02d:%02d".format(o.start.hour, o.start.minute, o.end.hour, o.end.minute)
                            if (!o.event.allDay && !o.start.isAfter(now) && o.end.isAfter(now)) w += " · идёт сейчас"
                            if (o.event.location.isNotEmpty()) w += " · ${o.event.location}"
                            Caption(w)
                        }
                    }
                }
            }
        }
        // ---- привычки
        item {
            Card("Привычки сегодня", action = { TextButton(onClick = { nav.go("habits") }) { Text("Все") } }) {
                if (habits.isEmpty()) Secondary("Добавьте первую привычку — и отмечайте её здесь одним касанием.")
                habits.forEach { h ->
                    val hm = marks[h.id] ?: emptySet()
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(today in hm, { repo.setMark(h.id, today, it) },
                            colors = CheckboxDefaults.colors(checkedColor = t.accent, checkmarkColor = t.accentText))
                        Text(h.name, Modifier.weight(1f), color = t.text)
                        val s = Logic.currentStreak(hm, today)
                        if (s > 0) Caption("$s ${Logic.plural(s, "день", "дня", "дней")} ", modifier = Modifier.padding(end = 6.dp))
                        HeatStrip(Logic.lastDays(today, 7), hm, today, cell = 8.dp, gap = 2.dp)
                    }
                }
            }
        }
        // ---- ближайшие задачи
        item {
            val upcoming = Logic.upcoming(tasks, today, period)
            var menu by remember { mutableStateOf(false) }
            Card("Ближайшие задачи", action = {
                Box {
                    TextButton(onClick = { menu = true }) { Text(PERIODS.first { it.first == period }.second + " ▾") }
                    DropdownMenu(menu, { menu = false }) {
                        PERIODS.forEach { (v, n) -> DropdownMenuItem(text = { Text(n) }, onClick = { period = v; repo.setPref("upcoming_days", v.toString()); menu = false }) }
                    }
                }
            }) {
                Caption("Просроченные и со сроком на " + when (period) { 4 -> "ближайшие 4 дня"; 7 -> "ближайшую неделю"; else -> "ближайшие две недели" })
                if (upcoming.isEmpty()) Secondary("На ближайшие дни сроков нет.")
                upcoming.take(10).forEach { task ->
                    Row(Modifier.fillMaxWidth().clickable { nav.taskId = task.id; nav.go("tasks") }, verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(false, { repo.updateTask(task.copy(done = true)) },
                            colors = CheckboxDefaults.colors(checkedColor = t.accent))
                        Column(Modifier.weight(1f)) {
                            Text(task.title, color = t.text, fontWeight = if (task.priority == PRIORITY_HIGH) FontWeight.SemiBold else FontWeight.Normal)
                            topics[task.topicId]?.let { tp ->
                                Row(verticalAlignment = Alignment.CenterVertically) { Dot(hex(tp.color), 7.dp); Spacer(Modifier.width(4.dp)); Caption(tp.name) }
                            }
                        }
                        subs[task.id]?.let { st -> Caption("${st.count { it.done }}/${st.size}  ", modifier = Modifier.padding(end = 4.dp)) }
                        val d = task.deadline!!
                        Caption(Logic.dueText(d, today), color = when { Logic.isOverdue(task, today) -> t.danger; d == today -> t.warn; else -> t.text2 })
                    }
                }
            }
        }
        // ---- график
        item {
            Card("Привычки за 14 дней") {
                if (habits.isEmpty()) Secondary("График появится, когда вы начнёте отмечать привычки.")
                else {
                    val pts = Logic.completionByDay(habits, marks, today, 14)
                    Caption("В среднем ${pts.map { it.second }.average().toInt()}% отмечено")
                    MiniBars(pts.map { it.second })
                }
            }
        }
        // ---- цели
        item {
            Card("Цели", action = { TextButton(onClick = { nav.go("goals") }) { Text("Все") } }) {
                if (goals.isEmpty()) Secondary("Поставьте долгосрочную цель и разбейте её на шаги.")
                goals.take(3).forEach { g ->
                    val p = Logic.goalProgress(g, steps[g.id] ?: emptyList(), saved[g.id] ?: 0.0)
                    Column(Modifier.fillMaxWidth().clickable { nav.goalId = g.id; nav.go("goals") }.padding(vertical = 4.dp),
                        verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Row { Text(g.title, Modifier.weight(1f), color = t.text); Caption("${(p * 100).toInt()}%") }
                        BlocksProgress(p)
                        g.targetDate?.let { Caption("До ${Logic.humanDate(it, today)} · ${Logic.dueText(it, today)}") }
                    }
                }
            }
        }
        item { Spacer(Modifier.height(16.dp)) }
    }
}

/** Мини-график: столбики собраны из «кирпичиков». */
@Composable
fun MiniBars(values: List<Double>) {
    val t = tok
    androidx.compose.foundation.Canvas(Modifier.fillMaxWidth().height(80.dp)) {
        val n = values.size
        val slot = size.width / n
        val bw = slot * 0.6f
        val block = 5.dp.toPx(); val gap = 2.dp.toPx()
        val cap = (size.height / (block + gap)).toInt()
        values.forEachIndexed { i, v ->
            var count = Math.round(cap * v / 100.0).toInt()
            if (v > 0 && count == 0) count = 1
            val x = i * slot + (slot - bw) / 2
            for (k in 0 until count) {
                drawRoundRect(t.accent, topLeft = androidx.compose.ui.geometry.Offset(x, size.height - (k + 1) * (block + gap) + gap),
                    size = androidx.compose.ui.geometry.Size(bw, block), cornerRadius = androidx.compose.ui.geometry.CornerRadius(1.5f))
            }
        }
    }
}
