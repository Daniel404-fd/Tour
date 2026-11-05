package ru.habittracker.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.border
import androidx.compose.ui.draw.clip
import androidx.compose.material.icons.filled.Check
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.outlined.Notes
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.outlined.Flag
import androidx.compose.material.icons.outlined.Folder
import androidx.compose.material.icons.outlined.MoreVert
import androidx.compose.material.icons.outlined.PushPin
import androidx.compose.material.icons.outlined.Settings
import androidx.compose.material.icons.outlined.Sync
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.delay
import ru.habittracker.app.App
import ru.habittracker.app.ConfirmDialog
import ru.habittracker.app.Nav
import ru.habittracker.app.TextInputDialog
import ru.habittracker.app.data.Goal
import ru.habittracker.app.data.GoalStep
import ru.habittracker.app.data.Logic
import ru.habittracker.app.data.Note
import ru.habittracker.app.pickDate
import ru.habittracker.app.useData
import java.time.LocalDate
import java.time.temporal.ChronoUnit

@Composable
fun MoreScreen(nav: Nav) {
    when (nav.more) {
        "goals" -> GoalsScreen(nav)
        "notes" -> NotesScreen(nav)
        "settings" -> SettingsScreen(nav)
        else -> MoreMenu(nav)
    }
}

@Composable
private fun MoreMenu(nav: Nav) {
    val t = tok
    Column(Modifier.fillMaxSize().padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text("Ещё", style = Header, color = t.text)
        listOf(Triple("goals", "Цели", Icons.Outlined.Flag), Triple("notes", "Заметки", Icons.AutoMirrored.Outlined.Notes),
            Triple("settings", "Настройки и синхронизация", Icons.Outlined.Settings)).forEach { (k, n, i) ->
            Card(modifier = Modifier.clickable { nav.more = k }) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Icon(i, null, tint = t.teal); Spacer(Modifier.width(14.dp)); Text(n, fontSize = 17.sp, color = t.text)
                }
            }
        }
        val s = App.instance.sync
        if (s.enabled) Caption(s.status.ifEmpty { "Синхронизация включена" }, color = if (s.ok) t.text2 else t.danger)
    }
}

@Composable
fun BackTitle(title: String, onBack: () -> Unit, actions: @Composable () -> Unit = {}) {
    Row(Modifier.fillMaxWidth().padding(top = 8.dp, end = 8.dp), verticalAlignment = Alignment.CenterVertically) {
        IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Назад") }
        Text(title, style = Header.copy(fontSize = 22.sp), color = tok.text, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
        actions()
    }
}

// ======================================================================== цели

@Composable
fun GoalsScreen(nav: Nav) {
    val repo = App.instance.repo
    val goals = useData { repo.goals() }
    val steps = useData { repo.allSteps() }
    val saved = useData { repo.savedAmounts() }
    var filter by remember { mutableStateOf("active") }
    var editing by remember { mutableStateOf<Goal?>(null) }
    val today = LocalDate.now()
    val t = tok
    val open = nav.goalId?.let { id -> goals.firstOrNull { it.id == id } }
    if (open != null) { GoalDetail(open, steps[open.id] ?: emptyList(), saved[open.id] ?: 0.0, onBack = { nav.goalId = null }, onEdit = { editing = open }); editing?.let { GoalEditor(it) { editing = null } }; return }

    val shown = goals.filter { when (filter) { "done" -> it.done && !it.archived; "archived" -> it.archived; else -> !it.done && !it.archived } }
        .sortedWith(compareBy({ it.done }, { it.targetDate == null }, { it.targetDate ?: LocalDate.MAX }))
    Box(Modifier.fillMaxSize()) {
        LazyColumn(Modifier.fillMaxSize().padding(horizontal = 16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            item {
                BackTitle("Цели", { nav.more = null })
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    listOf("active" to "Активные", "done" to "Достигнутые", "archived" to "Архив").forEach { (k, n) -> Chip(n, filter == k) { filter = k } }
                }
            }
            if (shown.isEmpty()) item { EmptyText(if (filter == "active") "Целей пока нет. Цели — то, к чему вы идёте месяцами. Нажмите «+»." else "Здесь пусто.") }
            items(shown, key = { it.id }) { g ->
                val s = saved[g.id] ?: 0.0
                val st = steps[g.id] ?: emptyList()
                val p = Logic.goalProgress(g, st, s)
                Card(modifier = Modifier.clickable { nav.goalId = g.id }) {
                    Text(g.title, fontWeight = FontWeight.SemiBold, color = t.text)
                    BlocksProgress(p)
                    var info = "${(p * 100).toInt()}%"
                    if (g.financial) info += " · ${Logic.formatMoney(s)} из ${Logic.formatMoney(g.targetAmount)}"
                    if (st.isNotEmpty()) info += " · ${st.count { it.done }} из ${st.size} ${Logic.plural(st.size, "шага", "шагов", "шагов")}"
                    Caption(info)
                    g.targetDate?.let { Caption("До ${Logic.humanDate(it, today)} · ${Logic.dueText(it, today)}", color = deadlineColor(g, today)) }
                }
            }
            item { Spacer(Modifier.height(88.dp)) }
        }
        FloatingActionButton(onClick = { editing = Goal(title = "") }, containerColor = t.teal, contentColor = t.tealText,
            modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp)) { Icon(Icons.Filled.Add, "Новая цель") }
    }
    editing?.let { GoalEditor(it) { editing = null } }
}

@Composable
private fun deadlineColor(g: Goal, today: LocalDate): Color {
    val d = g.targetDate ?: return tok.text2
    val days = ChronoUnit.DAYS.between(today, d)
    return when { g.done -> tok.text2; days < 0 -> tok.danger; days <= 14 -> tok.warn; else -> tok.text2 }
}

@Composable
private fun GoalDetail(g: Goal, steps: List<GoalStep>, saved: Double, onBack: () -> Unit, onEdit: () -> Unit) {
    val repo = App.instance.repo
    val t = tok
    val today = LocalDate.now()
    var newStep by remember { mutableStateOf("") }
    var menu by remember { mutableStateOf(false) }
    var delete by remember { mutableStateOf(false) }
    var money by remember { mutableStateOf<Boolean?>(null) }   // true — снять, false — пополнить
    val history = useData { repo.contributions(g.id) }
    val p = Logic.goalProgress(g, steps, saved)
    LazyColumn(Modifier.fillMaxSize().padding(horizontal = 16.dp).imePadding(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        item {
            BackTitle(g.title, onBack) {
                Box {
                    IconButton(onClick = { menu = true }) { Icon(Icons.Outlined.MoreVert, "Действия с целью") }
                    DropdownMenu(menu, { menu = false }) {
                        DropdownMenuItem(text = { Text("Изменить") }, onClick = { menu = false; onEdit() })
                        DropdownMenuItem(text = { Text(if (g.archived) "Вернуть из архива" else "В архив") }, onClick = { menu = false; repo.updateGoal(g.copy(archived = !g.archived)) })
                        DropdownMenuItem(text = { Text("Удалить навсегда", color = t.danger) }, onClick = { menu = false; delete = true })
                    }
                }
            }
        }
        item {
            Card {
                g.targetDate?.let { Caption("До ${Logic.humanDate(it, today)} · ${Logic.dueText(it, today)}", color = deadlineColor(g, today)) }
                if (g.description.isNotEmpty()) Text(g.description, color = t.text)
                Row(verticalAlignment = Alignment.CenterVertically) {
                    BlocksProgress(p, Modifier.weight(1f)); Spacer(Modifier.width(10.dp))
                    Text("${(p * 100).toInt()}%", color = t.accent, fontWeight = FontWeight.SemiBold)
                }
                if (g.financial && g.targetAmount > 0 && steps.isNotEmpty() && !g.done)
                    Caption("Прогресс считается поровну: накопления ${(Logic.moneyProgress(g, saved) * 100).toInt()}% и шаги ${steps.count { it.done } * 100 / steps.size}%.")
                if (!g.archived) Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    if (g.done) OutlinedButton(onClick = { repo.updateGoal(g.copy(done = false, completedOn = null)) }) { Text("Вернуть в работу") }
                    else Button(onClick = { repo.updateGoal(g.copy(done = true)) },
                        colors = ButtonDefaults.buttonColors(containerColor = t.teal)) { Text("Цель достигнута") }
                    OutlinedButton(onClick = onEdit) { Text("Изменить") }
                }
            }
        }
        if (g.financial) item {
            Card("Накопления") {
                Text("${Logic.formatMoney(saved)} из ${Logic.formatMoney(g.targetAmount)}", fontSize = 22.sp, fontWeight = FontWeight.SemiBold, color = t.text)
                BlocksProgress(Logic.moneyProgress(g, saved))
                val left = g.targetAmount - saved
                if (left > 0) {
                    var hint = "Осталось ${Logic.formatMoney(left)}"
                    val td = g.targetDate
                    if (td != null && td.isAfter(today) && !g.done) {
                        val months = maxOf(1.0, ChronoUnit.DAYS.between(today, td) / 30.44)
                        hint += " · откладывайте ≈ ${Logic.formatMoney(Math.round(left / months / 100.0) * 100.0)} в месяц"
                    }
                    Secondary(hint)
                } else Text("Нужная сумма накоплена", color = t.accent, fontWeight = FontWeight.SemiBold)
                if (!g.archived) Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { money = false }, colors = ButtonDefaults.buttonColors(containerColor = t.teal)) { Text("Пополнить") }
                    OutlinedButton(onClick = { money = true }) { Text("Снять") }
                }
                if (history.isNotEmpty()) Caption("История")
                history.take(10).forEach { c ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Caption(c.day.format(java.time.format.DateTimeFormatter.ofPattern("dd.MM.yyyy")), modifier = Modifier.width(90.dp))
                        Text((if (c.amount > 0) "+" else "") + Logic.formatMoney(c.amount), color = if (c.amount > 0) t.text else t.danger,
                            modifier = Modifier.width(110.dp), fontSize = 14.sp)
                        Caption(c.note, modifier = Modifier.weight(1f), maxLines = 1)
                        if (!g.archived) TextButton(onClick = { repo.deleteContribution(c.id) }) { Text("×") }
                    }
                }
            }
        }
        item {
            Card("Шаги" + if (steps.isNotEmpty()) " · ${steps.count { it.done }} из ${steps.size}" else "") {
                if (steps.isEmpty()) Secondary("Разбейте цель на конкретные шаги — так проще начать и видно, сколько осталось.")
                steps.forEach { s ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Checkbox(s.done, { repo.setStepDone(s.id, it) }, enabled = !g.archived,
                            colors = CheckboxDefaults.colors(checkedColor = t.accent, checkmarkColor = t.accentText))
                        Text(s.title, Modifier.weight(1f), color = if (s.done) t.text2 else t.text,
                            textDecoration = if (s.done) TextDecoration.LineThrough else null)
                        if (!g.archived) TextButton(onClick = { repo.deleteStep(s.id) }) { Text("×") }
                    }
                }
                if (!g.archived && !g.done) Row(verticalAlignment = Alignment.CenterVertically) {
                    OutlinedTextField(newStep, { newStep = it }, label = { Text("Новый шаг") }, singleLine = true, modifier = Modifier.weight(1f))
                    TextButton(enabled = newStep.isNotBlank(), onClick = { repo.addStep(g.id, newStep.trim()); newStep = "" }) { Text("Добавить") }
                }
            }
        }
        item { Spacer(Modifier.height(24.dp)) }
    }
    money?.let { withdraw -> ContributionDialog(g, withdraw) { money = null } }
    if (delete) ConfirmDialog("Удалить цель", "Удалить «${g.title}» вместе с шагами и накоплениями? Это нельзя отменить.", "Удалить",
        { repo.deleteGoal(g.id); onBack() }, { delete = false })
}

@Composable
private fun ContributionDialog(g: Goal, withdraw: Boolean, onClose: () -> Unit) {
    val repo = App.instance.repo
    val ctx = LocalContext.current
    var amount by remember { mutableStateOf("") }
    var note by remember { mutableStateOf("") }
    var day by remember { mutableStateOf(LocalDate.now()) }
    val v = Logic.parseMoney(amount)
    AlertDialog(onDismissRequest = onClose, title = { Text(if (withdraw) "Снять с накоплений" else "Пополнить накопления") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedTextField(amount, { amount = it }, label = { Text("Сумма, ₽") }, singleLine = true,
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal))
                OutlinedButton(onClick = { pickDate(ctx, day) { day = it } }) { Text(Logic.humanDate(day)) }
                OutlinedTextField(note, { note = it }, label = { Text("Комментарий") }, singleLine = true)
            }
        },
        confirmButton = {
            TextButton(enabled = v != null && v > 0, onClick = {
                repo.addContribution(g.id, if (withdraw) -v!! else v!!, day, note.trim()); onClose()
            }) { Text(if (withdraw) "Снять" else "Внести") }
        }, dismissButton = { TextButton(onClick = onClose) { Text("Отмена") } })
}

@Composable
private fun GoalEditor(goal: Goal, onClose: () -> Unit) {
    val repo = App.instance.repo
    val ctx = LocalContext.current
    var title by remember { mutableStateOf(goal.title) }
    var desc by remember { mutableStateOf(goal.description) }
    var date by remember { mutableStateOf(goal.targetDate) }
    var financial by remember { mutableStateOf(goal.financial) }
    var target by remember { mutableStateOf(if (goal.targetAmount > 0) Logic.formatMoney(goal.targetAmount).removeSuffix(" ₽") else "") }
    var initial by remember { mutableStateOf("") }
    val t = tok
    val targetOk = !financial || (Logic.parseMoney(target) ?: 0.0) > 0
    AlertDialog(onDismissRequest = onClose, title = { Text(if (goal.id == 0L) "Новая цель" else "Цель") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedTextField(title, { title = it }, label = { Text("Цель") }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(desc, { desc = it }, label = { Text("Описание") }, minLines = 2, modifier = Modifier.fillMaxWidth())
                Row(verticalAlignment = Alignment.CenterVertically) {
                    OutlinedButton(onClick = { pickDate(ctx, date ?: LocalDate.of(LocalDate.now().year, 12, 31)) { date = it } }) {
                        Text(date?.let { "До " + Logic.humanDate(it) } ?: "Без срока")
                    }
                    if (date != null) TextButton(onClick = { date = null }) { Text("Убрать") }
                }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(financial, { financial = it }, colors = CheckboxDefaults.colors(checkedColor = t.accent))
                    Text("Финансовая цель — копить деньги")
                }
                if (financial) {
                    OutlinedTextField(target, { target = it }, label = { Text("Сколько накопить, ₽") }, singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal))
                    if (goal.id == 0L) OutlinedTextField(initial, { initial = it }, label = { Text("Уже отложено, ₽") }, singleLine = true,
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal))
                }
            }
        },
        confirmButton = {
            TextButton(enabled = title.isNotBlank() && targetOk, onClick = {
                val g = goal.copy(title = title.trim(), description = desc.trim(), targetDate = date, financial = financial,
                    targetAmount = if (financial) Logic.parseMoney(target) ?: 0.0 else goal.targetAmount)
                if (goal.id == 0L) {
                    val id = repo.addGoal(g)
                    val init = Logic.parseMoney(initial) ?: 0.0
                    if (financial && init > 0) repo.addContribution(id, init, note = "уже было отложено")
                } else repo.updateGoal(g)
                onClose()
            }) { Text("Сохранить") }
        }, dismissButton = { TextButton(onClick = onClose) { Text("Отмена") } })
}

// ======================================================================== заметки

private const val FOLDER_ALL = -1L
private const val FOLDER_NONE = 0L

@Composable
fun NotesScreen(nav: Nav) {
    val repo = App.instance.repo
    val notes = useData { repo.notes() }
    val folders = useData { repo.folders() }
    var folder by remember { mutableStateOf(repo.pref("notes_folder", "-1")!!.toLongOrNull() ?: FOLDER_ALL) }
    var query by remember { mutableStateOf("") }
    var newFolder by remember { mutableStateOf(false) }
    var folderMenu by remember { mutableStateOf<Long?>(null) }
    var renameFolder by remember { mutableStateOf<Long?>(null) }
    val t = tok
    val openId = nav.noteId
    if (openId != null) { NoteEditor(openId, folders) { nav.noteId = null }; return }
    if (folder > 0 && folders.none { it.id == folder }) folder = FOLDER_ALL

    val shown = notes.filter { when (folder) { FOLDER_ALL -> true; FOLDER_NONE -> it.folderId == null; else -> it.folderId == folder } }
        .filter { query.isBlank() || it.title.contains(query, true) || it.body.contains(query, true) }
        .sortedWith(compareBy<Note>({ !it.pinned }).thenByDescending { it.updatedAt })
    Box(Modifier.fillMaxSize()) {
        LazyColumn(Modifier.fillMaxSize()) {
            item {
                Column(Modifier.padding(horizontal = 16.dp)) {
                    BackTitle("Заметки", { nav.more = null })
                    OutlinedTextField(query, { query = it }, placeholder = { Text("Поиск по заметкам") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                    Spacer(Modifier.height(8.dp))
                }
                Row(Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(6.dp),
                    verticalAlignment = Alignment.CenterVertically) {
                    Chip("Все ${notes.size}", folder == FOLDER_ALL) { folder = FOLDER_ALL; repo.setPref("notes_folder", "-1") }
                    folders.forEach { f ->
                        Box {
                            Chip("${f.name} ${notes.count { it.folderId == f.id }}", folder == f.id) {
                                if (folder == f.id) folderMenu = f.id else { folder = f.id; repo.setPref("notes_folder", f.id.toString()) }
                            }
                            DropdownMenu(folderMenu == f.id, { folderMenu = null }) {
                                DropdownMenuItem(text = { Text("Переименовать") }, onClick = { folderMenu = null; renameFolder = f.id })
                                DropdownMenuItem(text = { Text("Удалить папку", color = t.danger) }, onClick = { folderMenu = null; repo.deleteFolder(f.id) })
                            }
                        }
                    }
                    if (folders.isNotEmpty()) Chip("Без папки", folder == FOLDER_NONE) { folder = FOLDER_NONE; repo.setPref("notes_folder", "0") }
                    TextButton(onClick = { newFolder = true }) { Icon(Icons.Outlined.Folder, null); Spacer(Modifier.width(4.dp)); Text("Папка") }
                }
                if (folder > 0) Caption("Нажмите на папку ещё раз, чтобы переименовать или удалить", modifier = Modifier.padding(horizontal = 16.dp))
                Spacer(Modifier.height(6.dp))
            }
            if (shown.isEmpty()) item { Box(Modifier.padding(horizontal = 16.dp)) { EmptyText(if (query.isNotBlank()) "Ничего не найдено." else "Здесь пока нет заметок. Нажмите «+».") } }
            items(shown, key = { it.id }) { n ->
                Column(Modifier.fillMaxWidth().clickable { nav.noteId = n.id }.padding(horizontal = 16.dp, vertical = 10.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(n.displayTitle, fontWeight = FontWeight.SemiBold, color = t.text, modifier = Modifier.weight(1f), maxLines = 1, overflow = TextOverflow.Ellipsis)
                        if (n.pinned) Icon(Icons.Outlined.PushPin, "Закреплена", tint = t.accent)
                    }
                    val lines = n.body.lines().filter { it.isNotBlank() }.let { if (n.title.isBlank()) it.drop(1) else it }
                    Caption(n.updatedAt.replace("T", " ").take(16) + " · " + (lines.firstOrNull() ?: "Нет текста"), maxLines = 1)
                }
                HorizontalDivider(color = t.border, modifier = Modifier.padding(horizontal = 16.dp))
            }
            item { Spacer(Modifier.height(88.dp)) }
        }
        FloatingActionButton(onClick = { nav.noteId = repo.addNote(if (folder > 0) folder else null) }, containerColor = t.teal,
            contentColor = t.tealText, modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp)) { Icon(Icons.Filled.Add, "Новая заметка") }
    }
    if (newFolder) TextInputDialog("Новая папка", "", "Название папки", "Создать", { folder = repo.addFolder(it); repo.setPref("notes_folder", folder.toString()) }, { newFolder = false })
    renameFolder?.let { fid -> TextInputDialog("Переименовать папку", folders.first { it.id == fid }.name, "Название папки",
        onConfirm = { repo.renameFolder(fid, it) }, onDismiss = { renameFolder = null }) }
}

@Composable
internal fun NoteEditor(id: Long, folders: List<ru.habittracker.app.data.NoteFolder>, onBack: () -> Unit) {
    val repo = App.instance.repo
    val note = remember(id) { repo.note(id) }
    if (note == null) { onBack(); return }
    var title by remember(id) { mutableStateOf(note.title) }
    var body by remember(id) { mutableStateOf(note.body) }
    var pinned by remember(id) { mutableStateOf(note.pinned) }
    var folderId by remember(id) { mutableStateOf(note.folderId) }
    var menu by remember { mutableStateOf(false) }
    var delete by remember { mutableStateOf(false) }
    var deleted by remember { mutableStateOf(false) }
    val t = tok
    // автосохранение: через полсекунды после ввода и при выходе
    LaunchedEffect(title, body) {
        delay(600)
        if (!deleted && (title != note.title || body != note.body)) repo.updateNote(id, title.trim(), body)
    }
    DisposableEffect(id) {
        onDispose {
            val cur = repo.note(id)
            if (!deleted && cur != null && (cur.title != title.trim() || cur.body != body)) repo.updateNote(id, title.trim(), body)
            if (!deleted && cur != null && title.isBlank() && body.isBlank()) repo.deleteNote(id)   // пустую не храним
        }
    }
    val fieldColors = TextFieldDefaults.colors(focusedContainerColor = Color.Transparent, unfocusedContainerColor = Color.Transparent,
        focusedIndicatorColor = Color.Transparent, unfocusedIndicatorColor = Color.Transparent)
    Column(Modifier.fillMaxSize().imePadding()) {
        BackTitle("", onBack) {
            IconButton(onClick = { pinned = !pinned; repo.setNotePinned(id, pinned) }) {
                Icon(Icons.Outlined.PushPin, if (pinned) "Открепить" else "Закрепить", tint = if (pinned) t.accent else t.text2)
            }
            Box {
                IconButton(onClick = { menu = true }) { Icon(Icons.Outlined.MoreVert, "Действия с заметкой") }
                DropdownMenu(menu, { menu = false }) {
                    DropdownMenuItem(text = { Text("Без папки") }, onClick = { menu = false; folderId = null; repo.moveNote(id, null) })
                    folders.forEach { f -> DropdownMenuItem(text = { Text("В папку «${f.name}»") }, onClick = { menu = false; folderId = f.id; repo.moveNote(id, f.id) }) }
                    DropdownMenuItem(text = { Text("Удалить", color = t.danger) }, onClick = { menu = false; delete = true })
                }
            }
        }
        Caption("Папка: " + (folders.firstOrNull { it.id == folderId }?.name ?: "без папки"), modifier = Modifier.padding(horizontal = 16.dp))
        TextField(title, { title = it }, placeholder = { Text("Название") }, singleLine = true, colors = fieldColors,
            textStyle = TextStyle(fontSize = 22.sp, fontWeight = FontWeight.SemiBold, color = t.text), modifier = Modifier.fillMaxWidth())
        TextField(body, { body = it }, placeholder = { Text("Текст заметки… Сохраняется автоматически.") }, colors = fieldColors,
            textStyle = TextStyle(fontSize = 17.sp, color = t.text), modifier = Modifier.fillMaxWidth().weight(1f))
    }
    if (delete) ConfirmDialog("Удалить заметку", "Удалить заметку «${note.displayTitle}»? Это нельзя отменить.", "Удалить",
        { deleted = true; repo.deleteNote(id); onBack() }, { delete = false })
}

// ======================================================================== настройки

@Composable
fun SettingsScreen(nav: Nav) {
    val s = App.instance.sync
    val t = tok
    val uri = LocalUriHandler.current
    var login by remember { mutableStateOf(s.login) }
    var password by remember { mutableStateOf("") }
    var device by remember { mutableStateOf(s.deviceName) }
    var editing by remember { mutableStateOf(!s.enabled) }
    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 16.dp).imePadding(),
        verticalArrangement = Arrangement.spacedBy(12.dp)) {
        BackTitle("Настройки", { nav.more = null })
        Card("Синхронизация с компьютером") {
            if (s.enabled && !editing) {
                Secondary("Данные синхронизируются через Яндекс Диск (${s.login}) с программой на компьютере. " +
                    "Автоматически: при открытии и сворачивании приложения, после изменений и раз в час.")
                Text(if (s.busy) "Синхронизация…" else s.status.ifEmpty { "Ещё не синхронизировалось." },
                    color = if (s.ok) t.text else t.danger)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(onClick = { s.runNow() }, enabled = !s.busy, colors = ButtonDefaults.buttonColors(containerColor = t.teal)) {
                        Icon(Icons.Outlined.Sync, null); Spacer(Modifier.width(6.dp)); Text("Синхронизировать")
                    }
                    OutlinedButton(onClick = { editing = true }) { Text("Изменить") }
                }
                TextButton(onClick = { s.disable(); editing = true }) { Text("Отключить синхронизацию") }
            } else {
                Secondary("Подключите тот же Яндекс Диск, что и в программе на компьютере (Настройки → Синхронизация с телефоном).")
                Secondary("Нужен пароль приложения, а не обычный пароль: Яндекс ID → Безопасность → Пароли приложений → «Файлы».")
                TextButton(onClick = { uri.openUri("https://id.yandex.ru/security/app-passwords") }) { Text("Открыть «Пароли приложений»") }
                OutlinedTextField(login, { login = it }, label = { Text("Логин Яндекса") }, singleLine = true, modifier = Modifier.fillMaxWidth(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email))
                OutlinedTextField(password, { password = it }, label = { Text(if (s.enabled) "Пароль приложения (не менять — оставьте пустым)" else "Пароль приложения") },
                    singleLine = true, visualTransformation = PasswordVisualTransformation(), modifier = Modifier.fillMaxWidth())
                OutlinedTextField(device, { device = it }, label = { Text("Имя устройства") }, singleLine = true, modifier = Modifier.fillMaxWidth())
                Button(enabled = login.isNotBlank() && (password.isNotBlank() || s.enabled), onClick = {
                    s.configure(login, password.ifBlank { null }, device); editing = false; password = ""; s.runNow()
                }, colors = ButtonDefaults.buttonColors(containerColor = t.teal)) { Text("Подключить") }
            }
        }
        AppearanceCard()
        Card("Где хранятся данные") {
            Secondary("Все данные лежат только на телефоне, в личной папке приложения. Если включена синхронизация — ещё и на вашем Яндекс Диске, в папке «HabitTracker-sync».")
            Caption("Трекер для Android, версия 1.3.0")
        }
        Spacer(Modifier.height(24.dp))
    }
}

// ---------------------------------------------------------------- оформление

@Composable
private fun AppearanceCard() {
    val t = tok
    Card("Оформление") {
        Secondary("Основной цвет — кнопки, ссылки, выбранная вкладка.")
        Swatches(PRIMARY_PRESETS, Appearance.primary ?: PRIMARY_PRESETS[0].first, "Основной цвет") {
            Appearance.update(primary = if (it == PRIMARY_PRESETS[0].first) null else it)
        }
        Secondary("Цвет отметок и прогресса.")
        Swatches(ACCENT_PRESETS, Appearance.accent ?: ACCENT_PRESETS[0].first, "Цвет прогресса") {
            Appearance.update(accent = if (it == ACCENT_PRESETS[0].first) null else it)
        }
        Secondary("Тема")
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            listOf("system" to "Как в системе", "light" to "Светлая", "dark" to "Тёмная").forEach { (k, n) ->
                Chip(n, Appearance.mode == k) { Appearance.update(mode = k) }
            }
        }
        if (Appearance.primary != null || Appearance.accent != null || Appearance.mode != "system")
            TextButton(onClick = { Appearance.reset() }) { Text("Вернуть как было") }
        Caption("Цвета подстраиваются, чтобы текст читался и в тёмной теме. На компьютере оформление настраивается отдельно.")
    }
}

@Composable
private fun Swatches(presets: List<Pair<String, String>>, current: String, what: String, onPick: (String) -> Unit) {
    val t = tok
    Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        presets.forEach { (c, name) ->
            val sel = c.equals(current, true)
            Box(Modifier.size(40.dp).clip(androidx.compose.foundation.shape.CircleShape).background(hex(c))
                .border(if (sel) 3.dp else 0.dp, t.text, androidx.compose.foundation.shape.CircleShape)
                .clickable(onClickLabel = "$what: $name") { onPick(c) },
                contentAlignment = Alignment.Center) {
                if (sel) Icon(androidx.compose.material.icons.Icons.Filled.Check, "$what: $name, выбран", tint = Color.White)
            }
        }
    }
}
