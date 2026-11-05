"""Версия 2.8: повторяющиеся задачи, метки, связь с целью/заметкой, «Сегодня», обзор недели,
Ctrl+K, фильтры досок, «Все доски», удаление с отменой."""
from datetime import date, datetime, timedelta

import pytest

from tracker import logic, sync
from tracker.db import Database
from tracker.logic import Goal, Task, next_due, parse_quick_task
from tests.test_v25 import app, keep  # noqa: F401

THU = date(2026, 11, 5)


@pytest.mark.parametrize("rule, due, expected", [
    ("d:1", THU, date(2026, 11, 6)),
    ("d:3", date(2026, 10, 1), date(2026, 11, 6)),          # давно просрочено — ближайший будущий
    ("w:1:0,2", date(2026, 11, 4), date(2026, 11, 9)),       # пн и ср
    ("w:1:0,1,2,3,4", THU, date(2026, 11, 6)),               # по будням: чт → пт
    ("w:1:0,1,2,3,4", date(2026, 11, 6), date(2026, 11, 9)), # пт → пн
    ("w:2", THU, date(2026, 11, 19)),
    ("m:1", date(2026, 10, 31), date(2026, 11, 30)),         # 31-го нет — последний день
    ("m:1:-1", date(2026, 11, 30), date(2026, 12, 31)),
    ("y:1", date(2025, 2, 28), date(2027, 2, 28)),
])
def test_next_due(rule, due, expected):
    assert next_due(rule, due, THU) == expected


def test_quick_parse_repeat_and_labels():
    q = parse_quick_task("Планёрка каждый понедельник @работа", [], THU)
    assert (q.title, q.repeat, q.deadline, q.labels) == ("Планёрка", "w:1:0", date(2026, 11, 9), ["работа"])
    q = parse_quick_task("Зарядка каждый день", [], THU)
    assert (q.title, q.repeat, q.deadline) == ("Зарядка", "d:1", THU)
    q = parse_quick_task("Полить цветы по будням", [], THU)
    assert q.repeat == "w:1:0,1,2,3,4"
    assert logic.parse_labels("срочно, #Клиент;срочно") == ["срочно", "Клиент"]


def test_repeating_task_spawns_next(tmp_path):
    db = Database(tmp_path / "t.sqlite3")
    tid = db.add_task(Task(0, "Отчёт", deadline=date.today(), repeat="d:1", labels="работа"))
    db.add_subtask(tid, "цифры")
    db.set_subtask_done(db.subtasks(tid)[0].id, True)
    db.complete_task(tid)
    old = db.get_task(tid)
    assert old.done and old.repeat is None
    [new] = [t for t in db.list_tasks() if not t.done]
    assert new.deadline == date.today() + timedelta(days=1) and new.repeat == "d:1" and new.labels == "работа"
    assert [(s.title, s.done) for s in db.subtasks(new.id)] == [("цифры", False)]
    db.complete_task(tid, False)          # снять галочку со старой — новых копий не плодится
    db.complete_task(tid, True)
    assert len(db.list_tasks()) == 2


def test_repeating_card_returns_to_first_column(tmp_path):
    db = Database(tmp_path / "t.sqlite3")
    b = db.add_board("Работа")
    todo, doing, done = db.list_columns(b)
    tid = db.add_card(b, doing.id, "Планёрка", deadline=date.today(), repeat="w:1")
    db.move_card(tid, done.id, 0)
    cards = db.list_tasks(board_id=b)
    nxt = next(t for t in cards if t.id != tid)
    assert nxt.column_id == todo.id and not nxt.done and nxt.deadline == date.today() + timedelta(days=7)


def test_goal_progress_counts_linked_tasks(tmp_path):
    db = Database(tmp_path / "t.sqlite3")
    gid = db.add_goal(Goal(0, "Права"))
    db.add_step(gid, "Мед. справка")
    a = db.add_task(Task(0, "Записаться в автошколу", goal_id=gid))
    db.add_task(Task(0, "Сдать теорию", goal_id=gid))
    g = db.get_goal(gid)
    flags = db.goal_task_flags()
    assert logic.goal_progress(g, db.all_steps().get(gid, []), 0, flags[gid]) == 0
    db.complete_task(a)
    assert logic.goal_progress(g, db.all_steps().get(gid, []), 0, db.goal_task_flags()[gid]) == pytest.approx(1 / 3)
    db.delete_goal(gid)
    assert db.get_task(a).goal_id is None            # задача остаётся, связь пропадает


def test_new_fields_sync(tmp_path):
    pc, ph = Database(tmp_path / "pc.sqlite3"), Database(tmp_path / "ph.sqlite3")
    gid = pc.add_goal(Goal(0, "Отпуск"))
    nid = pc.add_note("План", "…")
    pc.add_task(Task(0, "Билеты", repeat="m:1:-1", labels="личное, срочно", goal_id=gid, note_id=nid))
    ph.sync_merge([sync.decode(pc.sync_export("ПК"))])
    [t] = ph.list_tasks()
    assert t.repeat == "m:1:-1" and t.label_list == ["личное", "срочно"]
    assert ph.get_goal(t.goal_id).title == "Отпуск" and ph.get_note(t.note_id).title == "План"


# ---------------------------------------------------------------- окна

def test_today_page_lists_and_plans(tmp_path, app):
    from tracker.ui import today_tab
    db = Database(tmp_path / "t.sqlite3")
    today = date.today()
    late = db.add_task(Task(0, "Хвост", deadline=today - timedelta(days=3)))
    b = db.add_board("Работа")
    card = db.add_card(b, db.list_columns(b)[0].id, "Созвон", deadline=today)
    db.add_habit("Зарядка")
    page = keep(today_tab.TodayPage(db))
    page.resize(1200, 800)
    page.refresh()
    rows = page.findChildren(today_tab.TaskRow)
    assert {r.task.title for r in rows} >= {"Хвост", "Созвон"}
    page._all_reschedule([late], today)
    assert db.get_task(late).deadline == today
    start = datetime.combine(today, datetime.min.time()).replace(hour=15)
    page.plan_task(card, start)
    [ev] = db.list_events()
    assert ev.title == "Созвон" and ev.start == start and ev.end == start + timedelta(hours=1)
    page._quick_field.setText("Позвонить в банк !")
    page._quick(page._quick_field)
    t = next(t for t in db.list_tasks() if t.title == "Позвонить в банк")
    assert t.deadline == today and t.priority == logic.PRIORITY_HIGH


def test_week_review_and_note(tmp_path, app):
    from tracker.ui import today_tab
    db = Database(tmp_path / "t.sqlite3")
    tid = db.add_task(Task(0, "Сделанное"))
    db.complete_task(tid)
    page = keep(today_tab.TodayPage(db, navigate=lambda *a, **k: None))
    page._tab(1)
    assert "Сделано за неделю: 1" in page.header.subtitle.text()
    today = date.today()
    start = today - timedelta(days=today.weekday())
    page._save_review(start, start + timedelta(days=6), [db.get_task(tid)], [], [], {}, [today])
    [n] = db.list_notes()
    assert n.title.startswith("Неделя") and "✓ Сделанное" in n.body
    assert db.list_folders()[0].name == "Обзоры недели"


def test_palette_search_and_create(tmp_path, app):
    from tracker.session import Session
    from tracker.ui.main_window import MainWindow, SECTIONS
    from tracker.ui.palette import CommandPalette
    s = Session.open_plain(tmp_path / "d")
    db = s.db
    db.add_task(Task(0, "Купить молоко"))
    b = db.add_board("Работа 1")
    db.add_note("Молочные продукты", "список", board_id=b)
    win = keep(MainWindow(s))
    pal = CommandPalette(win, [(k, t) for k, t, _ in SECTIONS])
    pal.edit.setText("мол")
    texts = [pal.list.item(i).text() for i in range(pal.list.count())]
    assert any(t.startswith("Купить молоко") for t in texts)
    assert any(t.startswith("Молочные продукты") for t in texts)
    pal.edit.setText("+ Отчёт завтра @клиент")
    texts = [pal.list.item(i).text() for i in range(pal.list.count())]
    assert texts[1].startswith("Новая задача: Отчёт")
    assert any("Новая карточка в «Работа 1»" in t for t in texts)
    pal._run_current()
    t = next(t for t in db.list_tasks() if t.title == "Отчёт")
    assert t.label_list == ["клиент"] and t.deadline == date.today() + timedelta(days=1)


def test_board_label_filter_overview_and_undo(tmp_path, app):
    from tracker.session import Session
    from tracker.ui import boards_tab, widgets as w
    from tracker.ui.main_window import MainWindow, BOARDS
    s = Session.open_plain(tmp_path / "d")
    db = s.db
    b1, b2 = db.add_board("Работа 1"), db.add_board("Работа 2")
    c1 = db.add_card(b1, db.list_columns(b1)[0].id, "Отчёт", labels="клиент")
    db.add_card(b1, db.list_columns(b1)[0].id, "Кофе")
    db.add_card(b2, db.list_columns(b2)[0].id, "Созвон", deadline=date.today() - timedelta(days=1))
    win = keep(MainWindow(s))
    win.show()
    win.navigate("boards")
    page = win.pages[BOARDS]
    page.select_board(b1)
    page._set_label("клиент")

    def titles():
        return [page.cols_row.itemAt(0).widget().list.item(i).toolTip()
                for i in range(page.cols_row.itemAt(0).widget().list.count())]
    assert titles() == ["Отчёт"]
    page._set_label(None)
    assert sorted(titles()) == ["Кофе", "Отчёт"]
    page.select_board(boards_tab.ALL_BOARDS)
    assert "просрочено" in page.header.subtitle.text()
    page.select_board(b1)
    page.delete_card(c1)                      # без вопроса, с «Отменить»
    assert c1 in w.PENDING_DELETE and db.get_task(c1) is not None
    assert "Отчёт" not in titles()
    win._finish_undo(apply=False)              # нажали «Отменить»
    assert db.get_task(c1) is not None and "Отчёт" in titles()
    page.delete_card(c1)
    win._finish_undo(apply=True)               # подсказка истекла
    assert db.get_task(c1) is None
    win.close()


def test_card_keyboard_moves(tmp_path, app):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import QEvent
    from tracker.ui import boards_tab
    db = Database(tmp_path / "t.sqlite3")
    b = db.add_board("Работа")
    todo, doing, _ = db.list_columns(b)
    tid = db.add_card(b, todo.id, "A")
    page = keep(boards_tab.BoardsPage(db))
    page.refresh()
    col = page.cols_row.itemAt(0).widget()
    col.list.setCurrentRow(0)
    col.list.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Right, Qt.ControlModifier))
    assert db.get_task(tid).column_id == doing.id
