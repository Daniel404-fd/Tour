package ru.habittracker.app

import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import ru.habittracker.app.data.Db
import ru.habittracker.app.data.Event
import ru.habittracker.app.data.Goal
import ru.habittracker.app.data.Repo
import ru.habittracker.app.data.Sync
import ru.habittracker.app.data.SubtaskDraft
import ru.habittracker.app.data.Task
import java.io.File
import java.time.LocalDate
import java.time.LocalDateTime

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [34], application = android.app.Application::class)
class SyncInteropTest {
    private fun newRepo() = Repo(Db(ApplicationProvider.getApplicationContext(), null))

    @Test
    fun mergesFileFromDesktop() {
        val repo = newRepo()
        val blob = javaClass.classLoader!!.getResourceAsStream("desktop-payload.json.gz")!!.readBytes()
        val stats = Sync.mergeAll(repo.db, listOf(Sync.decode(blob)), repo.deviceId())
        assertTrue(stats.toString(), repo.habits().any { it.name == "Зарядка" })
        val h = repo.habits().first { it.name == "Зарядка" }
        assertTrue(LocalDate.of(2026, 1, 2) in (repo.allMarks()[h.id] ?: emptySet()))
        val task = repo.tasks().first { it.title == "Сдать отчёт" }
        assertEquals("Работа", repo.topics().first { it.id == task.topicId }.name)
        assertEquals(listOf("Собрать цифры" to false, "Отправить" to true), repo.subtasks(task.id).map { it.title to it.done })
        assertEquals("m:1:-1", task.repeat)
        assertEquals(listOf("работа", "срочно"), task.labelList)
        assertEquals("Повышение", repo.goals().first { it.id == task.goalId }.title)
        val att = repo.attachments().single()
        assertEquals("привет.txt" to 5L, att.name to att.size)
        assertEquals("С вложением", repo.note(att.noteId)!!.title)
        val g = repo.goals().first { it.title == "Отпуск" }
        assertTrue(g.financial)
        assertEquals(2500.5, repo.savedAmounts()[g.id]!!, 0.001)
        assertEquals(listOf("Выбрать страну"), repo.allSteps()[g.id]!!.map { it.title })
        val note = repo.notes().first { it.title == "Ёлка" }
        assertEquals("Идеи", repo.folders().first { it.id == note.folderId }.name)
        val ev = repo.events().first { it.title == "Йога" }
        assertEquals(listOf(0, 2), ev.weekdays)
        assertEquals(1, repo.calendars().size)                 // основной календарь не задвоился
        val b = repo.boards().single()
        assertEquals("Работа 1", b.name)
        val cols = repo.columns(b.id)
        assertEquals(listOf("К выполнению", "В работе", "Готово"), cols.map { it.name })
        val card = repo.boardTasks(b.id).single()
        assertEquals("Ревью договора" to cols[1].id, card.title to card.columnId)
        assertTrue(repo.tasks().none { it.boardId != null })     // в обычный список карточки не попадают
        assertEquals(listOf("Контакты"), repo.boardNotes(b.id).map { it.title })
        assertTrue(repo.notes().none { it.title == "Контакты" })
        assertEquals(repo.calendars()[0].id, ev.calendarId)

        // повторное слияние ничего не меняет
        val again = Sync.mergeAll(repo.db, listOf(Sync.decode(blob)), repo.deviceId())
        assertEquals(repo.habits().size, 1)
        assertTrue(again.toString(), !again.changed)
    }

    @Test
    fun twoPhonesConverge() {
        val a = newRepo(); val b = newRepo()
        a.addHabit("Чтение"); b.addTask(Task(title = "Купить хлеб"))
        fun swap() {
            val pa = Sync.decode(Sync.encode(Sync.export(a.db, a.deviceId(), "A")))
            val pb = Sync.decode(Sync.encode(Sync.export(b.db, b.deviceId(), "B")))
            Sync.mergeAll(a.db, listOf(pb), a.deviceId()); Sync.mergeAll(b.db, listOf(pa), b.deviceId())
        }
        swap()
        assertEquals(listOf("Чтение"), b.habits().map { it.name })
        assertEquals(listOf("Купить хлеб"), a.tasks().map { it.title })
        Thread.sleep(5)
        a.deleteHabit(a.habits()[0].id)
        swap()
        assertTrue(b.habits().isEmpty())
    }

    @Test
    fun subtasksEditorDiff() {
        val repo = newRepo()
        val tid = repo.addTask(Task(title = "Переезд"))
        repo.applySubtasks(tid, listOf(SubtaskDraft(0, "a", false), SubtaskDraft(0, "b", true)))
        val (a, b) = repo.subtasks(tid)
        repo.applySubtasks(tid, listOf(SubtaskDraft(b.id, "b2", true), SubtaskDraft(0, "c", false)))
        assertEquals(listOf("b2" to true, "c" to false), repo.subtasks(tid).map { it.title to it.done })
        assertTrue(repo.subtasks(tid).none { it.id == a.id })
        repo.deleteTask(tid)
        assertTrue(repo.allSubtasks().isEmpty())
    }

    @Test
    fun boardsMoveAndComplete() {
        val repo = newRepo()
        val b = repo.addBoard("Работа", "#1D4ED8")
        val (todo, doing, done) = repo.columns(b)
        val a = repo.addCard(b, todo.id, "A"); val bb = repo.addCard(b, todo.id, "B"); val c = repo.addCard(b, todo.id, "C")
        repo.moveCard(c, todo.id, 0)
        assertEquals(listOf("C", "A", "B"), repo.cardsIn(todo.id).map { it.title })
        repo.moveCard(bb, done.id, 0)
        assertTrue(repo.task(bb)!!.done)
        repo.moveCard(bb, doing.id, 0)
        assertTrue(!repo.task(bb)!!.done)
        repo.completeTask(a)
        assertEquals(done.id, repo.task(a)!!.columnId)
        repo.completeTask(a, false)
        assertEquals(todo.id, repo.task(a)!!.columnId)
        repeat(60) { repo.moveCard(c, todo.id, 1); repo.moveCard(c, todo.id, 0) }
        assertEquals(listOf("C", "A"), repo.cardsIn(todo.id).map { it.title })
        repo.deleteBoard(b)
        assertTrue(repo.tasks(includeBoards = true).isEmpty() && repo.boards().isEmpty())
    }

    @Test
    fun repeatingTaskSpawnsNext() {
        val repo = newRepo()
        val today = LocalDate.now()
        val id = repo.addTask(Task(title = "Отчёт", deadline = today, repeat = "d:1", labels = "работа"))
        repo.applySubtasks(id, listOf(SubtaskDraft(0, "цифры", true)))
        repo.completeTask(id)
        val old = repo.task(id)!!
        assertTrue(old.done && old.repeat == null)
        val next = repo.tasks().single { !it.done }
        assertEquals(today.plusDays(1), next.deadline)
        assertEquals("d:1", next.repeat)
        assertEquals(listOf("цифры" to false), repo.subtasks(next.id).map { it.title to it.done })
        // карточка возвращается в первую колонку
        val b = repo.addBoard("Работа", "#1D4ED8")
        val (todo, _, done) = repo.columns(b)
        val c = repo.addCard(b, todo.id, "Планёрка", today)
        repo.updateTask(repo.task(c)!!.copy(repeat = "w:1"))
        repo.moveCard(c, done.id, 0)
        val again = repo.boardTasks(b).single { it.id != c }
        assertEquals(todo.id to today.plusDays(7), again.columnId to again.deadline)
    }

    @Test
    fun goalProgressWithLinkedTasks() {
        val repo = newRepo()
        val g = repo.addGoal(Goal(title = "Права"))
        repo.addStep(g, "Справка")
        val a = repo.addTask(Task(title = "Автошкола", goalId = g))
        repo.addTask(Task(title = "Теория", goalId = g))
        repo.completeTask(a)
        val goal = repo.goals().single()
        assertEquals(1.0 / 3, ru.habittracker.app.data.Logic.goalProgress(goal, repo.allSteps()[g] ?: emptyList(), 0.0, repo.goalTaskFlags()[g]!!), 1e-9)
    }

    @Test
    fun attachmentsStoreAndCleanup() {
        val ctx = ApplicationProvider.getApplicationContext<android.content.Context>()
        val repo = newRepo()
        val n = repo.addNote()
        val id = ru.habittracker.app.data.Attachments.addBytes(ctx, repo, n, "текст".toByteArray(), "заметка.txt")
        val a = repo.attachments(n).single()
        assertEquals(id, a.id)
        assertTrue(ru.habittracker.app.data.Attachments.file(ctx, a).exists())
        assertEquals("text", ru.habittracker.app.data.Attachments.kind(a.name))
        repo.deleteNote(n)
        assertTrue(repo.attachments().isEmpty())
        assertTrue(ru.habittracker.app.data.Attachments.cleanup(ctx, repo) >= 1)
        assertTrue(!ru.habittracker.app.data.Attachments.file(ctx, a).exists())
    }

    @Test
    fun customColorsStayReadable() {
        for (dark in listOf(false, true)) for (c in listOf("#FFD700", "#000000", "#BE185D", "#0F6E6A")) {
            val t = ru.habittracker.app.ui.derive(if (dark) ru.habittracker.app.ui.DarkTokens else ru.habittracker.app.ui.LightTokens, dark, c, c)
            val r = ru.habittracker.app.ui.Contrast::ratio
            assertTrue("$c teal", r(t.tealText, t.teal) >= 4.5)
            assertTrue("$c link", r(t.link, t.surface) >= 4.5)
            assertTrue("$c accent", r(t.accentText, t.accent) >= 4.5)
            assertTrue("$c onSoft", r(t.tealOnSoft, t.tealSoft) >= 4.5)
        }
        // стандартные токены тоже: вторичный текст и ссылки на карточке
        for (t in listOf(ru.habittracker.app.ui.LightTokens, ru.habittracker.app.ui.DarkTokens)) {
            assertTrue(ru.habittracker.app.ui.Contrast.ratio(t.text2, t.surface) >= 7.0)
            assertTrue(ru.habittracker.app.ui.Contrast.ratio(t.text3, t.surface) >= 4.5)
            assertTrue(ru.habittracker.app.ui.Contrast.ratio(t.link, t.surface) >= 4.5)
        }
    }

    /** Файл «как с телефона» — его проверяет tools/interop.py check на стороне ПК (в CI). */
    @Test
    fun writesFileForDesktop() {
        val repo = newRepo()
        val h = repo.addHabit("Пробежка")
        repo.setMark(h, LocalDate.of(2026, 3, 1), true)
        val tid = repo.addTask(Task(title = "Позвонить маме", deadline = LocalDate.of(2026, 3, 8)))
        repo.applySubtasks(tid, listOf(SubtaskDraft(0, "Купить цветы", true), SubtaskDraft(0, "Позвонить", false)))
        val n = repo.addNote(); repo.updateNote(n, "С телефона", "Текст")
        repo.addEvent(Event(title = "Врач", start = LocalDateTime.of(2026, 3, 2, 10, 0), end = LocalDateTime.of(2026, 3, 2, 11, 0),
            calendarId = repo.calendars()[0].id, reminder = 30))
        val b = repo.addBoard("Фриланс", "#7E22CE")
        val cols = repo.columns(b)
        val card = repo.addCard(b, cols[0].id, "Логотип")
        repo.moveCard(card, cols[2].id, 0)
        val bn = repo.addNote(boardId = b); repo.updateNote(bn, "Бриф", "")
        val g = repo.addGoal(Goal(title = "Машина", financial = true, targetAmount = 500000.0))
        repo.addTask(Task(title = "Планёрка", repeat = "w:1:0,1,2,3,4", labels = "работа", goalId = g))
        val pn = repo.addNote(); repo.updateNote(pn, "С фото", "")
        ru.habittracker.app.data.Attachments.addBytes(ApplicationProvider.getApplicationContext(), repo, pn, byteArrayOf(1, 2, 3), "фото.jpg", "image/jpeg")
        repo.addContribution(g, 1000.0)
        val out = File(System.getProperty("interop.out") ?: "build/interop/android-payload.json.gz")
        out.parentFile?.mkdirs()
        out.writeBytes(Sync.encode(Sync.export(repo.db, repo.deviceId(), "Телефон")))
    }
}
