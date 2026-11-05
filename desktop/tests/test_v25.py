"""Версия 2.5: подзадачи, масштаб календаря, свои цвета, фильтр тем списком."""
import os
from datetime import date

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication, QComboBox

from tracker import sync
from tracker.db import Database
from tracker.logic import Task


_pages = []


def keep(page):
    """Страницы удаляем как в программе — deleteLater, а не сборщиком мусора Python
    (иначе при выходе из интерпретатора PySide может упасть, хотя тесты прошли)."""
    _pages.append(page)
    return page


@pytest.fixture
def app():
    from PySide6.QtCore import QCoreApplication, QEvent
    a = QApplication.instance() or QApplication([])
    from tracker.ui import theme
    theme.install(a)
    yield a
    while _pages:
        _pages.pop().deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    theme.set_appearance({})


# ---------------------------------------------------------------- подзадачи

def test_subtasks_crud_and_cascade(tmp_path):
    db = Database(tmp_path / "t.sqlite3")
    tid = db.add_task(Task(0, "Переезд"))
    a = db.add_subtask(tid, "Коробки")
    b = db.add_subtask(tid, "Грузчики")
    db.set_subtask_done(a, True)
    db.rename_subtask(b, "Заказать грузчиков")
    assert [(s.title, s.done) for s in db.subtasks(tid)] == [("Коробки", True), ("Заказать грузчиков", False)]
    db.delete_task(tid)
    assert db.all_subtasks() == {}


def test_subtasks_sync_both_ways(tmp_path):
    pc, phone = Database(tmp_path / "pc.sqlite3"), Database(tmp_path / "phone.sqlite3")
    tid = pc.add_task(Task(0, "Отчёт"))
    s1 = pc.add_subtask(tid, "Собрать цифры")
    phone.sync_merge([sync.decode(pc.sync_export("ПК"))])
    [t] = phone.list_tasks()
    [st] = phone.subtasks(t.id)
    phone.set_subtask_done(st.id, True)
    phone.add_subtask(t.id, "Отправить")
    pc.sync_merge([sync.decode(phone.sync_export("Телефон"))])
    assert [(s.title, s.done) for s in pc.subtasks(tid)] == [("Собрать цифры", True), ("Отправить", False)]
    # удаление подзадачи тоже доходит
    pc.delete_subtask(s1)
    phone.sync_merge([sync.decode(pc.sync_export("ПК"))])
    assert [s.title for s in phone.subtasks(t.id)] == ["Отправить"]


def test_apply_subtasks_diff_and_order(tmp_path, app):
    from tracker.ui.tasks_tab import apply_subtasks
    db = Database(tmp_path / "t.sqlite3")
    tid = db.add_task(Task(0, "T"))
    apply_subtasks(db, tid, [{"id": 0, "title": "a", "done": False}, {"id": 0, "title": "b", "done": True}])
    a, b = db.subtasks(tid)
    apply_subtasks(db, tid, [{"id": b.id, "title": "b2", "done": True}, {"id": 0, "title": "c", "done": False}])
    assert [(s.title, s.done) for s in db.subtasks(tid)] == [("b2", True), ("c", False)]


def test_task_page_detail_and_progress(tmp_path, app):
    from tracker.ui import tasks_tab
    db = Database(tmp_path / "t.sqlite3")
    tid = db.add_task(Task(0, "Ремонт", deadline=date.today()))
    db.add_subtask(tid, "Обои")
    s2 = db.add_subtask(tid, "Клей")
    db.set_subtask_done(s2, True)
    page = keep(tasks_tab.TasksPage(db))
    page.resize(1200, 700)
    page.refresh()
    assert page.table.item(0, 1).text() == "1/2"
    page.table.selectRow(0)
    assert page.detail.isVisibleTo(page)
    assert [e["title"] for e in page.d_subs.entries()] == ["Обои", "Клей"]
    # отметили подзадачу в карточке — записалось в базу
    from PySide6.QtCore import Qt
    page.d_subs.list.item(0).setCheckState(Qt.Checked)
    app.processEvents()
    assert all(s.done for s in db.subtasks(tid))


def test_many_topics_become_dropdown(tmp_path, app):
    from tracker.ui import tasks_tab
    db = Database(tmp_path / "t.sqlite3")
    ids = [db.add_topic(f"Тема {i}", "#008000") for i in range(16)]
    db.add_task(Task(0, "x", topic_id=ids[3]))
    db.add_task(Task(0, "y", topic_id=ids[5]))
    page = keep(tasks_tab.TasksPage(db))
    page.refresh()
    combos = [c for c in page.findChildren(QComboBox) if c.accessibleName() == "Фильтр по теме"]
    assert combos, "при 16 темах фильтр должен быть списком"
    combo = combos[-1]
    combo.setCurrentIndex(combo.findData(ids[3]))
    app.processEvents()
    assert page.table.rowCount() == 1 and page.table.item(0, 0).text().startswith("x")
    assert db.get_pref("tasks_topic") == str(ids[3])    # выбор запоминается


def test_few_topics_stay_chips(tmp_path, app):
    from tracker.ui import tasks_tab
    db = Database(tmp_path / "t.sqlite3")
    for i in range(3):
        db.add_topic(f"Тема {i}", "#008000")
    page = keep(tasks_tab.TasksPage(db))
    page.refresh()
    assert not [c for c in page.findChildren(QComboBox) if c.accessibleName() == "Фильтр по теме"]
    assert len(page.topic_group.buttons()) == 5   # все + 3 темы + без темы


# ---------------------------------------------------------------- масштаб календаря

def test_calendar_zoom_keeps_time_and_persists(tmp_path, app):
    from tracker.ui import calendar_tab
    db = Database(tmp_path / "t.sqlite3")
    page = keep(calendar_tab.CalendarPage(db, lambda *a, **k: None))
    page.resize(1200, 800)
    page.show()
    page.refresh()
    app.processEvents()
    page.zoom(1)
    page.zoom(1)
    assert page.grid.hour_h == 76
    assert page.grid.minimumHeight() == 24 * 76 + 1
    assert db.get_pref("cal_zoom") == "76"
    assert page.zoom_label.text() == "158%"
    for _ in range(20):
        page.zoom(-1)
    assert page.grid.hour_h == calendar_tab.ZOOM_STEPS[0] and not page.zoom_out.isEnabled()
    page2 = keep(calendar_tab.CalendarPage(db, lambda *a, **k: None))
    assert page2.grid.hour_h == calendar_tab.ZOOM_STEPS[0]
    page.close()


# ---------------------------------------------------------------- оформление

@pytest.mark.parametrize("dark", [False, True])
@pytest.mark.parametrize("primary", ["#FFD700", "#0F6E6A", "#000000", "#BE185D"])
def test_custom_colors_stay_readable(primary, dark):
    from tracker.ui import theme as th
    t = th.derive(th.DARK if dark else th.LIGHT, dark, {"primary": primary, "accent": primary})
    assert th.contrast(t["teal_text"], t["teal"]) >= 4.5      # текст на кнопках и панели
    assert th.contrast(t["link"], t["surface"]) >= 4.5         # ссылки
    assert th.contrast(t["accent_text"], t["accent"]) >= 4.5   # отмеченный день
    assert th.contrast(t["teal_on_soft"], t["teal_soft"]) >= 4.5


def test_sidebar_text_follows_background():
    from tracker.ui import theme as th
    light = th.derive(th.LIGHT, False, {"sidebar": {"mode": "color", "color": "#F5E6C8"}})
    assert light["sidebar_text"] == "#1A1C1E"
    dark = th.derive(th.LIGHT, False, {"sidebar": {"mode": "color", "color": "#202040"}})
    assert dark["sidebar_text"] == "#FFFFFF"
    img = th.derive(th.LIGHT, False, {"sidebar": {"mode": "image", "image": "x.png", "dim": 0.5}})
    assert img["sidebar_image"] == "x.png" and img["sidebar_dim"] == 0.5 and img["sidebar_text"] == "#FFFFFF"


def test_set_appearance_repaints(app):
    from tracker.ui import theme as th
    th.set_appearance({"primary": "#1D4ED8", "mode": "dark"})
    assert th.theme.dark and th.theme["teal"] != th.DARK["teal"]
    th.set_appearance({"mode": "light"})
    assert not th.theme.dark and th.theme["teal"] == th.LIGHT["teal"]
