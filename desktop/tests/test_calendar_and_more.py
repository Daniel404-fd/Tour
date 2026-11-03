import sqlite3
from datetime import date, datetime, timedelta

from tracker import cal, logic
from tracker.cal import Event
from tracker.db import Database
from tracker.logic import Goal, GoalStep, Note

D = datetime(2026, 11, 2, 10, 0)   # понедельник


def ev(**kw):
    base = dict(id=1, title="X", start=D, end=D + timedelta(hours=1))
    base.update(kw)
    return Event(**base)


def starts(events, a, b):
    return [o.start for o in cal.occurrences(events, a, b)]


# ---------------------------------------------------------------- повторы

def test_single_event_in_range():
    e = ev()
    assert starts([e], datetime(2026, 11, 2), datetime(2026, 11, 3)) == [D]
    assert starts([e], datetime(2026, 11, 3), datetime(2026, 11, 4)) == []


def test_daily_with_interval_until_and_exdate():
    e = ev(freq=cal.FREQ_DAILY, interval=2, until=date(2026, 11, 10), exdates=[date(2026, 11, 6)])
    got = [d.date() for d in starts([e], datetime(2026, 11, 1), datetime(2026, 12, 1))]
    assert got == [date(2026, 11, 2), date(2026, 11, 4), date(2026, 11, 8), date(2026, 11, 10)]


def test_weekly_on_weekdays():
    e = ev(freq=cal.FREQ_WEEKLY, weekdays=[0, 2, 4])   # пн, ср, пт
    got = [d.day for d in starts([e], datetime(2026, 11, 1), datetime(2026, 11, 15))]
    assert got == [2, 4, 6, 9, 11, 13]


def test_biweekly():
    e = ev(freq=cal.FREQ_WEEKLY, interval=2)
    got = [d.day for d in starts([e], datetime(2026, 11, 1), datetime(2026, 12, 1))]
    assert got == [2, 16, 30]


def test_monthly_31st_skips_short_months_like_google():
    e = ev(start=datetime(2026, 1, 31, 9), end=datetime(2026, 1, 31, 10), freq=cal.FREQ_MONTHLY)
    got = [d.month for d in starts([e], datetime(2026, 1, 1), datetime(2026, 8, 1))]
    assert got == [1, 3, 5, 7]


def test_yearly_birthday():
    e = ev(start=datetime(2020, 5, 9), end=datetime(2020, 5, 10), all_day=True, freq=cal.FREQ_YEARLY)
    assert starts([e], datetime(2026, 1, 1), datetime(2027, 1, 1)) == [datetime(2026, 5, 9)]


def test_multi_day_event_visible_on_every_day():
    e = ev(start=datetime(2026, 11, 2), end=datetime(2026, 11, 5), all_day=True)
    occ = cal.occurrences([e], datetime(2026, 11, 1), datetime(2026, 11, 8))
    assert [len(cal.on_day(occ, date(2026, 11, d))) for d in range(1, 7)] == [0, 1, 1, 1, 0, 0]


def test_event_started_before_range_is_included():
    e = ev(start=datetime(2026, 11, 1, 23), end=datetime(2026, 11, 2, 2))
    assert len(cal.occurrences([e], datetime(2026, 11, 2), datetime(2026, 11, 3))) == 1


# ---------------------------------------------------------------- раскладка

def test_layout_overlapping_events_share_width():
    # 9-11 и 9:30-10 пересекаются; 10-12 занимает колонку, освободившуюся в 10:00; 13-14 отдельно
    items = [(9, 11), (10, 12), (13, 14), (9.5, 10)]
    lay = cal.layout_columns(items)
    assert lay[2] == (0, 1)
    assert lay[0] == (0, 2) and lay[3] == (1, 2) and lay[1] == (1, 2)


def test_layout_reuses_free_column():
    # длинное событие — в первую колонку, как в Google
    lay = cal.layout_columns([(9, 10), (9, 12), (10, 11)])
    assert lay[1] == (0, 2) and lay[0] == (1, 2) and lay[2] == (1, 2)


def test_month_grid_starts_monday():
    g = cal.month_grid(2026, 11)
    assert len(g) == 6 and g[0][0] == date(2026, 10, 26) and g[0][0].weekday() == 0


def test_snap_and_reminders():
    assert cal.snap(datetime(2026, 11, 2, 10, 7)) == datetime(2026, 11, 2, 10, 0)
    assert cal.snap(datetime(2026, 11, 2, 10, 8)) == datetime(2026, 11, 2, 10, 15)
    e = ev(reminder=10)
    occ = cal.occurrences([e], datetime(2026, 11, 2), datetime(2026, 11, 3))
    now = D - timedelta(minutes=10)
    assert cal.due_reminders(occ, now, timedelta(minutes=1), set()) == occ
    assert cal.due_reminders(occ, now, timedelta(minutes=1), {occ[0].key}) == []
    assert cal.due_reminders(occ, now - timedelta(minutes=5), timedelta(minutes=1), set()) == []


def test_recurrence_text():
    assert cal.recurrence_text(ev(freq=cal.FREQ_WEEKLY, weekdays=[0, 2])) == "Каждую неделю: пн, ср"


# ---------------------------------------------------------------- БД

def test_events_roundtrip_in_db(tmp_path):
    db = Database(tmp_path / "t.sqlite3")
    [personal] = db.list_calendars()
    assert personal.name == "Личное"
    e = ev(id=0, calendar_id=personal.id, freq=cal.FREQ_WEEKLY, weekdays=[0, 3],
           until=date(2026, 12, 31), exdates=[date(2026, 11, 5)], reminder=15, location="Офис")
    eid = db.add_event(e)
    got = db.get_event(eid)
    assert (got.title, got.start, got.end, got.weekdays, got.until, got.exdates, got.reminder,
            got.location) == ("X", D, D + timedelta(hours=1), [0, 3], date(2026, 12, 31),
                              [date(2026, 11, 5)], 15, "Офис")
    got.title = "Y"
    db.update_event(got)
    assert db.get_event(eid).title == "Y"
    db.delete_calendar(personal.id)
    assert db.list_events() == []
    db.close()


def test_prefs(tmp_path):
    db = Database(tmp_path / "t.sqlite3")
    assert db.get_pref("upcoming_days", "4") == "4"
    db.set_pref("upcoming_days", "7")
    db.set_pref("upcoming_days", "14")
    assert db.get_pref("upcoming_days") == "14"
    db.close()


# ---------------------------------------------------------------- финансовые цели

def test_financial_goal_progress():
    g = Goal(1, "Отпуск", financial=True, target_amount=100_000)
    assert logic.goal_progress(g, [], saved=25_000) == 0.25
    steps = [GoalStep(1, 1, "a", True), GoalStep(2, 1, "b")]
    assert logic.goal_progress(g, steps, saved=25_000) == (0.25 + 0.5) / 2
    assert logic.goal_progress(g, [], saved=150_000) == 1.0      # перевыполнили — 100 %
    assert logic.goal_progress(g, [], saved=-5) == 0.0
    plain = Goal(2, "Обычная")
    assert logic.goal_progress(plain, steps, saved=999) == 0.5   # деньги не учитываются


def test_money_format_and_parse():
    assert logic.format_money(1234567) == "1 234 567 ₽"
    assert logic.format_money(1234.5) == "1 234,50 ₽"
    assert logic.format_money(-500) == "−500 ₽"
    assert logic.parse_money("12 500,75 ₽") == 12500.75
    assert logic.parse_money("−300") == -300
    assert logic.parse_money("abc") is None


def test_contributions_in_db(tmp_path):
    db = Database(tmp_path / "t.sqlite3")
    gid = db.add_goal(Goal(0, "Ноутбук", financial=True, target_amount=90_000))
    db.add_contribution(gid, 30_000, date(2026, 10, 1), "зарплата")
    cid = db.add_contribution(gid, 15_000, date(2026, 11, 1))
    db.add_contribution(gid, -5_000, date(2026, 11, 2), "сняли")
    assert db.saved_amounts()[gid] == 40_000
    assert [c.amount for c in db.contributions(gid)] == [-5_000, 15_000, 30_000]
    db.delete_contribution(cid)
    assert db.saved_amounts()[gid] == 25_000
    g = db.get_goal(gid)
    assert g.financial and g.target_amount == 90_000
    db.delete_goal(gid)
    assert db.saved_amounts() == {}
    db.close()


# ---------------------------------------------------------------- папки заметок

def test_note_folders(tmp_path):
    db = Database(tmp_path / "t.sqlite3")
    work = db.add_folder("Работа")
    db.add_folder("дом")
    n1 = db.add_note("План", folder_id=work)
    n2 = db.add_note("Покупки")
    assert [f.name for f in db.list_folders()] == ["дом", "Работа"]
    notes = db.list_notes()
    assert [n.id for n in logic.filter_by_folder(notes, work)] == [n1]
    assert [n.id for n in logic.filter_by_folder(notes, logic.FOLDER_NONE)] == [n2]
    assert len(logic.filter_by_folder(notes, logic.FOLDER_ALL)) == 2
    db.move_note(n2, work)
    assert db.get_note(n2).folder_id == work
    db.delete_folder(work)
    assert {n.folder_id for n in db.list_notes()} == {None}   # заметки не пропали
    db.close()


def test_migration_from_v22(tmp_path):
    """База версии 2.2 (без папок, финансов, календаря) открывается и дополняется."""
    path = tmp_path / "old.sqlite3"
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE goals (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '', target_date TEXT, done INTEGER NOT NULL DEFAULT 0,
            archived INTEGER NOT NULL DEFAULT 0, created_on TEXT NOT NULL, completed_on TEXT);
        CREATE TABLE notes (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL DEFAULT '',
            body TEXT NOT NULL DEFAULT '', pinned INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        INSERT INTO goals(title, created_on) VALUES ('Старая цель', '2026-01-01');
        INSERT INTO notes(title, created_at, updated_at) VALUES ('Старая заметка', 'x', 'x');
    """)
    conn.commit()
    conn.close()
    db = Database(path)
    [g] = db.list_goals()
    assert (g.title, g.financial, g.target_amount) == ("Старая цель", False, 0.0)
    [n] = db.list_notes()
    assert (n.title, n.folder_id) == ("Старая заметка", None)
    assert len(db.list_calendars()) == 1
    db.close()
