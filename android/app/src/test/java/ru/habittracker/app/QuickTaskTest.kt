package ru.habittracker.app

import org.junit.Assert.assertEquals
import org.junit.Test
import ru.habittracker.app.data.PRIORITY_HIGH
import ru.habittracker.app.data.Quick
import ru.habittracker.app.data.Topic
import java.time.LocalDate

/** Те же случаи, что в desktop/tests/test_v26.py — разбор строки одинаков на ПК и телефоне. */
class QuickTaskTest {
    private val wed = LocalDate.of(2026, 11, 4)
    private val topics = listOf(Topic(1, "Дом", "#008000"), Topic(2, "Работа", "#000080"), Topic(3, "Учёба", "#800000"))

    private fun check(text: String, title: String, deadline: LocalDate?, topic: Long?, high: Boolean) {
        val q = Quick.parse(text, topics, wed)
        assertEquals(text, listOf(title, deadline, topic, high), listOf(q.title, q.deadline, q.topicId, q.priority == PRIORITY_HIGH))
    }

    @Test fun cases() {
        check("Купить молоко завтра #дом !", "Купить молоко", LocalDate.of(2026, 11, 5), 1, true)
        check("Отчёт в пятницу #раб", "Отчёт", LocalDate.of(2026, 11, 6), 2, false)
        check("Созвон в среду", "Созвон", LocalDate.of(2026, 11, 11), null, false)
        check("Планёрка пн", "Планёрка", LocalDate.of(2026, 11, 9), null, false)
        check("Врач 12.01", "Врач", LocalDate.of(2027, 1, 12), null, false)
        check("Экзамен 20.12.2026 #учёба", "Экзамен", LocalDate.of(2026, 12, 20), 3, false)
        check("Сегодня позвонить маме", "позвонить маме", wed, null, false)
        check("Позвонить маме", "Позвонить маме", null, null, false)
        check("Сдать 31.02", "Сдать 31.02", null, null, false)
        check("Подарок #друзья", "Подарок #друзья", null, null, false)
        check("Купить хлеб завтра послезавтра", "Купить хлеб послезавтра", LocalDate.of(2026, 11, 5), null, false)
    }

    @Test fun hintsAndDefaultTopic() {
        val q = Quick.parse("Пропылесосить завтра", topics, wed, defaultTopic = 1)
        assertEquals(1L, q.topicId)
        assertEquals(listOf("срок: чт, 5 ноября (завтра)", "тема: Дом"), q.hints)
    }
}
