package ru.habittracker.app.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
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
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.automirrored.filled.Undo
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.SnackbarDuration
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.SnackbarResult
import androidx.compose.material3.SwipeToDismissBox
import androidx.compose.material3.SwipeToDismissBoxValue
import androidx.compose.material3.rememberSwipeToDismissBoxState
import androidx.compose.runtime.rememberCoroutineScope
import kotlinx.coroutines.launch
import ru.habittracker.app.data.Quick
import ru.habittracker.app.data.QuickTask
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.KeyboardArrowUp
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material.icons.automirrored.outlined.Label
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Checkbox
import androidx.compose.material3.CheckboxDefaults
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import ru.habittracker.app.App
import ru.habittracker.app.ConfirmDialog
import ru.habittracker.app.Nav
import ru.habittracker.app.data.Logic
import ru.habittracker.app.data.PRIORITY_HIGH
import ru.habittracker.app.data.PRIORITY_NAMES
import ru.habittracker.app.data.Subtask
import ru.habittracker.app.data.SubtaskDraft
import ru.habittracker.app.data.TOPIC_COLORS
import ru.habittracker.app.data.Task
import ru.habittracker.app.data.Topic
import ru.habittracker.app.pickDate
import ru.habittracker.app.useData
import java.time.LocalDate

private val STATUSES = listOf("active" to "Активные", "done" to "Выполненные", "all" to "Все", "archived" to "Архив")
private const val TOPIC_ALL = -1L
private const val TOPIC_NONE = 0L
/** Больше тем — вместо ряда кнопок выпадающий список (иначе ряд приходится долго листать). */
const val TOPIC_CHIP_LIMIT = 15

@Composable
fun TasksScreen(nav: Nav) {
    val repo = App.instance.repo
    var status by remember { mutableStateOf("active") }
    var topic by remember { mutableStateOf(repo.pref("tasks_topic", "-1")!!.toLongOrNull() ?: TOPIC_ALL) }
    fun pickTopic(v: Long) { topic = v; repo.setPref("tasks_topic", v.toString()) }
    var expanded by remember { mutableStateOf(setOf<Long>()) }
    val subs = useData { repo.allSubtasks() }
    val snackbar = remember { SnackbarHostState() }
    val scope = rememberCoroutineScope()
    var editing by remember { mutableStateOf<Task?>(null) }
    var topicsDialog by remember { mutableStateOf(false) }
    val all = useData { repo.tasks() }
    val topics = useData { repo.topics() }
    val byId = topics.associateBy { it.id }
    val today = LocalDate.now()
    val t = tok

    LaunchedEffect(nav.taskId) {
        nav.taskId?.let { id -> repo.task(id)?.let { editing = it } }
        nav.taskId = null
    }

    if (topic > 0 && topics.none { it.id == topic }) topic = TOPIC_ALL
    val byStatus = all.filter {
        when (status) { "archived" -> it.archived; "active" -> !it.archived && !it.done; "done" -> !it.archived && it.done; else -> !it.archived }
    }
    val counts = byStatus.groupingBy { it.topicId ?: TOPIC_NONE }.eachCount()
    val shown = Logic.sortTasks(byStatus.filter { when (topic) { TOPIC_ALL -> true; TOPIC_NONE -> it.topicId == null; else -> it.topicId == topic } })

    Box(Modifier.fillMaxSize()) {
        LazyColumn(Modifier.fillMaxSize()) {
            item {
                Column(Modifier.padding(horizontal = 16.dp)) {
                    Spacer(Modifier.height(12.dp))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text("Задачи", style = Header, color = t.text, modifier = Modifier.weight(1f))
                        IconButton(onClick = { topicsDialog = true }) { Icon(Icons.AutoMirrored.Outlined.Label, "Темы") }
                    }
                    val active = all.count { !it.done && !it.archived }
                    val overdue = all.count { Logic.isOverdue(it, today) }
                    Secondary("$active ${Logic.plural(active, "активная", "активные", "активных")}" +
                        if (overdue > 0) " · $overdue ${Logic.plural(overdue, "просрочена", "просрочены", "просрочено")}" else "")
                    Spacer(Modifier.height(8.dp))
                }
                Row(Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 16.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    STATUSES.forEach { (k, n) -> Chip(n, status == k) { status = k } }
                }
                Spacer(Modifier.height(6.dp))
                if (topics.size > TOPIC_CHIP_LIMIT) Box(Modifier.padding(horizontal = 16.dp)) {
                    TopicDropdown(topics, topic, counts, byStatus.size) { pickTopic(it) }
                } else if (topics.isNotEmpty()) Row(Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 16.dp),
                    horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Chip("Все темы", topic == TOPIC_ALL) { pickTopic(TOPIC_ALL) }
                    topics.forEach { tp -> Chip(tp.name + (counts[tp.id]?.let { " $it" } ?: ""), topic == tp.id, dot = hex(tp.color)) { pickTopic(tp.id) } }
                    Chip("Без темы", topic == TOPIC_NONE) { pickTopic(TOPIC_NONE) }
                }
                Spacer(Modifier.height(8.dp))
                QuickAdd(topics, if (topic > 0) topic else null) { q ->
                    val id = repo.addTask(Task(title = q.title, deadline = q.deadline, priority = q.priority, topicId = q.topicId))
                    if (status != "active" && status != "all") status = "active"
                    if (topic != TOPIC_ALL && topic != (q.topicId ?: TOPIC_NONE)) pickTopic(TOPIC_ALL)
                    scope.launch { snackbar.showSnackbar("Добавлено: ${q.title}", duration = SnackbarDuration.Short) }
                    id
                }
                Spacer(Modifier.height(4.dp))
            }
            if (shown.isEmpty()) item {
                Box(Modifier.padding(horizontal = 16.dp)) {
                    EmptyText(if (all.isEmpty()) "Задач пока нет. Напишите задачу в строке выше или нажмите «+». Готовую задачу смахните вправо." else if (status == "active") "Здесь нет активных задач — всё сделано." else "По выбранным фильтрам ничего нет.")
                }
            }
            items(shown, key = { it.id }) { task ->
                Box(Modifier.animateItem()) {    // строки плавно уезжают и появляются, а не «прыгают»
                SwipeToComplete(task, onToggle = {
                    val nowDone = !task.done
                    repo.updateTask(task.copy(done = nowDone, completedOn = null))
                    scope.launch {
                        snackbar.currentSnackbarData?.dismiss()
                        val r = snackbar.showSnackbar(if (nowDone) "Выполнено: ${task.title}" else "Возвращено в работу: ${task.title}",
                            actionLabel = "Отменить", duration = SnackbarDuration.Short)
                        if (r == SnackbarResult.ActionPerformed) repo.task(task.id)?.let { repo.updateTask(it.copy(done = task.done, completedOn = task.completedOn)) }
                    }
                }) {
                TaskRow(task, byId[task.topicId], today, subs[task.id] ?: emptyList(), task.id in expanded,
                    onToggleExpand = { expanded = if (task.id in expanded) expanded - task.id else expanded + task.id },
                    onOpen = { editing = task })
                }
                }
                HorizontalDivider(color = t.border, modifier = Modifier.padding(start = 60.dp))
            }
            item { Spacer(Modifier.height(88.dp)) }
        }
        SnackbarHost(snackbar, Modifier.align(Alignment.BottomCenter).padding(bottom = 80.dp))
        FloatingActionButton(onClick = { editing = Task(title = "", topicId = if (topic > 0) topic else null) },
            containerColor = t.teal, contentColor = t.tealText, modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp)) {
            Icon(Icons.Filled.Add, "Новая задача")
        }
    }
    editing?.let { TaskEditor(it, topics) { editing = null } }
    if (topicsDialog) TopicsDialog(topics) { topicsDialog = false }
}

/** Строка быстрого добавления: «Купить молоко завтра #дом !» — срок, тема и приоритет распознаются. */
@Composable
private fun QuickAdd(topics: List<Topic>, defaultTopic: Long?, onAdd: (QuickTask) -> Long) {
    val t = tok
    var text by remember { mutableStateOf("") }
    val q = Quick.parse(text, topics, LocalDate.now(), defaultTopic)
    fun submit() { if (q.title.isNotBlank()) { onAdd(q); text = "" } }
    Column(Modifier.padding(horizontal = 16.dp)) {
        OutlinedTextField(text, { text = it }, modifier = Modifier.fillMaxWidth(), singleLine = true,
            placeholder = { Text("Быстро: «Купить молоко завтра #дом !»") },
            trailingIcon = { if (q.title.isNotBlank()) IconButton(onClick = { submit() }) { Icon(Icons.Filled.Add, "Добавить задачу", tint = t.link) } },
            keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(imeAction = androidx.compose.ui.text.input.ImeAction.Done),
            keyboardActions = androidx.compose.foundation.text.KeyboardActions(onDone = { submit() }))
        if (text.isNotBlank()) Caption(if (q.hints.isEmpty()) "Срок: завтра, «в пятницу», 12.11 · тема: #название · «!» — важно"
            else q.hints.joinToString(" · "), modifier = Modifier.padding(start = 4.dp, top = 2.dp))
    }
}

/** Смахните задачу вправо — выполнено (или обратно в работу), с отменой в подсказке внизу. */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun SwipeToComplete(task: Task, onToggle: () -> Unit, content: @Composable () -> Unit) {
    val t = tok
    val toggle by androidx.compose.runtime.rememberUpdatedState(onToggle)   // задача могла измениться с момента создания строки
    val last = remember { longArrayOf(0L) }
    val state = rememberSwipeToDismissBoxState(confirmValueChange = { v ->
        val now = System.currentTimeMillis()
        if (v == SwipeToDismissBoxValue.StartToEnd && now - last[0] > 600) { last[0] = now; toggle() }
        false     // строка возвращается на место — список сам обновится
    }, positionalThreshold = { it * 0.35f })
    SwipeToDismissBox(state, enableDismissFromEndToStart = false, backgroundContent = {
        Row(Modifier.fillMaxSize().background(if (task.done) t.warnSoft else t.accent).padding(horizontal = 20.dp),
            verticalAlignment = Alignment.CenterVertically) {
            Icon(if (task.done) Icons.AutoMirrored.Filled.Undo else Icons.Filled.Check, null,
                tint = if (task.done) t.warn else t.accentText)
            Spacer(Modifier.width(10.dp))
            Text(if (task.done) "Вернуть в работу" else "Выполнено", color = if (task.done) t.warn else t.accentText,
                fontWeight = FontWeight.SemiBold)
        }
    }) { content() }
}

/** Выпадающий фильтр тем: с количеством задач в каждой. */
@Composable
fun TopicDropdown(topics: List<Topic>, selected: Long, counts: Map<Long, Int>, total: Int, onPick: (Long) -> Unit) {
    val t = tok
    var open by remember { mutableStateOf(false) }
    val cur = topics.firstOrNull { it.id == selected }
    Box {
        Row(Modifier.clip(RoundedCornerShape(16.dp)).background(if (selected != TOPIC_ALL) t.tealSoft else t.surface)
            .border(1.dp, if (selected != TOPIC_ALL) t.teal else t.borderStrong, RoundedCornerShape(16.dp))
            .clickable { open = true }.padding(horizontal = 12.dp, vertical = 7.dp), verticalAlignment = Alignment.CenterVertically) {
            if (cur != null) { Dot(hex(cur.color)); Spacer(Modifier.width(6.dp)) }
            Text("Тема: " + when (selected) { TOPIC_ALL -> "все"; TOPIC_NONE -> "без темы"; else -> cur?.name ?: "все" },
                color = if (selected != TOPIC_ALL) t.tealOnSoft else t.text, fontSize = 14.sp)
            Icon(Icons.Filled.KeyboardArrowDown, null, tint = t.text2)
        }
        DropdownMenu(open, { open = false }) {
            DropdownMenuItem(text = { Text("Все темы · $total") }, onClick = { open = false; onPick(TOPIC_ALL) })
            topics.forEach { tp ->
                DropdownMenuItem(text = { Text("${tp.name} · ${counts[tp.id] ?: 0}") }, leadingIcon = { Dot(hex(tp.color), 10.dp) },
                    onClick = { open = false; onPick(tp.id) })
            }
            DropdownMenuItem(text = { Text("Без темы · ${counts[TOPIC_NONE] ?: 0}") }, onClick = { open = false; onPick(TOPIC_NONE) })
        }
    }
}

@Composable
private fun TaskRow(task: Task, topic: Topic?, today: LocalDate, subs: List<Subtask>, expanded: Boolean,
                    onToggleExpand: () -> Unit, onOpen: () -> Unit) {
    val repo = App.instance.repo
    val t = tok
    val overdue = Logic.isOverdue(task, today)
    val dueToday = Logic.isDueToday(task, today)
    Column(Modifier.fillMaxWidth().background(if (overdue) t.dangerSoft else if (dueToday) t.warnSoft else t.bg)) {
    Row(Modifier.fillMaxWidth()
        .clickable(onClick = onOpen).padding(horizontal = 6.dp, vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
        Checkbox(task.done, { repo.updateTask(task.copy(done = it, completedOn = null)) },
            colors = CheckboxDefaults.colors(checkedColor = t.accent, checkmarkColor = t.accentText))
        Column(Modifier.weight(1f).padding(end = 10.dp)) {
            Text(task.title, color = if (task.done) t.text2 else t.text, textDecoration = if (task.done) TextDecoration.LineThrough else null,
                fontWeight = if (task.priority == PRIORITY_HIGH && !task.done) FontWeight.SemiBold else FontWeight.Normal)
            Row(verticalAlignment = Alignment.CenterVertically) {
                if (topic != null) { Dot(hex(topic.color), 7.dp); Spacer(Modifier.width(4.dp)); Caption(topic.name); Spacer(Modifier.width(10.dp)) }
                task.deadline?.let { d ->
                    val txt = d.format(java.time.format.DateTimeFormatter.ofPattern("dd.MM")) + if (!task.done && !task.archived) " · ${Logic.dueText(d, today)}" else ""
                    Caption(txt, color = when { overdue -> t.danger; dueToday -> t.warn; else -> t.text2 })
                }
            }
        }
        if (subs.isNotEmpty()) {
            val done = subs.count { it.done }
            Row(Modifier.clip(RoundedCornerShape(12.dp)).clickable(onClick = onToggleExpand).padding(horizontal = 8.dp, vertical = 6.dp),
                verticalAlignment = Alignment.CenterVertically) {
                Text("$done/${subs.size}", fontSize = 14.sp, color = if (done == subs.size) t.accent else t.text2, fontWeight = FontWeight.Medium)
                Icon(if (expanded) Icons.Filled.KeyboardArrowUp else Icons.Filled.KeyboardArrowDown,
                    if (expanded) "Скрыть подзадачи" else "Показать подзадачи", tint = t.text2)
            }
        }
    }
    if (expanded) subs.forEach { st ->
        Row(Modifier.fillMaxWidth().clickable { repo.setSubtaskDone(st.id, !st.done) }.padding(start = 44.dp, end = 12.dp),
            verticalAlignment = Alignment.CenterVertically) {
            Checkbox(st.done, { repo.setSubtaskDone(st.id, it) },
                colors = CheckboxDefaults.colors(checkedColor = t.accent, checkmarkColor = t.accentText))
            Text(st.title, color = if (st.done) t.text2 else t.text, fontSize = 15.sp,
                textDecoration = if (st.done) TextDecoration.LineThrough else null)
        }
    }
    }
}

/** Редактор подзадач в диалоге задачи: сохраняется вместе с задачей. */
@Composable
fun SubtaskEditor(items: List<SubtaskDraft>, onChange: (List<SubtaskDraft>) -> Unit) {
    val t = tok
    var newTitle by remember { mutableStateOf("") }
    Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Caption(if (items.isEmpty()) "Подзадачи — разбейте задачу на шаги" else "Подзадачи · ${items.count { it.done }} из ${items.size}")
        items.forEachIndexed { i, d ->
            Row(verticalAlignment = Alignment.CenterVertically) {
                Checkbox(d.done, { v -> onChange(items.toMutableList().also { it[i] = d.copy(done = v) }) },
                    colors = CheckboxDefaults.colors(checkedColor = t.accent, checkmarkColor = t.accentText))
                Text(d.title, Modifier.weight(1f), color = if (d.done) t.text2 else t.text,
                    textDecoration = if (d.done) TextDecoration.LineThrough else null)
                IconButton(onClick = { onChange(items.filterIndexed { k, _ -> k != i }) }) {
                    Icon(Icons.Filled.Close, "Удалить подзадачу «${d.title}»", tint = t.text2)
                }
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            OutlinedTextField(newTitle, { newTitle = it }, placeholder = { Text("Новая подзадача") }, singleLine = true,
                modifier = Modifier.weight(1f),
                keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(imeAction = androidx.compose.ui.text.input.ImeAction.Done),
                keyboardActions = androidx.compose.foundation.text.KeyboardActions(onDone = {
                    if (newTitle.isNotBlank()) { onChange(items + SubtaskDraft(0, newTitle.trim(), false)); newTitle = "" }
                }))
            IconButton(enabled = newTitle.isNotBlank(), onClick = {
                onChange(items + SubtaskDraft(0, newTitle.trim(), false)); newTitle = ""
            }) { Icon(Icons.Filled.Add, "Добавить подзадачу") }
        }
    }
}

@Composable
fun TaskEditor(task: Task, topics: List<Topic>, onClose: () -> Unit) {
    val repo = App.instance.repo
    val ctx = LocalContext.current
    var title by remember { mutableStateOf(task.title) }
    var desc by remember { mutableStateOf(task.description) }
    var deadline by remember { mutableStateOf(task.deadline) }
    var priority by remember { mutableStateOf(task.priority) }
    var topicId by remember { mutableStateOf(task.topicId) }
    var done by remember { mutableStateOf(task.done) }
    var confirmDelete by remember { mutableStateOf(false) }
    var drafts by remember { mutableStateOf(repo.subtasks(task.id).map { SubtaskDraft(it.id, it.title, it.done) }) }
    val t = tok
    AlertDialog(onDismissRequest = onClose, title = { Text(if (task.id == 0L) "Новая задача" else "Задача") },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedTextField(title, { title = it }, label = { Text("Что нужно сделать") }, modifier = Modifier.fillMaxWidth())
                OutlinedTextField(desc, { desc = it }, label = { Text("Описание") }, modifier = Modifier.fillMaxWidth(), minLines = 2)
                Caption("Срок")
                Row(verticalAlignment = Alignment.CenterVertically) {
                    OutlinedButton(onClick = { pickDate(ctx, deadline ?: LocalDate.now()) { deadline = it } }) {
                        Text(deadline?.let { Logic.humanDate(it) } ?: "Без срока")
                    }
                    if (deadline != null) TextButton(onClick = { deadline = null }) { Text("Убрать") }
                }
                Caption("Приоритет")
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    PRIORITY_NAMES.forEach { (k, n) -> Chip(n, priority == k) { priority = k } }
                }
                if (topics.size > TOPIC_CHIP_LIMIT) {
                    Caption("Тема")
                    var open by remember { mutableStateOf(false) }
                    Box {
                        val cur = topics.firstOrNull { it.id == topicId }
                        OutlinedButton(onClick = { open = true }) {
                            if (cur != null) { Dot(hex(cur.color)); Spacer(Modifier.width(6.dp)) }
                            Text(cur?.name ?: "Без темы"); Icon(Icons.Filled.KeyboardArrowDown, null)
                        }
                        DropdownMenu(open, { open = false }) {
                            DropdownMenuItem(text = { Text("Без темы") }, onClick = { topicId = null; open = false })
                            topics.forEach { tp -> DropdownMenuItem(text = { Text(tp.name) }, leadingIcon = { Dot(hex(tp.color), 10.dp) },
                                onClick = { topicId = tp.id; open = false }) }
                        }
                    }
                } else if (topics.isNotEmpty()) {
                    Caption("Тема")
                    Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        Chip("Без темы", topicId == null) { topicId = null }
                        topics.forEach { tp -> Chip(tp.name, topicId == tp.id, dot = hex(tp.color)) { topicId = tp.id } }
                    }
                }
                SubtaskEditor(drafts) { drafts = it }
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Checkbox(done, { done = it }, colors = CheckboxDefaults.colors(checkedColor = t.accent)); Text("Выполнена")
                }
                if (task.id != 0L) Row {
                    TextButton(onClick = { repo.updateTask(task.copy(archived = !task.archived)); onClose() }) {
                        Text(if (task.archived) "Вернуть из архива" else "В архив")
                    }
                    TextButton(onClick = { confirmDelete = true }) { Text("Удалить", color = t.danger) }
                }
            }
        },
        confirmButton = {
            TextButton(enabled = title.isNotBlank(), onClick = {
                val upd = task.copy(title = title.trim(), description = desc.trim(), deadline = deadline, priority = priority,
                    topicId = topicId, done = done, completedOn = if (done && task.done) task.completedOn else null)
                val id = if (task.id == 0L) repo.addTask(upd) else { repo.updateTask(upd); task.id }
                repo.applySubtasks(id, drafts)
                if (task.boardId != null && done != task.done) repo.completeTask(id, done)   // карточка — в «Готово» или обратно
                onClose()
            }) { Text("Сохранить") }
        },
        dismissButton = { TextButton(onClick = onClose) { Text("Отмена") } })
    if (confirmDelete) ConfirmDialog("Удалить задачу", "Удалить «${task.title}» навсегда? Это нельзя отменить.", "Удалить",
        { repo.deleteTask(task.id); onClose() }, { confirmDelete = false })
}

@Composable
private fun TopicsDialog(topics: List<Topic>, onClose: () -> Unit) {
    val repo = App.instance.repo
    var edit by remember { mutableStateOf<Topic?>(null) }
    var delete by remember { mutableStateOf<Topic?>(null) }
    val t = tok
    AlertDialog(onDismissRequest = onClose, title = { Text("Темы задач") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Caption("Темы помогают разделить задачи по сферам жизни: дом, работа, учёба…")
                topics.forEach { tp ->
                    Row(Modifier.fillMaxWidth().clickable { edit = tp }.padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                        Dot(hex(tp.color), 12.dp); Spacer(Modifier.width(10.dp))
                        Text(tp.name, Modifier.weight(1f))
                        TextButton(onClick = { delete = tp }) { Text("Удалить", color = t.danger) }
                    }
                }
                TextButton(onClick = { edit = Topic(0, "", TOPIC_COLORS[0]) }) { Text("+ Новая тема") }
            }
        },
        confirmButton = { TextButton(onClick = onClose) { Text("Готово") } })
    edit?.let { tp -> TopicEditDialog(tp) { edit = null } }
    delete?.let { tp -> ConfirmDialog("Удалить тему", "Удалить тему «${tp.name}»? Задачи не удалятся — станут «без темы».", "Удалить",
        { repo.deleteTopic(tp.id) }, { delete = null }) }
}

@Composable
private fun TopicEditDialog(topic: Topic, onClose: () -> Unit) {
    val repo = App.instance.repo
    var name by remember { mutableStateOf(topic.name) }
    var color by remember { mutableStateOf(topic.color) }
    val t = tok
    AlertDialog(onDismissRequest = onClose, title = { Text(if (topic.id == 0L) "Новая тема" else "Тема") },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                OutlinedTextField(name, { name = it }, label = { Text("Название") }, singleLine = true)
                ColorRow(TOPIC_COLORS, color) { color = it }
            }
        },
        confirmButton = {
            TextButton(enabled = name.isNotBlank(), onClick = {
                if (topic.id == 0L) repo.addTopic(name.trim(), color) else repo.updateTopic(topic.copy(name = name.trim(), color = color))
                onClose()
            }) { Text("Сохранить") }
        }, dismissButton = { TextButton(onClick = onClose) { Text("Отмена") } })
}

@Composable
fun ColorRow(colors: List<String>, selected: String?, onPick: (String) -> Unit) {
    val t = tok
    Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        colors.forEach { c ->
            Box(Modifier.size(32.dp).clip(CircleShape).background(hex(c))
                .border(if (c.equals(selected, true)) 3.dp else 0.dp, t.text, CircleShape).clickable { onPick(c) })
        }
    }
}
