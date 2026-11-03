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
        val g = repo.goals().first { it.title == "Отпуск" }
        assertTrue(g.financial)
        assertEquals(2500.5, repo.savedAmounts()[g.id]!!, 0.001)
        assertEquals(listOf("Выбрать страну"), repo.allSteps()[g.id]!!.map { it.title })
        val note = repo.notes().first { it.title == "Ёлка" }
        assertEquals("Идеи", repo.folders().first { it.id == note.folderId }.name)
        val ev = repo.events().first { it.title == "Йога" }
        assertEquals(listOf(0, 2), ev.weekdays)
        assertEquals(1, repo.calendars().size)                 // основной календарь не задвоился
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

    /** Файл «как с телефона» — его проверяет tools/interop.py check на стороне ПК (в CI). */
    @Test
    fun writesFileForDesktop() {
        val repo = newRepo()
        val h = repo.addHabit("Пробежка")
        repo.setMark(h, LocalDate.of(2026, 3, 1), true)
        repo.addTask(Task(title = "Позвонить маме", deadline = LocalDate.of(2026, 3, 8)))
        val n = repo.addNote(); repo.updateNote(n, "С телефона", "Текст")
        repo.addEvent(Event(title = "Врач", start = LocalDateTime.of(2026, 3, 2, 10, 0), end = LocalDateTime.of(2026, 3, 2, 11, 0),
            calendarId = repo.calendars()[0].id, reminder = 30))
        val g = repo.addGoal(Goal(title = "Машина", financial = true, targetAmount = 500000.0))
        repo.addContribution(g, 1000.0)
        val out = File(System.getProperty("interop.out") ?: "build/interop/android-payload.json.gz")
        out.parentFile?.mkdirs()
        out.writeBytes(Sync.encode(Sync.export(repo.db, repo.deviceId(), "Телефон")))
    }
}
