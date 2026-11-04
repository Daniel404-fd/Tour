"""Версия 2.6: быстрое добавление задачи одной строкой и сортировка таблицы по заголовку."""
from datetime import date

import pytest

from tracker import logic
from tracker.db import Database
from tracker.logic import Task, Topic, parse_quick_task
from tests.test_v25 import app, keep  # noqa: F401  (фикстура и аккуратное удаление страниц)

WED = date(2026, 11, 4)   # среда
TOPICS = [Topic(1, "Дом", "#008000"), Topic(2, "Работа", "#000080"), Topic(3, "Учёба", "#800000")]


@pytest.mark.parametrize("text, title, deadline, topic, high", [
    ("Купить молоко завтра #дом !", "Купить молоко", date(2026, 11, 5), 1, True),
    ("Отчёт в пятницу #раб", "Отчёт", date(2026, 11, 6), 2, False),
    ("Созвон в среду", "Созвон", date(2026, 11, 11), None, False),      # сегодня среда → следующая
    ("Планёрка пн", "Планёрка", date(2026, 11, 9), None, False),
    ("Врач 12.01", "Врач", date(2027, 1, 12), None, False),             # прошедшая дата — следующий год
    ("Экзамен 20.12.2026 #учёба", "Экзамен", date(2026, 12, 20), 3, False),
    ("Сегодня позвонить маме", "позвонить маме", WED, None, False),
    ("Позвонить маме", "Позвонить маме", None, None, False),
    ("Сдать 31.02", "Сдать 31.02", None, None, False),                  # нет такой даты — остаётся текстом
    ("Подарок #друзья", "Подарок #друзья", None, None, False),          # нет такой темы — остаётся текстом
    ("Купить хлеб завтра послезавтра", "Купить хлеб послезавтра", date(2026, 11, 5), None, False),
])
def test_parse_quick_task(text, title, deadline, topic, high):
    q = parse_quick_task(text, TOPICS, WED)
    assert (q.title, q.deadline, q.topic_id, q.priority == logic.PRIORITY_HIGH) == (title, deadline, topic, high)


def test_quick_default_topic_and_hints():
    q = parse_quick_task("Пропылесосить завтра", TOPICS, WED, default_topic=1)
    assert q.topic_id == 1
    assert q.hints == ["срок: чт, 5 ноября (завтра)", "тема: Дом"]


def _page(tmp_path):
    from tracker.ui import tasks_tab
    db = Database(tmp_path / "t.sqlite3")
    return db, keep(tasks_tab.TasksPage(db))


def test_quick_add_creates_and_selects(tmp_path, app):
    db, page = _page(tmp_path)
    db.add_topic("Дом", "#008000")
    page.refresh()
    page.quick.setText("Полить цветы завтра #дом !")
    assert "тема: Дом" in page.quick_hint.text()
    page.quick.returnPressed.emit()
    [t] = db.list_tasks()
    assert (t.title, t.priority) == ("Полить цветы", logic.PRIORITY_HIGH)
    assert page.quick.text() == "" and page._selected().id == t.id
    page.quick.setText("завтра")           # одна дата без названия — ничего не создаём
    page.quick.returnPressed.emit()
    assert len(db.list_tasks()) == 1


def test_header_sort_cycle_and_persist(tmp_path, app):
    db, page = _page(tmp_path)
    db.add_task(Task(0, "Бета", deadline=date(2030, 1, 3), priority=logic.PRIORITY_LOW))
    db.add_task(Task(0, "альфа", deadline=None, priority=logic.PRIORITY_HIGH))
    db.add_task(Task(0, "Гамма", deadline=date(2030, 1, 1)))
    page.refresh()
    titles = lambda: [page.table.item(r, 0).text() for r in range(page.table.rowCount())]
    default = titles()
    page._header_clicked(0)
    assert titles() == ["альфа", "Бета", "Гамма"]           # без учёта регистра
    page._header_clicked(0)
    assert titles() == ["Гамма", "Бета", "альфа"]
    page._header_clicked(0)
    assert titles() == default                               # третий щелчок — обычный порядок
    page._header_clicked(3)
    assert titles() == ["Гамма", "Бета", "альфа"]            # по сроку, без срока — в конце
    page._header_clicked(3)
    assert titles() == ["Бета", "Гамма", "альфа"]            # и при убывании пустые в конце
    assert db.get_pref("tasks_sort") == "3:desc"
    from tracker.ui import tasks_tab
    again = keep(tasks_tab.TasksPage(db))
    again.refresh()
    assert [again.table.item(r, 0).text() for r in range(3)] == ["Бета", "Гамма", "альфа"]
