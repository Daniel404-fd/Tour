from datetime import date, timedelta

from tracker import logic
from tracker.db import Database
from tracker.logic import Habit, Task

TODAY = date(2026, 11, 1)


def d(offset: int) -> date:
    """День относительно TODAY: d(0) — сегодня, d(-1) — вчера."""
    return TODAY + timedelta(days=offset)


# ---------- стрики ----------

def test_streak_when_today_marked():
    assert logic.current_streak({d(0), d(-1), d(-2)}, TODAY) == 3


def test_streak_when_today_not_marked_counts_until_yesterday():
    assert logic.current_streak({d(-1), d(-2), d(-3)}, TODAY) == 3


def test_streak_zero_when_nothing_today_and_yesterday():
    assert logic.current_streak({d(-2), d(-3)}, TODAY) == 0
    assert logic.current_streak(set(), TODAY) == 0


def test_streak_gap_breaks_series():
    marks = {d(0), d(-1), d(-3), d(-4), d(-5)}
    assert logic.current_streak(marks, TODAY) == 2


def test_best_streak():
    marks = {d(-10), d(-9), d(-8), d(-7), d(-5), d(0), d(-1)}
    assert logic.best_streak(marks) == 4
    assert logic.best_streak(set()) == 0
    assert logic.best_streak({d(-3)}) == 1


def test_best_streak_includes_current():
    marks = {d(-i) for i in range(6)} | {d(-20), d(-19)}
    assert logic.best_streak(marks) == 6


def test_backfill_mark_restores_streak():
    marks = {d(0), d(-1), d(-3), d(-4)}
    assert logic.current_streak(marks, TODAY) == 2
    assert logic.can_mark(d(-2), TODAY)
    marks.add(d(-2))
    assert logic.current_streak(marks, TODAY) == 5
    marks.discard(d(-2))  # снятие отметки задним числом
    assert logic.current_streak(marks, TODAY) == 2


def test_can_mark_only_last_7_days():
    assert logic.can_mark(d(0), TODAY)
    assert logic.can_mark(d(-6), TODAY)
    assert not logic.can_mark(d(-7), TODAY)
    assert not logic.can_mark(d(1), TODAY)


def test_backfill_through_db(tmp_path):
    db = Database(tmp_path / "t.sqlite3")
    hid = db.add_habit("Зарядка", created_on=d(-10))
    for off in (0, -1, -3):
        db.set_mark(hid, d(off), True)
    assert logic.current_streak(db.marks(hid), TODAY) == 2
    db.set_mark(hid, d(-2), True)
    assert logic.current_streak(db.marks(hid), TODAY) == 4
    db.set_mark(hid, d(0), False)
    assert logic.current_streak(db.marks(hid), TODAY) == 3
    db.close()


# ---------- задачи ----------

def test_sort_by_deadline_then_priority():
    tasks = [
        Task(1, "без дедлайна, высокий", deadline=None, priority=logic.PRIORITY_HIGH),
        Task(2, "завтра, низкий", deadline=d(1), priority=logic.PRIORITY_LOW),
        Task(3, "завтра, высокий", deadline=d(1), priority=logic.PRIORITY_HIGH),
        Task(4, "вчера, средний", deadline=d(-1), priority=logic.PRIORITY_MEDIUM),
        Task(5, "без дедлайна, низкий", deadline=None, priority=logic.PRIORITY_LOW),
        Task(6, "завтра, средний", deadline=d(1), priority=logic.PRIORITY_MEDIUM),
    ]
    assert [t.id for t in logic.sort_tasks(tasks)] == [4, 3, 6, 2, 1, 5]


def test_overdue_detection():
    assert logic.is_overdue(Task(1, "a", deadline=d(-1)), TODAY)
    assert not logic.is_overdue(Task(2, "b", deadline=d(0)), TODAY)
    assert not logic.is_overdue(Task(3, "c", deadline=d(1)), TODAY)
    assert not logic.is_overdue(Task(4, "d", deadline=None), TODAY)
    assert not logic.is_overdue(Task(5, "e", deadline=d(-5), done=True), TODAY)


def test_due_today_detection():
    assert logic.is_due_today(Task(1, "a", deadline=d(0)), TODAY)
    assert not logic.is_due_today(Task(2, "b", deadline=d(-1)), TODAY)
    assert not logic.is_due_today(Task(3, "c", deadline=d(0), done=True), TODAY)


def test_filter_tasks():
    tasks = [Task(1, "a"), Task(2, "b", done=True)]
    assert [t.id for t in logic.filter_tasks(tasks, logic.FILTER_ACTIVE)] == [1]
    assert [t.id for t in logic.filter_tasks(tasks, logic.FILTER_DONE)] == [2]
    assert [t.id for t in logic.filter_tasks(tasks, logic.FILTER_ALL)] == [1, 2]


# ---------- статистика ----------

def test_completion_by_day():
    habits = [Habit(1, "a", False, d(-30)), Habit(2, "b", False, d(-1)), Habit(3, "x", True, d(-30))]
    marks = {1: {d(0), d(-2)}, 2: {d(0)}, 3: {d(-2)}}
    stats = dict(logic.completion_by_day(habits, marks, TODAY, days=28))
    assert len(stats) == 28
    assert stats[d(0)] == 100.0
    assert stats[d(-1)] == 0.0
    assert stats[d(-2)] == 100.0  # привычки 2 ещё не было, архивная не учитывается
    assert stats[d(-3)] == 0.0


def test_completed_tasks_by_week():
    # TODAY = вс 01.11.2026, неделя начинается пн 26.10.2026
    tasks = [
        Task(1, "a", done=True, completed_on=d(0)),
        Task(2, "b", done=True, completed_on=d(-6)),   # пн той же недели
        Task(3, "c", done=True, completed_on=d(-7)),   # прошлая неделя
        Task(4, "d", done=True, completed_on=d(-100)),  # за пределами 8 недель
        Task(5, "e", done=False),
    ]
    weeks = logic.completed_tasks_by_week(tasks, TODAY, weeks=8)
    assert len(weeks) == 8
    assert weeks[-1] == (date(2026, 10, 26), 2)
    assert weeks[-2] == (date(2026, 10, 19), 1)
    assert sum(c for _, c in weeks) == 3


def test_summary():
    habits = [Habit(1, "a", False, d(-30)), Habit(2, "b", False, d(-30)), Habit(3, "x", True, d(-30))]
    marks = {1: {d(-1), d(-2)}, 2: {d(0)}, 3: {d(0), d(-1), d(-2), d(-3)}}
    tasks = [Task(1, "a", deadline=d(-1)), Task(2, "b", deadline=d(-2), done=True), Task(3, "c")]
    s = logic.summary(habits, marks, tasks, TODAY)
    assert (s.active_habits, s.best_current_streak, s.overdue_tasks) == (2, 2, 1)


# ---------- архив и удаление задач ----------

def test_archived_tasks_filtered_and_not_overdue():
    tasks = [
        Task(1, "активная", deadline=d(-1)),
        Task(2, "выполнена", done=True),
        Task(3, "в архиве", deadline=d(-1), archived=True),
        Task(4, "архив, выполнена", done=True, archived=True),
    ]
    ids = lambda mode: [t.id for t in logic.filter_tasks(tasks, mode)]
    assert ids(logic.FILTER_ACTIVE) == [1]
    assert ids(logic.FILTER_DONE) == [2]
    assert ids(logic.FILTER_ALL) == [1, 2]
    assert ids(logic.FILTER_ARCHIVED) == [3, 4]
    assert not logic.is_overdue(tasks[2], TODAY)
    assert not logic.is_due_today(Task(5, "x", deadline=TODAY, archived=True), TODAY)
    assert logic.summary([], {}, tasks, TODAY).overdue_tasks == 1


def test_task_archive_and_delete_in_db(tmp_path):
    db = Database(tmp_path / "t.sqlite3")
    a = db.add_task(Task(0, "A"))
    b = db.add_task(Task(0, "B"))
    db.set_task_archived(a, True)
    assert db.get_task(a).archived is True
    db.update_task(db.get_task(a))  # редактирование не сбрасывает архив
    assert db.get_task(a).archived is True
    db.set_task_archived(a, False)
    assert db.get_task(a).archived is False
    db.delete_task(b)
    assert [t.id for t in db.list_tasks()] == [a]
    db.close()


def test_migration_adds_archived_column(tmp_path):
    import sqlite3
    path = tmp_path / "old.sqlite3"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,"
                 " description TEXT NOT NULL DEFAULT '', deadline TEXT,"
                 " priority INTEGER NOT NULL DEFAULT 1, done INTEGER NOT NULL DEFAULT 0,"
                 " completed_on TEXT)")
    conn.execute("INSERT INTO tasks(title) VALUES ('старая')")
    conn.commit()
    conn.close()
    db = Database(path)
    assert [(t.title, t.archived) for t in db.list_tasks()] == [("старая", False)]
    db.close()
