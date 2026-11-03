package ru.habittracker.app

import android.Manifest
import android.app.DatePickerDialog
import android.app.TimePickerDialog
import android.content.Context
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.ui.unit.dp
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.CalendarMonth
import androidx.compose.material.icons.outlined.Checklist
import androidx.compose.material.icons.outlined.GridView
import androidx.compose.material.icons.outlined.Home
import androidx.compose.material.icons.outlined.MoreHoriz
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import ru.habittracker.app.ui.CalendarScreen
import ru.habittracker.app.ui.HabitsScreen
import ru.habittracker.app.ui.HomeScreen
import ru.habittracker.app.ui.MoreScreen
import ru.habittracker.app.ui.TasksScreen
import ru.habittracker.app.ui.TrackerTheme
import ru.habittracker.app.ui.tok
import java.time.LocalDate
import java.time.LocalTime

class MainActivity : ComponentActivity() {
    private val askNotifications = registerForActivityResult(ActivityResultContracts.RequestPermission()) {}

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        if (Build.VERSION.SDK_INT >= 33) askNotifications.launch(Manifest.permission.POST_NOTIFICATIONS)
        val start = intent?.getStringExtra("open") ?: "home"
        setContent { TrackerTheme { Root(start) } }
    }
}

data class Tab(val key: String, val title: String, val icon: ImageVector)

val TABS = listOf(
    Tab("home", "Главная", Icons.Outlined.Home),
    Tab("calendar", "Календарь", Icons.Outlined.CalendarMonth),
    Tab("habits", "Привычки", Icons.Outlined.GridView),
    Tab("tasks", "Задачи", Icons.Outlined.Checklist),
    Tab("more", "Ещё", Icons.Outlined.MoreHoriz),
)

/** Простая навигация: вкладка + подэкран внутри «Ещё» (цели, заметки, настройки). */
class Nav(tab: String) {
    var tab by mutableStateOf(tab)
    var more by mutableStateOf<String?>(null)
    var goalId by mutableStateOf<Long?>(null)
    var noteId by mutableStateOf<Long?>(null)
    var calendarDay by mutableStateOf<LocalDate?>(null)
    var taskId by mutableStateOf<Long?>(null)

    fun go(key: String) {
        when (key) {
            "goals", "notes", "settings", "stats" -> { tab = "more"; more = key }
            else -> { tab = key; if (key != "more") more = null }
        }
    }
}

@Composable
fun Root(start: String) {
    val nav = remember { Nav(if (start in TABS.map { it.key }) start else "home") }
    BackHandler(enabled = nav.tab != "home" || nav.more != null) {
        when {
            nav.noteId != null -> nav.noteId = null
            nav.goalId != null -> nav.goalId = null
            nav.more != null -> nav.more = null
            else -> nav.tab = "home"
        }
    }
    val t = tok
    Scaffold(containerColor = t.bg, bottomBar = {
        NavigationBar(containerColor = t.surface) {
            TABS.forEach { tab ->
                // только иконки: подписи занимали место и переносились («Календа-рь»); название — для TalkBack
                NavigationBarItem(selected = nav.tab == tab.key, onClick = {
                    if (nav.tab == tab.key && tab.key == "more") { nav.more = null; nav.goalId = null; nav.noteId = null }
                    nav.tab = tab.key
                },
                    icon = { Icon(tab.icon, contentDescription = tab.title, modifier = Modifier.size(26.dp)) },
                    alwaysShowLabel = false,
                    colors = NavigationBarItemDefaults.colors(indicatorColor = t.tealSoft, selectedIconColor = t.tealOnSoft,
                        selectedTextColor = t.tealOnSoft, unselectedIconColor = t.text2))
            }
        }
    }) { pad ->
        Box(Modifier.fillMaxSize().padding(pad)) {
            when (nav.tab) {
                "home" -> HomeScreen(nav)
                "calendar" -> CalendarScreen(nav)
                "habits" -> HabitsScreen()
                "tasks" -> TasksScreen(nav)
                else -> MoreScreen(nav)
            }
        }
    }
}

// ---------------------------------------------------------------- общие помощники

/** Данные перечитываются при каждом изменении базы (App.version). */
@Composable
fun <T> useData(block: () -> T): T {
    val v = App.instance.version
    return remember(v) { block() }
}

fun pickDate(ctx: Context, initial: LocalDate, onPick: (LocalDate) -> Unit) {
    DatePickerDialog(ctx, { _, y, m, d -> onPick(LocalDate.of(y, m + 1, d)) },
        initial.year, initial.monthValue - 1, initial.dayOfMonth).apply { datePicker.firstDayOfWeek = java.util.Calendar.MONDAY }.show()
}

fun pickTime(ctx: Context, initial: LocalTime, onPick: (LocalTime) -> Unit) {
    TimePickerDialog(ctx, { _, h, m -> onPick(LocalTime.of(h, m)) }, initial.hour, initial.minute, true).show()
}

@Composable
fun ConfirmDialog(title: String, text: String, confirm: String, onConfirm: () -> Unit, onDismiss: () -> Unit) {
    AlertDialog(onDismissRequest = onDismiss, title = { Text(title) }, text = { Text(text) },
        confirmButton = { TextButton(onClick = { onConfirm(); onDismiss() }) { Text(confirm, color = tok.danger) } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Отмена") } })
}

@Composable
fun TextInputDialog(title: String, initial: String, label: String, confirm: String = "Сохранить",
                    onConfirm: (String) -> Unit, onDismiss: () -> Unit) {
    var value by rememberSaveable { mutableStateOf(initial) }
    AlertDialog(onDismissRequest = onDismiss, title = { Text(title) },
        text = { OutlinedTextField(value, { value = it }, label = { Text(label) }, singleLine = true) },
        confirmButton = { TextButton(enabled = value.isNotBlank(), onClick = { onConfirm(value.trim()); onDismiss() }) { Text(confirm) } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Отмена") } })
}
