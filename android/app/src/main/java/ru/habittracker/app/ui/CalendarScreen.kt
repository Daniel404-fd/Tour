package ru.habittracker.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowLeft
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.outlined.Tune
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import ru.habittracker.app.App
import ru.habittracker.app.ConfirmDialog
import ru.habittracker.app.Nav
import ru.habittracker.app.TextInputDialog
import ru.habittracker.app.data.Cal
import ru.habittracker.app.data.CalendarInfo
import ru.habittracker.app.data.EVENT_COLORS
import ru.habittracker.app.data.Event
import ru.habittracker.app.data.FREQ_NAMES
import ru.habittracker.app.data.FREQ_NONE
import ru.habittracker.app.data.FREQ_WEEKLY
import ru.habittracker.app.data.Logic
import ru.habittracker.app.data.Occurrence
import ru.habittracker.app.data.REMINDER_CHOICES
import ru.habittracker.app.pickDate
import ru.habittracker.app.pickTime
import ru.habittracker.app.useData
import java.time.LocalDate
import java.time.LocalDateTime
import java.time.LocalTime
import java.time.YearMonth
import java.time.temporal.ChronoUnit

private fun hm(t: LocalDateTime) = "%02d:%02d".format(t.hour, t.minute)

@Composable
fun CalendarScreen(nav: Nav) {
    val repo = App.instance.repo
    val today = LocalDate.now()
    var day by remember { mutableStateOf(nav.calendarDay ?: today) }
    var month by remember { mutableStateOf(YearMonth.from(day)) }
    var editing by remember { mutableStateOf<Pair<Event, Occurrence?>?>(null) }
    var opened by remember { mutableStateOf<Occurrence?>(null) }
    var manage by remember { mutableStateOf(false) }
    val calendars = useData { repo.calendars() }
    val calMap = calendars.associateBy { it.id }
    val visible = calendars.filter { it.visible }.map { it.id }.toSet()
    val grid = remember(month) { Cal.monthGrid(month.year, month.monthValue) }
    val occs = useData { repo.events() }.let { evs ->
        remember(evs, month, visible) {
            Cal.occurrences(evs.filter { it.calendarId == null || it.calendarId in visible },
                grid.first().first().atStartOfDay(), grid.last().last().plusDays(1).atStartOfDay())
        }
    }
    val t = tok
    fun colorOf(o: Occurrence) = hex(o.event.color ?: calMap[o.event.calendarId]?.color ?: "#0B6E69")
    fun select(d: LocalDate) { day = d; nav.calendarDay = d; if (YearMonth.from(d) != month) month = YearMonth.from(d) }

    Box(Modifier.fillMaxSize()) {
        LazyColumn(Modifier.fillMaxSize().padding(horizontal = 12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            item {
                Row(Modifier.fillMaxWidth().padding(top = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                    Text("${Logic.MONTHS[month.monthValue - 1]} ${month.year}", style = Header, color = t.text, modifier = Modifier.weight(1f))
                    IconButton(onClick = { month = month.minusMonths(1) }) { Icon(Icons.AutoMirrored.Filled.KeyboardArrowLeft, "Предыдущий месяц") }
                    TextButton(onClick = { select(today) }) { Text("Сегодня") }
                    IconButton(onClick = { month = month.plusMonths(1) }) { Icon(Icons.AutoMirrored.Filled.KeyboardArrowRight, "Следующий месяц") }
                    IconButton(onClick = { manage = true }) { Icon(Icons.Outlined.Tune, "Календари") }
                }
                // ---- сетка месяца
                Row(Modifier.fillMaxWidth()) {
                    Logic.WD.forEachIndexed { i, w ->
                        Text(w, Modifier.weight(1f), textAlign = TextAlign.Center, fontSize = 12.sp, color = if (i >= 5) t.danger else t.text2)
                    }
                }
                grid.forEach { week ->
                    Row(Modifier.fillMaxWidth()) {
                        week.forEach { d ->
                            val dayOccs = Cal.onDay(occs, d)
                            val inMonth = d.monthValue == month.monthValue
                            val sel = d == day
                            Column(Modifier.weight(1f).aspectRatio(0.9f).padding(2.dp).clip(RoundedCornerShape(10.dp))
                                .background(if (sel) t.tealSoft else Color.Transparent).clickable { select(d) },
                                horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center) {
                                Box(Modifier.size(30.dp).clip(CircleShape).background(if (d == today) t.teal else Color.Transparent),
                                    contentAlignment = Alignment.Center) {
                                    Text("${d.dayOfMonth}", fontSize = 15.sp,
                                        fontWeight = if (d == today || sel) FontWeight.SemiBold else FontWeight.Normal,
                                        color = when { d == today -> t.tealText; !inMonth -> t.text3; else -> t.text })
                                }
                                Row(horizontalArrangement = Arrangement.spacedBy(2.dp), modifier = Modifier.height(8.dp)) {
                                    dayOccs.take(3).forEach { Dot(colorOf(it), 5.dp) }
                                }
                            }
                        }
                    }
                }
                Spacer(Modifier.height(4.dp))
                Text("${Logic.WEEKDAYS_FULL[day.dayOfWeek.value - 1]}, ${Logic.humanDate(day, today)}",
                    fontWeight = FontWeight.SemiBold, fontSize = 18.sp, color = t.text)
            }
            val list = Cal.onDay(occs, day).sortedWith(compareBy({ !it.event.allDay }, { it.start }))
            if (list.isEmpty()) item { EmptyText("Событий нет. Нажмите «+», чтобы запланировать.") }
            items(list, key = { it.key }) { o ->
                Row(Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(t.surface).clickable { opened = o }.padding(10.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.width(4.dp).height(38.dp).clip(RoundedCornerShape(2.dp)).background(colorOf(o)))
                    Spacer(Modifier.width(10.dp))
                    Column(Modifier.weight(1f)) {
                        Text(o.event.title.ifEmpty { "(без названия)" }, color = t.text, fontWeight = FontWeight.Medium,
                            maxLines = 1, overflow = TextOverflow.Ellipsis)
                        var w = if (o.event.allDay) "Весь день" else "${hm(o.start)}–${hm(o.end)}"
                        if (o.event.location.isNotEmpty()) w += " · ${o.event.location}"
                        if (o.event.recurring) w += " · повтор"
                        Caption(w, maxLines = 1)
                    }
                }
            }
            item { Spacer(Modifier.height(88.dp)) }
        }
        FloatingActionButton(onClick = {
            val now = LocalTime.now()
            val start = day.atTime(if (day == today) LocalTime.of(minOf(23, now.hour + 1), 0) else LocalTime.of(9, 0))
            editing = Event(title = "", start = start, end = start.plusHours(1), calendarId = calendars.firstOrNull()?.id) to null
        }, containerColor = t.teal, contentColor = t.tealText, modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp)) {
            Icon(Icons.Filled.Add, "Новое событие")
        }
    }
    opened?.let { o -> EventDetails(o, calMap[o.event.calendarId], onEdit = { opened = null; editing = o.event to o }, onClose = { opened = null }) }
    editing?.let { (ev, occ) -> EventEditor(ev, occ, calendars) { editing = null } }
    if (manage) CalendarsDialog(calendars) { manage = false }
}

// ---------------------------------------------------------------- просмотр события

@Composable
private fun EventDetails(o: Occurrence, cal: CalendarInfo?, onEdit: () -> Unit, onClose: () -> Unit) {
    val repo = App.instance.repo
    var askDelete by remember { mutableStateOf(false) }
    val ev = o.event
    AlertDialog(onDismissRequest = onClose, title = { Text(ev.title.ifEmpty { "(без названия)" }) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                val d = o.start.toLocalDate()
                Text(if (ev.allDay) "${Logic.humanDate(d)} · весь день"
                     else if (o.end.toLocalDate() == d) "${Logic.humanDate(d)}, ${hm(o.start)}–${hm(o.end)}"
                     else "${Logic.humanDate(d)}, ${hm(o.start)} — ${Logic.humanDate(o.end.toLocalDate())}, ${hm(o.end)}")
                if (ev.recurring) Caption(Cal.recurrenceText(ev))
                if (ev.location.isNotEmpty()) Caption("Место: ${ev.location}")
                cal?.let { Row(verticalAlignment = Alignment.CenterVertically) { Dot(hex(it.color)); Spacer(Modifier.width(6.dp)); Caption(it.name) } }
                ev.reminder?.let { r -> Caption("Напоминание: " + (REMINDER_CHOICES.firstOrNull { it.first == r }?.second?.lowercase() ?: "за $r мин")) }
                if (ev.description.isNotEmpty()) Text(ev.description)
            }
        },
        confirmButton = { TextButton(onClick = onEdit) { Text("Изменить") } },
        dismissButton = {
            Row {
                TextButton(onClick = { askDelete = true }) { Text("Удалить", color = tok.danger) }
                TextButton(onClick = onClose) { Text("Закрыть") }
            }
        })
    if (askDelete) {
        if (!ev.recurring) ConfirmDialog("Удалить событие", "Удалить «${ev.title}»?", "Удалить", { repo.deleteEvent(ev.id); onClose() }, { askDelete = false })
        else ScopeDialog("Удалить повторяющееся событие", { askDelete = false }) { scope ->
            val day = o.start.toLocalDate()
            when (scope) {
                0 -> repo.updateEvent(ev.copy(exdates = ev.exdates + day))
                1 -> if (!day.isAfter(ev.start.toLocalDate())) repo.deleteEvent(ev.id) else repo.updateEvent(ev.copy(until = day.minusDays(1)))
                else -> repo.deleteEvent(ev.id)
            }
            onClose()
        }
    }
}

/** «Только это / это и следующие / все» — как в Google Календаре. */
@Composable
private fun ScopeDialog(title: String, onDismiss: () -> Unit, onPick: (Int) -> Unit) {
    var scope by remember { mutableStateOf(0) }
    AlertDialog(onDismissRequest = onDismiss, title = { Text(title) },
        text = {
            Column {
                listOf("Только это событие", "Это и последующие", "Все события").forEachIndexed { i, s ->
                    Row(Modifier.fillMaxWidth().clickable { scope = i }.padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                        androidx.compose.material3.RadioButton(scope == i, { scope = i }); Text(s)
                    }
                }
            }
        },
        confirmButton = { TextButton(onClick = { onPick(scope); onDismiss() }) { Text("ОК") } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Отмена") } })
}

// ---------------------------------------------------------------- редактор

@Composable
private fun EventEditor(ev: Event, occ: Occurrence?, calendars: List<CalendarInfo>, onClose: () -> Unit) {
    val repo = App.instance.repo
    val ctx = LocalContext.current
    val t = tok
    val baseStart = occ?.start ?: ev.start
    val baseEnd = occ?.end ?: ev.end
    var title by remember { mutableStateOf(ev.title) }
    var allDay by remember { mutableStateOf(ev.allDay) }
    var startDay by remember { mutableStateOf(baseStart.toLocalDate()) }
    var startTime by remember { mutableStateOf(baseStart.toLocalTime()) }
    var endDay by remember { mutableStateOf(baseEnd.toLocalDate()) }
    var endTime by remember { mutableStateOf(baseEnd.toLocalTime()) }
    var calId by remember { mutableStateOf(ev.calendarId) }
    var color by remember { mutableStateOf(ev.color) }
    var freq by remember { mutableStateOf(ev.freq) }
    var interval by remember { mutableStateOf(ev.interval.toString()) }
    var weekdays by remember { mutableStateOf(ev.weekdays.toSet()) }
    var until by remember { mutableStateOf(ev.until) }
    var reminder by remember { mutableStateOf(ev.reminder) }
    var location by remember { mutableStateOf(ev.location) }
    var desc by remember { mutableStateOf(ev.description) }
    var freqMenu by remember { mutableStateOf(false) }
    var remMenu by remember { mutableStateOf(false) }
    var calMenu by remember { mutableStateOf(false) }
    var askScope by remember { mutableStateOf(false) }

    val start = if (allDay) startDay.atStartOfDay() else startDay.atTime(startTime)
    val end = if (allDay) endDay.plusDays(1).atStartOfDay() else endDay.atTime(endTime)
    val valid = end.isAfter(start)

    fun build(): Event = ev.copy(title = title.trim(), start = start, end = end, allDay = allDay, calendarId = calId, color = color,
        description = desc.trim(), location = location.trim(), freq = freq, interval = interval.toIntOrNull()?.coerceIn(1, 99) ?: 1,
        weekdays = if (freq == FREQ_WEEKLY) weekdays.sorted() else emptyList(), until = if (freq == FREQ_NONE) null else until,
        reminder = reminder)

    fun save(scope: Int) {
        val e = build()
        if (ev.id == 0L) { repo.addEvent(e); return }
        if (!ev.recurring || occ == null || scope == 2) {
            // правка всей серии: сдвиг на ту же разницу, что у выбранного повторения
            if (ev.recurring && occ != null) {
                val shift = ChronoUnit.MINUTES.between(occ.start, start)
                val dur = ChronoUnit.MINUTES.between(start, end)
                val s = ev.start.plusMinutes(shift)
                repo.updateEvent(e.copy(start = s, end = s.plusMinutes(dur), exdates = ev.exdates))
            } else repo.updateEvent(e)
            return
        }
        val day = occ.start.toLocalDate()
        if (scope == 0) {
            repo.updateEvent(ev.copy(exdates = ev.exdates + day))
            repo.addEvent(e.copy(id = 0, freq = FREQ_NONE, weekdays = emptyList(), until = null, exdates = emptyList()))
        } else {
            if (!day.isAfter(ev.start.toLocalDate())) repo.updateEvent(e)
            else {
                repo.updateEvent(ev.copy(until = day.minusDays(1)))
                repo.addEvent(e.copy(id = 0, exdates = ev.exdates.filter { !it.isBefore(day) }))
            }
        }
    }

    AlertDialog(onDismissRequest = onClose, title = { Text(if (ev.id == 0L) "Новое событие" else "Событие") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                OutlinedTextField(title, { title = it }, label = { Text("Название") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text("Весь день", Modifier.weight(1f)); Switch(allDay, { allDay = it })
                }
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Caption("Начало", modifier = Modifier.width(56.dp))
                    OutlinedButton(onClick = { pickDate(ctx, startDay) { d ->
                        val shift = ChronoUnit.DAYS.between(startDay, d); startDay = d; endDay = endDay.plusDays(shift) } }) { Text(Logic.humanDate(startDay)) }
                    if (!allDay) OutlinedButton(onClick = { pickTime(ctx, startTime) { tm ->
                        val dur = ChronoUnit.MINUTES.between(startDay.atTime(startTime), endDay.atTime(endTime))
                        startTime = tm; val ne = startDay.atTime(tm).plusMinutes(maxOf(15, dur)); endDay = ne.toLocalDate(); endTime = ne.toLocalTime() } }) {
                        Text("%02d:%02d".format(startTime.hour, startTime.minute)) }
                }
                Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Caption("Конец", modifier = Modifier.width(56.dp))
                    OutlinedButton(onClick = { pickDate(ctx, endDay) { endDay = it } }) { Text(Logic.humanDate(endDay)) }
                    if (!allDay) OutlinedButton(onClick = { pickTime(ctx, endTime) { endTime = it } }) { Text("%02d:%02d".format(endTime.hour, endTime.minute)) }
                }
                if (!valid) Caption("Конец должен быть позже начала", color = t.danger)
                // повтор
                Box {
                    OutlinedButton(onClick = { freqMenu = true }) { Text(FREQ_NAMES[freq] ?: "Не повторять") }
                    DropdownMenu(freqMenu, { freqMenu = false }) {
                        FREQ_NAMES.forEach { (k, n) -> DropdownMenuItem(text = { Text(n) }, onClick = { freq = k; freqMenu = false
                            if (k == FREQ_WEEKLY && weekdays.isEmpty()) weekdays = setOf(startDay.dayOfWeek.value - 1) }) }
                    }
                }
                if (freq != FREQ_NONE) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("Интервал", Modifier.weight(1f))
                        OutlinedTextField(interval, { v -> interval = v.filter { it.isDigit() }.take(2) }, singleLine = true, modifier = Modifier.width(80.dp))
                    }
                    if (freq == FREQ_WEEKLY) Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                        Logic.WD.forEachIndexed { i, w -> Chip(w, i in weekdays) { weekdays = if (i in weekdays && weekdays.size > 1) weekdays - i else weekdays + i } }
                    }
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        OutlinedButton(onClick = { pickDate(ctx, until ?: startDay.plusMonths(3)) { until = it } }) {
                            Text(until?.let { "До ${Logic.humanDate(it)}" } ?: "Бессрочно") }
                        if (until != null) TextButton(onClick = { until = null }) { Text("Убрать") }
                    }
                }
                // календарь, цвет, напоминание
                if (calendars.size > 1) Box {
                    OutlinedButton(onClick = { calMenu = true }) {
                        calendars.firstOrNull { it.id == calId }?.let { Dot(hex(it.color)); Spacer(Modifier.width(6.dp)) }
                        Text(calendars.firstOrNull { it.id == calId }?.name ?: "Календарь")
                    }
                    DropdownMenu(calMenu, { calMenu = false }) {
                        calendars.forEach { c -> DropdownMenuItem(text = { Text(c.name) }, leadingIcon = { Dot(hex(c.color)) },
                            onClick = { calId = c.id; calMenu = false }) }
                    }
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Caption("Цвет", modifier = Modifier.width(48.dp))
                    ColorRow(EVENT_COLORS.map { it.first }, color) { color = if (it.equals(color, true)) null else it }
                }
                Box {
                    OutlinedButton(onClick = { remMenu = true }) { Text(REMINDER_CHOICES.firstOrNull { it.first == reminder }?.second ?: "За $reminder мин") }
                    DropdownMenu(remMenu, { remMenu = false }) {
                        REMINDER_CHOICES.forEach { (v, n) -> DropdownMenuItem(text = { Text(n) }, onClick = { reminder = v; remMenu = false }) }
                    }
                }
                OutlinedTextField(location, { location = it }, label = { Text("Место") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(desc, { desc = it }, label = { Text("Описание") }, minLines = 2, modifier = Modifier.fillMaxWidth())
            }
        },
        confirmButton = {
            TextButton(enabled = valid, onClick = {
                if (ev.id != 0L && ev.recurring && occ != null) askScope = true else { save(2); onClose() }
            }) { Text("Сохранить") }
        },
        dismissButton = { TextButton(onClick = onClose) { Text("Отмена") } })
    if (askScope) ScopeDialog("Изменить повторяющееся событие", { askScope = false }) { save(it); onClose() }
}

// ---------------------------------------------------------------- календари

@Composable
private fun CalendarsDialog(calendars: List<CalendarInfo>, onClose: () -> Unit) {
    val repo = App.instance.repo
    var adding by remember { mutableStateOf(false) }
    var rename by remember { mutableStateOf<CalendarInfo?>(null) }
    var delete by remember { mutableStateOf<CalendarInfo?>(null) }
    var colorFor by remember { mutableStateOf<CalendarInfo?>(null) }
    AlertDialog(onDismissRequest = onClose, title = { Text("Календари") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState())) {
                Caption("Галочка — показывать события календаря.")
                calendars.forEach { c ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(c.visible, { repo.updateCalendar(c.copy(visible = it)) },
                            colors = CheckboxDefaults.colors(checkedColor = hex(c.color)))
                        Text(c.name, Modifier.weight(1f).clickable { rename = c })
                        IconButton(onClick = { colorFor = c }) { Dot(hex(c.color), 18.dp) }
                        if (calendars.size > 1) TextButton(onClick = { delete = c }) { Text("×") }
                    }
                }
                TextButton(onClick = { adding = true }) { Text("+ Новый календарь") }
            }
        },
        confirmButton = { TextButton(onClick = onClose) { Text("Готово") } })
    if (adding) TextInputDialog("Новый календарь", "", "Название", "Создать",
        { repo.addCalendar(it, EVENT_COLORS[calendars.size % EVENT_COLORS.size].first) }, { adding = false })
    rename?.let { c -> TextInputDialog("Переименовать календарь", c.name, "Название", onConfirm = { repo.updateCalendar(c.copy(name = it)) }, onDismiss = { rename = null }) }
    delete?.let { c -> ConfirmDialog("Удалить календарь", "Удалить «${c.name}» вместе со всеми его событиями?", "Удалить",
        { repo.deleteCalendar(c.id) }, { delete = null }) }
    colorFor?.let { c ->
        AlertDialog(onDismissRequest = { colorFor = null }, title = { Text("Цвет «${c.name}»") },
            text = { ColorRow(EVENT_COLORS.map { it.first }, c.color) { repo.updateCalendar(c.copy(color = it)); colorFor = null } },
            confirmButton = { TextButton(onClick = { colorFor = null }) { Text("Отмена") } })
    }
}
