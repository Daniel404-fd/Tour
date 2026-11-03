"""Правка повторяющихся событий: только это / это и следующие / все; перетаскивание мышью."""
import os
from datetime import date, datetime, time, timedelta

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication, QDialog

from tracker import cal
from tracker.cal import Event
from tracker.db import Database


@pytest.fixture
def page(tmp_path, monkeypatch):
    app = QApplication.instance() or QApplication([])
    from tracker.ui import calendar_tab, theme
    theme.install(app)
    db = Database(tmp_path / "t.sqlite3")
    p = calendar_tab.CalendarPage(db, lambda *a, **k: None)
    p.resize(1200, 800)
    return p, db, calendar_tab, monkeypatch


MON = datetime(2026, 11, 2, 10, 0)


def _series(db):
    [c] = db.list_calendars()
    eid = db.add_event(Event(0, "Планёрка", MON, MON + timedelta(minutes=30), calendar_id=c.id,
                             freq=cal.FREQ_DAILY))
    return db.get_event(eid)


def _occ(db, day):
    occs = cal.occurrences(db.list_events(), datetime.combine(day, time.min),
                           datetime.combine(day, time.min) + timedelta(days=1))
    return occs


def _scope(monkeypatch, mod, scope):
    monkeypatch.setattr(mod.ScopeDialog, "exec", lambda self: QDialog.Accepted)
    monkeypatch.setattr(mod.ScopeDialog, "scope", lambda self: scope)


def test_move_only_this_occurrence(page):
    p, db, mod, mp = page
    s = _series(db)
    _scope(mp, mod, mod.ScopeDialog.THIS)
    [o] = _occ(db, date(2026, 11, 4))
    p.change_occurrence(o, o.start + timedelta(hours=2), o.end + timedelta(hours=2))
    [moved] = _occ(db, date(2026, 11, 4))
    assert moved.start.hour == 12 and not moved.event.recurring
    assert _occ(db, date(2026, 11, 5))[0].start.hour == 10          # остальные не тронуты
    assert date(2026, 11, 4) in db.get_event(s.id).exdates


def test_edit_this_and_following(page):
    p, db, mod, mp = page
    s = _series(db)
    _scope(mp, mod, mod.ScopeDialog.FOLLOWING)
    [o] = _occ(db, date(2026, 11, 6))
    edited = Event(**{**s.__dict__, "title": "Стендап", "start": o.start, "end": o.end})
    p.apply_edit(db.get_event(s.id), o, edited)
    assert _occ(db, date(2026, 11, 5))[0].event.title == "Планёрка"
    assert _occ(db, date(2026, 11, 6))[0].event.title == "Стендап"
    assert _occ(db, date(2026, 11, 20))[0].event.title == "Стендап"
    assert db.get_event(s.id).until == date(2026, 11, 5)


def test_move_all_events(page):
    p, db, mod, mp = page
    s = _series(db)
    _scope(mp, mod, mod.ScopeDialog.ALL)
    [o] = _occ(db, date(2026, 11, 10))
    p.change_occurrence(o, o.start + timedelta(minutes=30), o.end + timedelta(minutes=30))
    assert all(x.start.time() == time(10, 30) for x in
               cal.occurrences(db.list_events(), datetime(2026, 11, 2), datetime(2026, 11, 20)))
    assert len(db.list_events()) == 1


def test_delete_only_this(page):
    p, db, mod, mp = page
    s = _series(db)
    _scope(mp, mod, mod.ScopeDialog.THIS)
    [o] = _occ(db, date(2026, 11, 3))
    p.delete_occurrence(db.get_event(s.id), o)
    assert _occ(db, date(2026, 11, 3)) == []
    assert len(_occ(db, date(2026, 11, 4))) == 1


def test_drag_to_create_and_move_in_week_grid(page, monkeypatch):
    p, db, mod, mp = page
    mp.setattr(mod.EventDialog, "exec", lambda self: QDialog.Rejected)   # окно создания не открываем
    created = []
    p.anchor = date(2026, 11, 2)
    p.set_view("week")
    g = p.grid
    g.resize(1000, 24 * mod.HOUR_H)
    g.set_data(p.days(), [])
    g.createRequested.connect(lambda s, e, a: created.append((s, e, a)))

    class Ev:
        def __init__(self, x, y, b=Qt.LeftButton):
            self._p = QPointF(x, y); self._b = b
        def position(self): return self._p
        def button(self): return self._b

    cw = g.col_w()
    x = mod.GUTTER + cw * 2 + 10                     # среда
    g.mousePressEvent(Ev(x, 9 * mod.HOUR_H + 2))
    g.mouseMoveEvent(Ev(x, 11 * mod.HOUR_H - 5))
    g.mouseReleaseEvent(Ev(x, 11 * mod.HOUR_H - 5))
    (s, e, all_day), = created
    assert s == datetime(2026, 11, 4, 9, 0) and e == datetime(2026, 11, 4, 11, 0) and not all_day

    # перенос: событие во вторник 14:00 тянем на четверг 16:00
    [c] = db.list_calendars()
    db.add_event(Event(0, "Созвон", datetime(2026, 11, 3, 14), datetime(2026, 11, 3, 15), calendar_id=c.id))
    p.refresh()
    g.resize(1000, 24 * mod.HOUR_H)
    g.grab()   # зоны событий для мыши считаются при отрисовке
    changes = []
    g.changeRequested.connect(lambda o, s2, e2: changes.append((s2, e2)))
    x1 = mod.GUTTER + cw * 1 + 20
    x2 = mod.GUTTER + cw * 3 + 20
    g.mousePressEvent(Ev(x1, 14 * mod.HOUR_H + 10))
    g.mouseMoveEvent(Ev(x2, 16 * mod.HOUR_H + 10))
    g.mouseReleaseEvent(Ev(x2, 16 * mod.HOUR_H + 10))
    assert changes == [(datetime(2026, 11, 5, 16), datetime(2026, 11, 5, 17))]
