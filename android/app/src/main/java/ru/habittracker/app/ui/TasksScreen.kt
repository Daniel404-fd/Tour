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
import ru.habittracker.app.data.TOPIC_COLORS
import ru.habittracker.app.data.Task
import ru.habittracker.app.data.Topic
import ru.habittracker.app.pickDate
import ru.habittracker.app.useData
import java.time.LocalDate

private val STATUSES = listOf("active" to "Активные", "done" to "Выполненные", "all" to "Все", "archived" to "Архив")
private const val TOPIC_ALL = -1L
private const val TOPIC_NONE = 0L

@Composable
fun TasksScreen(nav: Nav) {
    val repo = App.instance.repo
    var status by remember { mutableStateOf("active") }
    var topic by remember { mutableStateOf(TOPIC_ALL) }
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

    val shown = Logic.sortTasks(all.filter {
        when (status) { "archived" -> it.archived; "active" -> !it.archived && !it.done; "done" -> !it.archived && it.done; else -> !it.archived }
    }.filter { when (topic) { TOPIC_ALL -> true; TOPIC_NONE -> it.topicId == null; else -> it.topicId == topic } })

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
                if (topics.isNotEmpty()) Row(Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 16.dp),
                    horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Chip("Все темы", topic == TOPIC_ALL) { topic = TOPIC_ALL }
                    topics.forEach { tp -> Chip(tp.name, topic == tp.id, dot = hex(tp.color)) { topic = tp.id } }
                    Chip("Без темы", topic == TOPIC_NONE) { topic = TOPIC_NONE }
                }
                Spacer(Modifier.height(8.dp))
            }
            if (shown.isEmpty()) item {
                Box(Modifier.padding(horizontal = 16.dp)) {
                    EmptyText(if (all.isEmpty()) "Задач пока нет. Нажмите «+»." else if (status == "active") "Здесь нет активных задач — всё сделано." else "По выбранным фильтрам ничего нет.")
                }
            }
            items(shown, key = { it.id }) { task ->
                TaskRow(task, byId[task.topicId], today, onOpen = { editing = task })
                HorizontalDivider(color = t.border, modifier = Modifier.padding(start = 60.dp))
            }
            item { Spacer(Modifier.height(88.dp)) }
        }
        FloatingActionButton(onClick = { editing = Task(title = "", topicId = if (topic > 0) topic else null) },
            containerColor = t.teal, contentColor = t.tealText, modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp)) {
            Icon(Icons.Filled.Add, "Новая задача")
        }
    }
    editing?.let { TaskEditor(it, topics) { editing = null } }
    if (topicsDialog) TopicsDialog(topics) { topicsDialog = false }
}

@Composable
private fun TaskRow(task: Task, topic: Topic?, today: LocalDate, onOpen: () -> Unit) {
    val repo = App.instance.repo
    val t = tok
    val overdue = Logic.isOverdue(task, today)
    val dueToday = Logic.isDueToday(task, today)
    Row(Modifier.fillMaxWidth().background(if (overdue) t.dangerSoft else if (dueToday) t.warnSoft else t.bg)
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
                if (topics.isNotEmpty()) {
                    Caption("Тема")
                    Row(Modifier.horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        Chip("Без темы", topicId == null) { topicId = null }
                        topics.forEach { tp -> Chip(tp.name, topicId == tp.id, dot = hex(tp.color)) { topicId = tp.id } }
                    }
                }
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
                if (task.id == 0L) repo.addTask(upd) else repo.updateTask(upd)
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
