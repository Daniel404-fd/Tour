"""Проверка совместимости синхронизации ПК ↔ Android.

  python tools/interop.py make  <out.json.gz>   — сделать файл «как с ПК» (фикстура для теста Android)
  python tools/interop.py check <in.json.gz>    — слить файл, сделанный Android, в пустую базу ПК и проверить
"""
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "desktop"))
from tracker import sync  # noqa: E402
from tracker.cal import Event  # noqa: E402
from tracker.db import Database  # noqa: E402
from tracker.logic import Goal, Task  # noqa: E402


def make(out: Path):
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "pc.sqlite3")
        h = db.add_habit("Зарядка", created_on=date(2026, 1, 1))
        db.set_mark(h, date(2026, 1, 2), True)
        tp = db.add_topic("Работа", "#000080")
        tid = db.add_task(Task(0, "Сдать отчёт", deadline=date(2026, 2, 1), topic_id=tp))
        db.add_subtask(tid, "Собрать цифры")
        db.set_subtask_done(db.add_subtask(tid, "Отправить"), True)
        g = db.add_goal(Goal(0, "Отпуск", financial=True, target_amount=100000.0))
        db.add_contribution(g, 2500.5, date(2026, 1, 3), "аванс")
        db.add_step(g, "Выбрать страну")
        b = db.add_board("Работа 1", "#1D4ED8")
        cols = db.list_columns(b)
        db.add_card(b, cols[1].id, "Ревью договора")
        db.add_note("Контакты", "Иван", board_id=b)
        f = db.add_folder("Идеи")
        db.add_note("Ёлка", "Купить игрушки", folder_id=f)
        cal = db.list_calendars()[0].id
        db.add_event(Event(0, "Йога", datetime(2026, 1, 5, 19, 0), datetime(2026, 1, 5, 20, 0),
                           calendar_id=cal, freq="weekly", weekdays=[0, 2]))
        out.write_bytes(db.sync_export("ПК"))
    print("ok:", out)


def check(src: Path):
    payload = sync.decode(src.read_bytes())
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "pc.sqlite3")
        db.sync_merge([payload])
        habits = [x.name for x in db.list_habits()]
        assert "Пробежка" in habits, habits
        hid = next(x.id for x in db.list_habits() if x.name == "Пробежка")
        assert date(2026, 3, 1) in db.marks(hid)
        t = next(t for t in db.list_tasks() if t.title == "Позвонить маме")
        assert [(x.title, x.done) for x in db.subtasks(t.id)] == [("Купить цветы", True), ("Позвонить", False)]
        assert any(n.title == "С телефона" for n in db.list_notes())
        assert any(e.title == "Врач" for e in db.list_events())
        g = next(x for x in db.list_goals() if x.title == "Машина")
        assert abs(db.saved_amounts()[g.id] - 1000.0) < 0.01
        assert [c.name for c in db.list_calendars()].count("Личное") == 1, "основной календарь задвоился"
        [b] = db.list_boards()
        assert b.name == "Фриланс"
        cols = db.list_columns(b.id)
        [card] = db.list_tasks(board_id=b.id)
        assert card.title == "Логотип" and card.column_id == cols[2].id and card.done
        assert all(t.board_id is None for t in db.list_tasks())
        assert [n.title for n in db.list_notes(board_id=b.id)] == ["Бриф"]
    print("ok: Android → ПК")


if __name__ == "__main__":
    {"make": make, "check": check}[sys.argv[1]](Path(sys.argv[2]))
