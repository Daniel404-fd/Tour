package ru.habittracker.app.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.outlined.MoreVert
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import ru.habittracker.app.App
import ru.habittracker.app.ConfirmDialog
import ru.habittracker.app.TextInputDialog
import ru.habittracker.app.data.EDITABLE_DAYS
import ru.habittracker.app.data.Habit
import ru.habittracker.app.data.Logic
import ru.habittracker.app.useData
import java.time.LocalDate

@Composable
fun HabitsScreen() {
    val repo = App.instance.repo
    var archive by remember { mutableStateOf(false) }
    var adding by remember { mutableStateOf(false) }
    val habits = useData { repo.habits(includeArchived = true).filter { it.archived == archive } }
    val marks = useData { repo.allMarks() }
    val today = LocalDate.now()
    val t = tok

    Box(Modifier.fillMaxSize()) {
        LazyColumn(Modifier.fillMaxSize().padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            item {
                Spacer(Modifier.height(12.dp))
                Text("Привычки", style = Header, color = t.text)
                val active = repo.habits()
                val done = active.count { today in (marks[it.id] ?: emptySet()) }
                Secondary(if (archive) "Привычки в архиве" else if (active.isEmpty()) "" else "Сегодня отмечено $done из ${active.size}")
                Spacer(Modifier.height(4.dp))
                Row { Chip("Активные", !archive) { archive = false }; Spacer(Modifier.width(8.dp)); Chip("Архив", archive) { archive = true } }
            }
            if (habits.isEmpty()) item {
                EmptyText(if (archive) "В архиве пусто." else "Привычек пока нет. Нажмите «+», чтобы добавить — например, «Зарядка».")
            }
            items(habits, key = { it.id }) { h -> Box(Modifier.animateItem()) { HabitCard(h, marks[h.id] ?: emptySet(), today) } }
            item { Spacer(Modifier.height(88.dp)) }
        }
        if (!archive) FloatingActionButton(onClick = { adding = true }, containerColor = t.teal, contentColor = t.tealText,
            modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp)) { Icon(Icons.Filled.Add, "Новая привычка") }
    }
    if (adding) TextInputDialog("Новая привычка", "", "Название", "Добавить", { repo.addHabit(it) }, { adding = false })
}

@Composable
private fun HabitCard(h: Habit, marks: Set<LocalDate>, today: LocalDate) {
    val repo = App.instance.repo
    val t = tok
    var menu by remember { mutableStateOf(false) }
    var rename by remember { mutableStateOf(false) }
    var delete by remember { mutableStateOf(false) }
    Card {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(Modifier.weight(1f)) {
                Text(h.name, fontWeight = FontWeight.SemiBold, fontSize = 17.sp, color = t.text)
                val cur = Logic.currentStreak(marks, today)
                Caption(if (h.archived) "В архиве" else "Серия: $cur ${Logic.plural(cur, "день", "дня", "дней")} · рекорд ${Logic.bestStreak(marks)}")
            }
            Box {
                IconButton(onClick = { menu = true }) { Icon(Icons.Outlined.MoreVert, "Действия с привычкой «${h.name}»") }
                DropdownMenu(menu, { menu = false }) {
                    if (!h.archived) {
                        DropdownMenuItem(text = { Text("Переименовать") }, onClick = { menu = false; rename = true })
                        DropdownMenuItem(text = { Text("В архив") }, onClick = { menu = false; repo.archiveHabit(h.id, true) })
                    } else DropdownMenuItem(text = { Text("Вернуть из архива") }, onClick = { menu = false; repo.archiveHabit(h.id, false) })
                    DropdownMenuItem(text = { Text("Удалить навсегда", color = t.danger) }, onClick = { menu = false; delete = true })
                }
            }
        }
        if (!h.archived) Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
            Logic.lastDays(today, EDITABLE_DAYS).forEach { d ->
                val on = d in marks
                Surface(onClick = { repo.setMark(h.id, d, !on) }, shape = RoundedCornerShape(8.dp),
                    color = if (on) t.accent else t.surface,
                    border = BorderStroke(1.dp, if (on) t.accent else if (d == today) t.text2 else t.borderStrong),
                    modifier = Modifier.weight(1f).heightIn(min = 48.dp)) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center,
                        modifier = Modifier.padding(vertical = 6.dp)) {
                        Text(if (d == today) "сег" else Logic.WD[d.dayOfWeek.value - 1], fontSize = 11.sp,
                            color = if (on) t.accentText else t.text2, textAlign = TextAlign.Center)
                        Text("${d.dayOfMonth}", fontSize = 15.sp, fontWeight = if (on || d == today) FontWeight.SemiBold else FontWeight.Normal,
                            color = if (on) t.accentText else t.text)
                    }
                }
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            val days = Logic.lastDays(today, 30)
            HeatStrip(days, marks, today, cell = 8.dp, gap = 2.dp)
            Spacer(Modifier.width(8.dp))
            Caption("${days.count { it in marks }} из 30")
        }
    }
    if (rename) TextInputDialog("Переименовать привычку", h.name, "Название", onConfirm = { repo.renameHabit(h.id, it) }, onDismiss = { rename = false })
    if (delete) ConfirmDialog("Удалить привычку", "Удалить «${h.name}» вместе со всеми отметками? Это нельзя отменить. Чтобы просто убрать из списка — отправьте в архив.",
        "Удалить", { repo.deleteHabit(h.id) }, { delete = false })
}
