package ru.habittracker.app.ui

import androidx.compose.foundation.ExperimentalFoundationApi
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.pager.HorizontalPager
import androidx.compose.foundation.pager.rememberPagerState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.outlined.MoreVert
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.style.TextDecoration
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.launch
import ru.habittracker.app.App
import ru.habittracker.app.ConfirmDialog
import ru.habittracker.app.Nav
import ru.habittracker.app.TextInputDialog
import ru.habittracker.app.data.Board
import ru.habittracker.app.data.BoardColumn
import ru.habittracker.app.data.Logic
import ru.habittracker.app.data.PRIORITY_HIGH
import ru.habittracker.app.data.Quick
import ru.habittracker.app.data.Subtask
import ru.habittracker.app.data.Task
import ru.habittracker.app.data.Topic
import ru.habittracker.app.useData
import java.time.LocalDate

private val BOARD_COLORS = listOf("#0F6E6A", "#1D4ED8", "#7E22CE", "#BE185D", "#B45309", "#15803D", "#374151")

/** Доски — канбан для отдельных областей (например, двух работ): колонки листаются вбок,
 *  карточки перекладываются меню или долгим нажатием; у каждой доски свои заметки. */
@Composable
fun BoardsScreen(nav: Nav) {
    val repo = App.instance.repo
    val t = tok
    val boards = useData { repo.boards() }
    var current by remember { mutableStateOf(nav.boardId ?: repo.pref("board_current", "0")!!.toLongOrNull()) }
    if (boards.isNotEmpty() && boards.none { it.id == current }) current = boards[0].id
    val board = boards.firstOrNull { it.id == current }
    var showNotes by remember { mutableStateOf(false) }
    var newBoard by remember { mutableStateOf(false) }
    var renameBoard by remember { mutableStateOf(false) }
    var deleteBoard by remember { mutableStateOf(false) }
    var addColumn by remember { mutableStateOf(false) }
    var menu by remember { mutableStateOf(false) }
    var openNote by remember { mutableStateOf<Long?>(null) }
    fun pick(id: Long) { current = id; nav.boardId = id; repo.setPref("board_current", id.toString()) }

    if (openNote != null) { NoteEditor(openNote!!, emptyList()) { openNote = null }; return }

    Column(Modifier.fillMaxSize()) {
        Row(Modifier.fillMaxWidth().padding(start = 16.dp, end = 4.dp, top = 12.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("Доски", style = Header, color = t.text, modifier = Modifier.weight(1f))
            if (board != null) Box {
                IconButton(onClick = { menu = true }) { Icon(Icons.Outlined.MoreVert, "Действия с доской") }
                DropdownMenu(menu, { menu = false }) {
                    DropdownMenuItem(text = { Text("Новая доска") }, onClick = { menu = false; newBoard = true })
                    DropdownMenuItem(text = { Text("Переименовать") }, onClick = { menu = false; renameBoard = true })
                    DropdownMenuItem(text = { Text("Новая колонка") }, onClick = { menu = false; addColumn = true })
                    DropdownMenuItem(text = { Text("В архив") }, onClick = { menu = false; repo.updateBoard(board.copy(archived = true)) })
                    DropdownMenuItem(text = { Text("Удалить доску", color = t.danger) }, onClick = { menu = false; deleteBoard = true })
                }
            }
        }
        if (board == null) {
            Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
                Secondary("Доски — для отдельных областей: например, «Работа 1» и «Работа 2». У каждой свои колонки " +
                    "(К выполнению → В работе → Готово), карточки и заметки. В обычный список задач они не попадают.")
                Button(onClick = { newBoard = true }, colors = ButtonDefaults.buttonColors(containerColor = t.teal)) { Text("Создать доску") }
                OutlinedButton(onClick = {
                    val a = repo.addBoard("Работа 1", BOARD_COLORS[1]); repo.addBoard("Работа 2", BOARD_COLORS[2]); pick(a)
                }) { Text("Две доски для двух работ") }
            }
        } else {
            Row(Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 4.dp),
                horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                boards.forEach { b -> Chip(b.name, b.id == board.id, dot = hex(b.color)) { pick(b.id) } }
                IconButton(onClick = { newBoard = true }) { Icon(Icons.Filled.Add, "Новая доска", tint = t.link) }
            }
            Row(Modifier.padding(horizontal = 16.dp, vertical = 4.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                Chip("Карточки", !showNotes) { showNotes = false }
                Chip("Заметки доски", showNotes) { showNotes = true }
            }
            if (showNotes) BoardNotesList(board) { openNote = it }
            else Kanban(board, nav)
        }
    }
    if (newBoard) TextInputDialog("Новая доска", "", "Название (например, «Работа в N»)", "Создать",
        { pick(repo.addBoard(it, BOARD_COLORS[repo.boards(true).size % BOARD_COLORS.size])) }, { newBoard = false })
    if (renameBoard && board != null) TextInputDialog("Переименовать доску", board.name, "Название",
        onConfirm = { repo.updateBoard(board.copy(name = it)) }, onDismiss = { renameBoard = false })
    if (addColumn && board != null) TextInputDialog("Новая колонка", "", "Название (например, «На проверке»)", "Добавить",
        { repo.addColumn(board.id, it) }, { addColumn = false })
    if (deleteBoard && board != null) ConfirmDialog("Удалить доску",
        "Удалить «${board.name}» вместе с карточками и заметками? Это нельзя отменить. Чтобы просто убрать — отправьте в архив.",
        "Удалить", { repo.deleteBoard(board.id) }, { deleteBoard = false })
}

@Composable
private fun Kanban(board: Board, nav: Nav) {
    val repo = App.instance.repo
    val columns = useData { repo.columns(board.id) }
    val cards = useData { repo.boardTasks(board.id) }
    val subs = useData { repo.allSubtasks() }
    val topics = useData { repo.topics() }
    var editing by remember { mutableStateOf<Task?>(null) }
    if (columns.isEmpty()) return
    val pager = rememberPagerState { columns.size }
    val scope = rememberCoroutineScope()
    LaunchedEffect(nav.cardId) {
        nav.cardId?.let { id -> repo.task(id)?.let { editing = it; columns.indexOfFirst { c -> c.id == it.columnId }.takeIf { i -> i >= 0 }?.let { i -> pager.scrollToPage(i) } } }
        nav.cardId = null
    }
    val t = tok
    // переключатель колонок сверху: видно, где ты, и можно перейти одним касанием
    Row(Modifier.horizontalScroll(rememberScrollState()).padding(horizontal = 16.dp, vertical = 4.dp),
        horizontalArrangement = Arrangement.spacedBy(14.dp)) {
        columns.forEachIndexed { i, c ->
            val n = cards.count { it.columnId == c.id }
            Text("${c.name} $n", color = if (pager.currentPage == i) t.text else t.text3, fontSize = 14.sp,
                fontWeight = if (pager.currentPage == i) FontWeight.SemiBold else FontWeight.Normal,
                modifier = Modifier.clip(RoundedCornerShape(6.dp)).clickable { scope.launch { pager.animateScrollToPage(i) } }.padding(4.dp))
        }
    }
    HorizontalPager(pager, Modifier.fillMaxSize(), contentPadding = PaddingValues(start = 12.dp, end = 40.dp), pageSpacing = 10.dp) { page ->
        val col = columns[page]
        ColumnPane(board, col, columns, cards.filter { it.columnId == col.id || (it.columnId == null && page == 0) }
            .sortedWith(compareBy({ it.position }, { it.id })), subs, topics.associateBy { it.id }) { editing = it }
    }
    editing?.let { TaskEditor(it, topics) { editing = null } }
}

@OptIn(ExperimentalFoundationApi::class)
@Composable
private fun ColumnPane(board: Board, col: BoardColumn, columns: List<BoardColumn>, cards: List<Task>,
                       subs: Map<Long, List<Subtask>>, topics: Map<Long, Topic>, onOpen: (Task) -> Unit) {
    val repo = App.instance.repo
    val t = tok
    var text by remember { mutableStateOf("") }
    var colMenu by remember { mutableStateOf(false) }
    var rename by remember { mutableStateOf(false) }
    var moveFor by remember { mutableStateOf<Task?>(null) }
    val today = LocalDate.now()
    Column(Modifier.fillMaxSize().clip(RoundedCornerShape(14.dp)).background(t.surface2)
        .border(1.dp, t.border, RoundedCornerShape(14.dp)).padding(10.dp).imePadding()) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(col.name, fontWeight = FontWeight.SemiBold, color = t.text, fontSize = 16.sp)
            Spacer(Modifier.width(6.dp)); Caption("${cards.size}" + if (col.isDone) " · готово" else "")
            Spacer(Modifier.weight(1f))
            Box {
                IconButton(onClick = { colMenu = true }) { Icon(Icons.Outlined.MoreVert, "Действия с колонкой «${col.name}»", tint = t.text2) }
                DropdownMenu(colMenu, { colMenu = false }) {
                    DropdownMenuItem(text = { Text("Переименовать") }, onClick = { colMenu = false; rename = true })
                }
            }
        }
        LazyColumn(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            if (cards.isEmpty()) item { Caption("Пусто. Добавьте карточку ниже" + if (page(columns, col) > 0) " или переложите сюда." else ".", modifier = Modifier.padding(8.dp)) }
            items(cards, key = { it.id }) { card ->
                Column(Modifier.animateItem().fillMaxWidth().clip(RoundedCornerShape(10.dp)).background(t.surface)
                    .border(1.dp, t.border, RoundedCornerShape(10.dp))
                    .combinedClickable(onClick = { onOpen(card) }, onLongClick = { moveFor = card }, onLongClickLabel = "Переложить")
                    .padding(horizontal = 12.dp, vertical = 10.dp), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Text(card.title, color = if (card.done) t.text3 else t.text, fontSize = 15.sp,
                        fontWeight = if (card.priority == PRIORITY_HIGH && !card.done) FontWeight.SemiBold else FontWeight.Normal,
                        textDecoration = if (card.done) TextDecoration.LineThrough else null)
                    val meta = buildList {
                        if (card.priority == PRIORITY_HIGH && !card.done) add("● важно" to t.danger)
                        card.deadline?.let { d -> add("${d.dayOfMonth}.${"%02d".format(d.monthValue)} · ${Logic.dueText(d, today)}" to
                            when { card.done -> t.text3; d.isBefore(today) -> t.danger; d == today -> t.warn; else -> t.text2 }) }
                        subs[card.id]?.let { st -> add("☑ ${st.count { it.done }}/${st.size}" to t.text2) }
                        topics[card.topicId]?.let { add(it.name to t.text2) }
                        if (card.repeat != null) add("↻" to t.text2)
                        card.labelList.forEach { add("#$it" to hex(Logic.labelColor(it))) }
                    }
                    if (meta.isNotEmpty()) Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        meta.forEach { (s, c) -> Text(s, fontSize = 13.sp, color = c, maxLines = 1, overflow = TextOverflow.Ellipsis) }
                    }
                }
            }
        }
        fun add() {
            val q = Quick.parse(text, repo.topics(), LocalDate.now())
            if (q.title.isNotBlank()) {
                val id = repo.addCard(board.id, col.id, q.title, q.deadline, q.priority, q.topicId)
                if (q.repeat != null || q.labels.isNotEmpty()) repo.task(id)?.let { repo.updateTask(it.copy(repeat = q.repeat, labels = q.labels.joinToString(", "))) }
                text = ""
            }
        }
        OutlinedTextField(text, { text = it }, Modifier.fillMaxWidth().padding(top = 8.dp), singleLine = true,
            placeholder = { Text("Новая карточка: «Отчёт в пятницу !»") },
            trailingIcon = {
                IconButton(onClick = { add() }, enabled = text.isNotBlank()) {
                    Icon(Icons.Filled.Add, "Добавить карточку", tint = if (text.isNotBlank()) t.link else t.text3)
                }
            },
            keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
            keyboardActions = KeyboardActions(onDone = { add() }))
    }
    if (rename) TextInputDialog("Колонка", col.name, "Название", onConfirm = { repo.renameColumn(col.id, it) }, onDismiss = { rename = false })
    moveFor?.let { card ->
        androidx.compose.material3.AlertDialog(onDismissRequest = { moveFor = null }, title = { Text("Переложить «${card.title}»") },
            text = {
                Column {
                    columns.forEach { c ->
                        Row(Modifier.fillMaxWidth().clickable(enabled = c.id != col.id) { repo.moveCard(card.id, c.id, 0); moveFor = null }
                            .padding(vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                            Text(c.name + if (c.isDone) " (готово)" else "", color = if (c.id == col.id) t.text3 else t.text, fontSize = 16.sp)
                        }
                        HorizontalDivider(color = t.border)
                    }
                    Row(Modifier.fillMaxWidth().clickable { repo.updateTask(card.copy(boardId = null, columnId = null)); moveFor = null }
                        .padding(vertical = 12.dp)) { Text("В обычные задачи", color = t.link, fontSize = 16.sp) }
                }
            },
            confirmButton = { androidx.compose.material3.TextButton(onClick = { moveFor = null }) { Text("Отмена") } })
    }
}

private fun page(columns: List<BoardColumn>, col: BoardColumn) = columns.indexOfFirst { it.id == col.id }

@Composable
private fun BoardNotesList(board: Board, onOpen: (Long) -> Unit) {
    val repo = App.instance.repo
    val t = tok
    val notes = useData { repo.boardNotes(board.id).sortedWith(compareBy<ru.habittracker.app.data.Note>({ !it.pinned }).thenByDescending { it.updatedAt }) }
    Box(Modifier.fillMaxSize()) {
        LazyColumn(Modifier.fillMaxSize()) {
            if (notes.isEmpty()) item {
                Box(Modifier.padding(horizontal = 16.dp)) { EmptyText("Заметки только этой доски: договорённости, контакты, идеи по работе. Нажмите «+».") }
            }
            items(notes, key = { it.id }) { n ->
                Column(Modifier.animateItem().fillMaxWidth().clickable { onOpen(n.id) }.padding(horizontal = 16.dp, vertical = 12.dp)) {
                    Text((if (n.pinned) "📌 " else "") + n.displayTitle, fontWeight = FontWeight.SemiBold, color = t.text,
                        maxLines = 1, overflow = TextOverflow.Ellipsis)
                    val first = n.body.lines().firstOrNull { it.isNotBlank() && it.trim() != n.title.trim() }
                    Caption(n.updatedAt.replace("T", " ").take(16) + (first?.let { " · $it" } ?: ""), maxLines = 1)
                }
                HorizontalDivider(color = t.border, modifier = Modifier.padding(horizontal = 16.dp))
            }
            item { Spacer(Modifier.height(88.dp)) }
        }
        FloatingActionButton(onClick = { onOpen(repo.addNote(boardId = board.id)) }, containerColor = t.teal, contentColor = t.tealText,
            modifier = Modifier.align(Alignment.BottomEnd).padding(16.dp)) { Icon(Icons.Filled.Add, "Новая заметка доски") }
    }
}
