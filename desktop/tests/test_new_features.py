import sqlite3
from datetime import date, timedelta

from tracker import logic
from tracker.db import Database
from tracker.logic import Goal, GoalStep, Note, Task

TODAY = date(2026, 11, 1)


def d(offset: int) -> date:
    return TODAY + timedelta(days=offset)


# ---------- темы ----------

def test_filter_by_topic():
    tasks = [Task(1, "a", topic_id=1), Task(2, "b", topic_id=2), Task(3, "c")]
    ids = lambda tid: [t.id for t in logic.filter_by_topic(tasks, tid)]
    assert ids(logic.TOPIC_ALL) == [1, 2, 3]
    assert ids(logic.TOPIC_NONE) == [3]
    assert ids(2) == [2]


def test_topics_in_db_and_delete_keeps_tasks(tmp_path):
    db = Database(tmp_path / "t.sqlite3")
    home = db.add_topic("Дом", "#2E7D32")
    work = db.add_topic("работа", "#1565C0")
    assert [t.name for t in db.list_topics()] == ["Дом", "работа"]  # без учёта регистра
    tid = db.add_task(Task(0, "Помыть окна", topic_id=home))
    assert db.get_task(tid).topic_id == home
    task = db.get_task(tid)
    task.topic_id = work
    db.update_task(task)
    assert db.get_task(tid).topic_id == work
    db.delete_topic(work)
    assert db.get_task(tid) is not None
    assert db.get_task(tid).topic_id is None
    db.close()


def test_migration_adds_topic_column(tmp_path):
    path = tmp_path / "old.sqlite3"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,"
                 " description TEXT NOT NULL DEFAULT '', deadline TEXT,"
                 " priority INTEGER NOT NULL DEFAULT 1, done INTEGER NOT NULL DEFAULT 0,"
                 " completed_on TEXT, archived INTEGER NOT NULL DEFAULT 0)")
    conn.execute("INSERT INTO tasks(title) VALUES ('старая')")
    conn.commit()
    conn.close()
    db = Database(path)
    [t] = db.list_tasks()
    assert (t.title, t.topic_id) == ("старая", None)
    assert db.list_goals() == [] and db.list_notes() == []
    db.close()


# ---------- ближайшие задачи ----------

def test_upcoming_tasks_window():
    tasks = [
        Task(1, "просрочена", deadline=d(-2)),
        Task(2, "сегодня", deadline=d(0)),
        Task(3, "через 4 дня", deadline=d(4)),
        Task(4, "через 5 дней", deadline=d(5)),
        Task(5, "без срока"),
        Task(6, "выполнена", deadline=d(1), done=True),
        Task(7, "в архиве", deadline=d(1), archived=True),
    ]
    assert [t.id for t in logic.upcoming_tasks(tasks, TODAY, days=4)] == [1, 2, 3]


def test_due_text_and_plural():
    assert logic.due_text(d(0), TODAY) == "сегодня"
    assert logic.due_text(d(1), TODAY) == "завтра"
    assert logic.due_text(d(3), TODAY) == "через 3 дня"
    assert logic.due_text(d(11), TODAY) == "через 11 дней"
    assert logic.due_text(d(21), TODAY) == "через 21 день"
    assert logic.due_text(d(-1), TODAY) == "просрочено на 1 день"
    assert logic.plural(12, "день", "дня", "дней") == "дней"
    assert logic.plural(22, "день", "дня", "дней") == "дня"


# ---------- цели ----------

def test_goal_progress():
    g = Goal(1, "Выучить английский")
    assert logic.goal_progress(g, []) == 0.0
    steps = [GoalStep(1, 1, "A1", True), GoalStep(2, 1, "A2", True),
             GoalStep(3, 1, "B1"), GoalStep(4, 1, "B2")]
    assert logic.goal_progress(g, steps) == 0.5
    g.done = True
    assert logic.goal_progress(g, steps) == 1.0


def test_active_goals_sorted_by_deadline():
    goals = [Goal(1, "без срока"), Goal(2, "далеко", target_date=d(300)),
             Goal(3, "близко", target_date=d(30)), Goal(4, "готово", done=True),
             Goal(5, "архив", archived=True)]
    assert [g.id for g in logic.active_goals(goals)] == [3, 2, 1]


def test_goals_and_steps_in_db(tmp_path):
    db = Database(tmp_path / "t.sqlite3")
    gid = db.add_goal(Goal(0, "Пробежать марафон", target_date=d(200)))
    s1 = db.add_step(gid, "10 км")
    s2 = db.add_step(gid, "Полумарафон")
    db.set_step_done(s1, True)
    steps = db.steps(gid)
    assert [s.title for s in steps] == ["10 км", "Полумарафон"]
    assert logic.goal_progress(db.get_goal(gid), steps) == 0.5
    goal = db.get_goal(gid)
    goal.done = True
    db.update_goal(goal)
    assert db.get_goal(gid).completed_on == date.today()
    db.delete_step(s2)
    assert len(db.steps(gid)) == 1
    db.delete_goal(gid)
    assert db.all_steps() == {}  # шаги удаляются вместе с целью
    db.close()


# ---------- заметки ----------

def test_note_display_title():
    assert Note(1, "  План  ").display_title == "План"
    assert Note(2, "", "\n\nПервая строка\nвторая").display_title == "Первая строка"
    assert Note(3).display_title == "Без названия"


def test_sort_and_search_notes():
    notes = [Note(1, "старая", updated_at="2026-10-01T10:00:00"),
             Note(2, "новая", "про отпуск", updated_at="2026-10-30T10:00:00"),
             Note(3, "закреплённая", pinned=True, updated_at="2026-01-01T10:00:00")]
    assert [n.id for n in logic.sort_notes(notes)] == [3, 2, 1]
    assert [n.id for n in logic.search_notes(notes, "ОТПУСК")] == [2]
    assert len(logic.search_notes(notes, "  ")) == 3


def test_notes_in_db(tmp_path):
    db = Database(tmp_path / "t.sqlite3")
    nid = db.add_note()
    db.update_note(nid, "Идеи", "текст")
    db.set_note_pinned(nid, True)
    n = db.get_note(nid)
    assert (n.title, n.body, n.pinned) == ("Идеи", "текст", True)
    db.delete_note(nid)
    assert db.get_note(nid) is None
    db.close()


def test_habit_restore_and_delete(tmp_path):
    db = Database(tmp_path / "t.sqlite3")
    hid = db.add_habit("Зарядка")
    db.set_mark(hid, TODAY, True)
    db.archive_habit(hid)
    assert db.list_habits() == []
    db.archive_habit(hid, False)
    assert [h.id for h in db.list_habits()] == [hid]
    db.delete_habit(hid)
    assert db.list_habits(include_archived=True) == [] and db.all_marks() == {}
    db.close()
