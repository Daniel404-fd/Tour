"""Слияние данных двух устройств."""
import sqlite3
import time
from datetime import date, datetime, timedelta

from tracker import sync
from tracker.cal import Event
from tracker.db import Database
from tracker.logic import Goal, Note, Task


def pair(tmp_path):
    return Database(tmp_path / "pc.sqlite3"), Database(tmp_path / "phone.sqlite3")


def exchange(a: Database, b: Database, rounds: int = 1):
    for _ in range(rounds):
        pa = sync.decode(a.sync_export("A"))
        pb = sync.decode(b.sync_export("B"))
        a.sync_merge([pb])
        b.sync_merge([pa])


def tick():
    time.sleep(0.003)   # метки времени с точностью до миллисекунды


def snapshot(db: Database):
    return {
        "habits": sorted((h.name, h.archived) for h in db.list_habits(include_archived=True)),
        "marks": sorted((h.name, d) for h in db.list_habits(include_archived=True)
                        for d in db.marks(h.id)),
        "tasks": sorted((t.title, t.done, t.deadline,
                         next((x.name for x in db.list_topics() if x.id == t.topic_id), None))
                        for t in db.list_tasks()),
        "notes": sorted((n.title, n.body, next((f.name for f in db.list_folders() if f.id == n.folder_id), None))
                        for n in db.list_notes()),
        "goals": sorted((g.title, g.financial, g.target_amount) for g in db.list_goals()),
        "saved": sorted((next(g.title for g in db.list_goals() if g.id == k), v)
                        for k, v in db.saved_amounts().items()),
        "steps": sorted((s.title, s.done) for st in db.all_steps().values() for s in st),
        "calendars": sorted(c.name for c in db.list_calendars()),
        "events": sorted((e.title, e.start, e.freq,
                          next(c.name for c in db.list_calendars() if c.id == e.calendar_id))
                         for e in db.list_events()),
    }


def test_existing_data_gets_sync_ids(tmp_path):
    db = Database(tmp_path / "t.sqlite3")
    db.add_task(Task(0, "A"))
    row = db.conn.execute("SELECT sync_uid, sync_ts FROM tasks").fetchone()
    assert len(row[0]) == 32 and row[1].endswith("Z")
    [c] = db.list_calendars()
    assert db.conn.execute("SELECT sync_uid FROM calendars").fetchone()[0] == sync.DEFAULT_CALENDAR_UID


def test_update_bumps_timestamp_and_delete_leaves_tombstone(tmp_path):
    db = Database(tmp_path / "t.sqlite3")
    tid = db.add_task(Task(0, "A"))
    ts1 = db.conn.execute("SELECT sync_ts FROM tasks").fetchone()[0]
    tick()
    t = db.get_task(tid); t.title = "B"; db.update_task(t)
    ts2 = db.conn.execute("SELECT sync_ts FROM tasks").fetchone()[0]
    assert ts2 > ts1
    uid = db.conn.execute("SELECT sync_uid FROM tasks").fetchone()[0]
    db.delete_task(tid)
    assert db.conn.execute("SELECT tbl FROM sync_tombstones WHERE uid = ?", (uid,)).fetchone() == ("tasks",)


def test_two_devices_converge(tmp_path):
    pc, phone = pair(tmp_path)
    home = pc.add_topic("Дом", "#008000")
    pc.add_task(Task(0, "Помыть окна", topic_id=home, deadline=date(2026, 11, 5)))
    h = pc.add_habit("Зарядка")
    pc.set_mark(h, date(2026, 11, 1), True)
    f = pc.add_folder("Идеи")
    pc.add_note("Отпуск", "Казань", folder_id=f)
    g = pc.add_goal(Goal(0, "Ноутбук", financial=True, target_amount=90000))
    pc.add_contribution(g, 30000, date(2026, 10, 1))
    pc.add_step(g, "Выбрать модель")
    [cal_] = pc.list_calendars()
    pc.add_event(Event(0, "Планёрка", datetime(2026, 11, 2, 10), datetime(2026, 11, 2, 11),
                       calendar_id=cal_.id, freq="weekly", weekdays=[0]))
    phone.add_habit("Чтение")
    phone.add_task(Task(0, "Купить молоко"))
    exchange(pc, phone)
    assert snapshot(pc) == snapshot(phone)
    s = snapshot(phone)
    assert ("Помыть окна", False, date(2026, 11, 5), "Дом") in s["tasks"]
    assert ("Отпуск", "Казань", "Идеи") in s["notes"]
    assert s["saved"] == [("Ноутбук", 30000)]
    assert s["calendars"] == ["Личное"]                  # общий календарь не задвоился
    assert ("Зарядка", date(2026, 11, 1)) in s["marks"]


def test_concurrent_edits_last_writer_wins_per_record(tmp_path):
    pc, phone = pair(tmp_path)
    a = pc.add_task(Task(0, "Задача 1"))
    b = pc.add_task(Task(0, "Задача 2"))
    exchange(pc, phone)
    # на ПК меняем первую, на телефоне — вторую: оба изменения должны выжить
    t = pc.get_task(a); t.title = "Задача 1 (ПК)"; pc.update_task(t)
    tick()
    pt = next(x for x in phone.list_tasks() if x.title == "Задача 2"); pt.done = True; phone.update_task(pt)
    exchange(pc, phone)
    assert snapshot(pc) == snapshot(phone)
    titles = {x.title: x.done for x in pc.list_tasks()}
    assert titles == {"Задача 1 (ПК)": False, "Задача 2": True}
    # одну и ту же запись правили оба — побеждает более позднее
    t = pc.get_task(a); t.title = "раньше"; pc.update_task(t)
    tick()
    pt = next(x for x in phone.list_tasks() if x.title == "Задача 1 (ПК)"); pt.title = "позже"; phone.update_task(pt)
    exchange(pc, phone)
    assert pc.get_task(a).title == "позже"
    assert snapshot(pc) == snapshot(phone)


def test_deletions_propagate_and_do_not_resurrect(tmp_path):
    pc, phone = pair(tmp_path)
    g = pc.add_goal(Goal(0, "Цель"))
    pc.add_step(g, "Шаг")
    pc.add_contribution(g, 100) if False else None
    h = pc.add_habit("Бег")
    pc.set_mark(h, date(2026, 11, 1), True)
    exchange(pc, phone)
    tick()
    pc.delete_goal(g)                                   # каскадом удалятся и шаги
    ph = next(x for x in phone.list_habits() if x.name == "Бег")
    phone.set_mark(ph.id, date(2026, 11, 1), False)     # снятие отметки на телефоне
    exchange(pc, phone, rounds=2)
    assert pc.list_goals() == [] and phone.list_goals() == []
    assert phone.all_steps() == {}
    assert pc.marks(h) == set()
    assert snapshot(pc) == snapshot(phone)


def test_edit_after_delete_wins(tmp_path):
    pc, phone = pair(tmp_path)
    a = pc.add_task(Task(0, "X"))
    exchange(pc, phone)
    pc.delete_task(a)
    tick()
    pt = phone.list_tasks()[0]; pt.title = "X изменена позже"; phone.update_task(pt)
    exchange(pc, phone)
    assert [t.title for t in pc.list_tasks()] == ["X изменена позже"]
    assert snapshot(pc) == snapshot(phone)


def test_same_habit_mark_on_both_devices_is_one(tmp_path):
    pc, phone = pair(tmp_path)
    h = pc.add_habit("Вода")
    exchange(pc, phone)
    ph = phone.list_habits()[0]
    pc.set_mark(h, date(2026, 11, 3), True)
    phone.set_mark(ph.id, date(2026, 11, 3), True)
    exchange(pc, phone)
    assert pc.marks(h) == {date(2026, 11, 3)}
    assert phone.marks(ph.id) == {date(2026, 11, 3)}


def test_merge_is_idempotent_and_survives_reopen(tmp_path):
    pc, phone = pair(tmp_path)
    pc.add_task(Task(0, "A"))
    payload = sync.decode(pc.sync_export("A"))
    s1 = phone.sync_merge([payload])
    s2 = phone.sync_merge([payload])
    assert s1.added == 1 and not s2.changed
    phone.close()
    again = Database(tmp_path / "phone.sqlite3")
    assert [t.title for t in again.list_tasks()] == ["A"]
    assert not again.sync_merge([payload]).changed


def test_three_devices(tmp_path):
    a, b, c = (Database(tmp_path / f"{n}.sqlite3") for n in "abc")
    a.add_task(Task(0, "от A"))
    b.add_task(Task(0, "от B"))
    c.add_task(Task(0, "от C"))
    pays = lambda: [sync.decode(d.sync_export(n)) for d, n in ((a, "a"), (b, "b"), (c, "c"))]
    for _ in range(2):
        p = pays()
        for d in (a, b, c):
            d.sync_merge(p)
    assert snapshot(a) == snapshot(b) == snapshot(c)
    assert len(a.list_tasks()) == 3


def test_device_id_is_stable_and_own_file_ignored(tmp_path):
    db = Database(tmp_path / "t.sqlite3")
    did = db.device_id()
    assert did == db.device_id()
    own = sync.decode(db.sync_export("me"))
    assert own["device"] == did
    assert not db.sync_merge([own]).changed


def test_equal_timestamps_still_converge(tmp_path):
    """Правки в одну и ту же миллисекунду: устройства всё равно приходят к одной версии."""
    pc, phone = pair(tmp_path)
    a = pc.add_task(Task(0, "X"))
    exchange(pc, phone)
    t = pc.get_task(a); t.title = "версия ПК"; pc.update_task(t)
    pt = phone.list_tasks()[0]; pt.title = "версия телефона"; phone.update_task(pt)
    same = "2030-01-01T00:00:00.000Z"
    for d in (pc, phone):
        d.conn.execute("UPDATE tasks SET sync_ts = ?", (same,))
        d.conn.commit()
    exchange(pc, phone)
    assert [x.title for x in pc.list_tasks()] == [x.title for x in phone.list_tasks()]
