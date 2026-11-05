"""Версия 2.7: доски (канбан) с заметками, своя папка данных, отложенная запись, плашки листаются."""
from datetime import date

import pytest

from tracker import logic, relocate, sync
from tracker.db import Database
from tracker.logic import Task
from tests.test_v25 import app, keep  # noqa: F401


# ---------------------------------------------------------------- доски: данные

def test_board_defaults_and_separation(tmp_path):
    db = Database(tmp_path / "t.sqlite3")
    db.add_task(Task(0, "Дома"))
    b = db.add_board("Работа 1")
    cols = db.list_columns(b)
    assert [c.name for c in cols] == ["К выполнению", "В работе", "Готово"]
    assert [c.is_done for c in cols] == [False, False, True]
    db.add_card(b, cols[0].id, "Созвон")
    assert [t.title for t in db.list_tasks()] == ["Дома"]               # обычный список — без карточек
    assert [t.title for t in db.list_tasks(board_id=b)] == ["Созвон"]
    assert len(db.list_tasks(include_boards=True)) == 2
    n = db.add_note("Контакты", board_id=b)
    db.add_note("Обычная")
    assert [x.title for x in db.list_notes()] == ["Обычная"]
    assert [x.id for x in db.list_notes(board_id=b)] == [n]


def test_move_card_order_and_done(tmp_path):
    db = Database(tmp_path / "t.sqlite3")
    b = db.add_board("Работа")
    todo, doing, done = db.list_columns(b)
    a = db.add_card(b, todo.id, "A")
    bb = db.add_card(b, todo.id, "B")
    c = db.add_card(b, todo.id, "C")
    db.move_card(c, todo.id, 0)
    assert [t.title for t in db.cards_in(todo.id)] == ["C", "A", "B"]
    db.move_card(a, todo.id, 2)                       # в самый низ
    assert [t.title for t in db.cards_in(todo.id)] == ["C", "B", "A"]
    db.move_card(bb, done.id, 0)
    t = db.get_task(bb)
    assert t.done and t.completed_on == date.today()
    db.move_card(bb, doing.id, 0)
    assert not db.get_task(bb).done
    for _ in range(60):                               # много вставок в одно место — порядок не ломается
        db.move_card(c, todo.id, 1)
        db.move_card(c, todo.id, 0)
    assert [t.title for t in db.cards_in(todo.id)] == ["C", "A"]


def test_complete_task_moves_card(tmp_path):
    db = Database(tmp_path / "t.sqlite3")
    b = db.add_board("Работа")
    todo, _, done = db.list_columns(b)
    tid = db.add_card(b, todo.id, "Отчёт")
    db.complete_task(tid)
    assert db.get_task(tid).column_id == done.id and db.get_task(tid).done
    db.complete_task(tid, False)
    assert db.get_task(tid).column_id == todo.id and not db.get_task(tid).done
    plain = db.add_task(Task(0, "Хлеб"))
    db.complete_task(plain)
    assert db.get_task(plain).done


def test_delete_column_moves_cards_and_board_cascade(tmp_path):
    db = Database(tmp_path / "t.sqlite3")
    b = db.add_board("Работа")
    todo, doing, done = db.list_columns(b)
    tid = db.add_card(b, doing.id, "X")
    db.add_subtask(tid, "шаг")
    db.delete_column(doing.id, done.id)
    assert db.get_task(tid).column_id == done.id and db.get_task(tid).done
    db.add_note("n", board_id=b)
    db.delete_board(b)
    assert db.list_tasks(include_boards=True) == [] and db.all_subtasks() == {}
    assert db.list_notes(board_id=b) == [] and db.list_boards() == []


def test_boards_sync_both_ways(tmp_path):
    pc, ph = Database(tmp_path / "pc.sqlite3"), Database(tmp_path / "ph.sqlite3")
    b = pc.add_board("Работа 1", "#1D4ED8")
    todo, doing, _ = pc.list_columns(b)
    tid = pc.add_card(b, todo.id, "Созвон", deadline=date(2026, 11, 10))
    pc.add_note("Контакты", "Иван", board_id=b)
    ph.sync_merge([sync.decode(pc.sync_export("ПК"))])
    [pb] = ph.list_boards()
    assert pb.name == "Работа 1"
    pcols = ph.list_columns(pb.id)
    [card] = ph.list_tasks(board_id=pb.id)
    assert card.column_id == pcols[0].id and ph.list_tasks() == []
    assert ph.list_notes(board_id=pb.id)[0].body == "Иван"
    ph.move_card(card.id, pcols[1].id, 0)
    pc.sync_merge([sync.decode(ph.sync_export("Телефон"))])
    assert pc.get_task(tid).column_id == doing.id


def test_old_payload_without_new_fields_keeps_board(tmp_path):
    """Файл от прежней версии (без board_id/column_id) не выкидывает карточку с доски."""
    pc, other = Database(tmp_path / "pc.sqlite3"), Database(tmp_path / "o.sqlite3")
    b = pc.add_board("Работа")
    col = pc.list_columns(b)[0]
    tid = pc.add_card(b, col.id, "Карточка")
    other.sync_merge([sync.decode(pc.sync_export("ПК"))])
    [t] = other.list_tasks(include_boards=True)
    other.conn.execute("UPDATE tasks SET title = 'Новое' WHERE id = ?", (t.id,))
    other.conn.commit()
    payload = sync.decode(other.sync_export("Старый"))
    for rec in payload["records"]["tasks"]:
        for f in ("board_id", "column_id", "position"):
            rec["data"].pop(f, None)
    pc.sync_merge([payload])
    t = pc.get_task(tid)
    assert t.title == "Новое" and t.board_id == b and t.column_id == col.id


# ---------------------------------------------------------------- доски: окно

def test_boards_page_quick_add_and_drop(tmp_path, app):
    from tracker.ui import boards_tab
    db = Database(tmp_path / "t.sqlite3")
    page = keep(boards_tab.BoardsPage(db))
    page.refresh()
    assert page.empty.isVisibleTo(page)
    page._two_jobs()
    assert [b.name for b in db.list_boards()] == ["Работа 1", "Работа 2"]
    cols = [page.cols_row.itemAt(i).widget() for i in range(page.cols_row.count())]
    cols = [c for c in cols if isinstance(c, boards_tab.ColumnWidget)]
    assert len(cols) == 3
    cols[0].add.setText("Отчёт завтра !")
    cols[0].add.returnPressed.emit()
    [t] = db.list_tasks(board_id=page.board_id)
    assert t.title == "Отчёт" and t.priority == logic.PRIORITY_HIGH
    from PySide6.QtCore import QMimeData, QByteArray, Qt
    md = QMimeData()
    md.setData(boards_tab.MIME, QByteArray(str(t.id).encode()))
    cols = [c for c in (page.cols_row.itemAt(i).widget() for i in range(page.cols_row.count()))
            if isinstance(c, boards_tab.ColumnWidget)]
    assert cols[2].list.dropMimeData(0, md, Qt.MoveAction) is False   # Qt ничего не удаляет сам
    app.processEvents()
    assert db.get_task(t.id).done and db.get_task(t.id).column_id == cols[2].column.id
    page.notes.new_note()
    page.notes.title.setText("Созвоны")
    page.notes._changed()
    page.flush()
    assert db.list_notes(board_id=page.board_id)[0].title == "Созвоны"


# ---------------------------------------------------------------- папка данных и прочее

def test_relocate_copy_and_pointer(tmp_path):
    home, new = tmp_path / "home", tmp_path / "cloud" / "Tracker"
    db = Database(home / "tracker.sqlite3")
    db.add_task(Task(0, "x"))
    (home / "backups").mkdir()
    (home / "backups" / "a.sqlite3").write_bytes(b"1")
    (home / "settings.json").write_text("{}")
    done = relocate.copy_data(home, new)
    assert "tracker.sqlite3" in done and "backups/" in done
    assert relocate.configured_dir(home) == home
    relocate.set_location(new, home)
    assert relocate.configured_dir(home) == new.resolve()
    assert [t.title for t in Database(new / "tracker.sqlite3").list_tasks()] == ["x"]
    relocate.set_location(None, home)
    assert relocate.configured_dir(home) == home
    with pytest.raises(ValueError):
        relocate.copy_data(home, home)


def test_deferred_save(tmp_path):
    db = Database(tmp_path / "t.sqlite3")
    calls = []
    db.save_later = lambda: calls.append(1)
    db.add_task(Task(0, "a"))
    db.add_task(Task(0, "b"))
    assert len(calls) == 2
    assert [t.title for t in Database(tmp_path / "t.sqlite3").list_tasks()] == []   # ещё не записано
    db.flush_save()
    assert len(Database(tmp_path / "t.sqlite3").list_tasks()) == 2


def test_chip_strip_never_squeezes(app):
    from tracker.ui import widgets as w
    strip = keep(w.ChipStrip())
    chips = [w.chip(f"Длинная тема номер {i}") for i in range(10)]
    for c in chips:
        strip.addWidget(c)
    strip.resize(300, strip.height())
    strip.show()
    app.processEvents()
    assert all(c.width() >= c.sizeHint().width() for c in chips)
    assert strip.area.horizontalScrollBar().maximum() > 0
    strip.close()


def test_sidebar_collapse_and_restore(tmp_path, app):
    from tracker.session import Session
    from tracker.ui.main_window import MainWindow, SIDEBAR_ICONS
    s = Session.open_plain(tmp_path / "d")
    win = keep(MainWindow(s))
    win.resize(1200, 800)
    win.show()
    app.processEvents()
    win.toggle_sidebar()
    import time
    for _ in range(40):
        app.processEvents()
        time.sleep(0.01)
    assert win._collapsed and win.sidebar.item(0).text() == ""
    assert win.splitter.sizes()[0] == SIDEBAR_ICONS
    assert s.db.get_pref("ui_sidebar").endswith(":1")
    win.navigate("boards")
    assert win.stack.currentWidget() is win.pages[4]
    win.close()


# ---------------------------------------------------------------- 2.7.1: правки по отзыву

def test_card_panel_subtasks_no_duplicates(tmp_path, app):
    from tracker.ui import boards_tab
    db = Database(tmp_path / "t.sqlite3")
    b = db.add_board("Работа")
    col = db.list_columns(b)[0]
    tid = db.add_card(b, col.id, "Отчёт")
    page = keep(boards_tab.BoardsPage(db))
    page.refresh()
    page.card_selected(tid)
    panel = page.card_panel
    for name in ("Собрать цифры", "Отправить"):
        panel.subs.add_edit.setText(name)
        panel.subs._add()
        app.processEvents()
    panel.subs.list.item(0).setCheckState(__import__("PySide6.QtCore", fromlist=["Qt"]).Qt.Checked)
    app.processEvents()
    assert [(s.title, s.done) for s in db.subtasks(tid)] == [("Собрать цифры", True), ("Отправить", False)]
    panel._toggle_done()
    assert db.get_task(tid).done


def test_column_add_button_and_ctrl_enter(tmp_path, app):
    from tracker.ui import boards_tab
    db = Database(tmp_path / "t.sqlite3")
    page = keep(boards_tab.BoardsPage(db))
    page._two_jobs()
    col = next(c for c in (page.cols_row.itemAt(i).widget() for i in range(page.cols_row.count()))
               if isinstance(c, boards_tab.ColumnWidget))
    col.add.setText("Позвонить")
    col.add_btn.click()
    assert [t.title for t in db.list_tasks(board_id=page.board_id)] == ["Позвонить"]


def test_message_boxes_restyled(app):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QMessageBox
    from tracker.ui import widgets as w
    seen = {}

    def check():
        box = QApplication_active()
        seen["icon"] = box.icon()
        seen["kinds"] = {b.text(): b.property("kind") for b in box.buttons()}
        seen["default"] = box.defaultButton().text()
        box.reject()

    def QApplication_active():
        from PySide6.QtWidgets import QApplication
        return next(x for x in QApplication.topLevelWidgets() if isinstance(x, QMessageBox) and x.isVisible())
    QTimer.singleShot(50, check)
    assert w.confirm(None, "Удалить карточку", "Удалить «NOVA»?") is False
    assert seen["icon"] == QMessageBox.NoIcon
    assert seen["kinds"]["Удалить"] == "dangerSolid" and seen["default"] == "Отмена"


def test_font_choice_scales_text(app):
    from tracker.ui import theme as th
    th.set_appearance({"font_size": 12})
    assert th.BASE_PT == 12 and "12.0pt" in app.styleSheet()
    fams = th.available_fonts()
    if fams:
        th.set_appearance({"font": fams[-1]})
        assert th.FONT_FAMILY == fams[-1]
    th.set_appearance({})
    assert th.BASE_PT == 10


def test_sidebar_never_half_width(tmp_path, app):
    from tracker.session import Session
    from tracker.ui.main_window import MainWindow, SIDEBAR_ICONS, SIDEBAR_MIN
    s = Session.open_plain(tmp_path / "d")
    win = keep(MainWindow(s))
    win.resize(1200, 800)
    win.show()
    app.processEvents()
    win._sidebar_dragged(0, 1)                     # Qt «схлопнул» панель
    assert win._collapsed and win.splitter.sizes()[0] == SIDEBAR_ICONS
    win._sidebar_dragged(90, 1)                    # чуть потянули — остаётся полосой иконок
    assert win._collapsed and win.splitter.sizes()[0] == SIDEBAR_ICONS
    win._sidebar_dragged(200, 1)                   # вытянули — разворачивается, не уже минимума
    assert not win._collapsed and win.splitter.sizes()[0] >= SIDEBAR_MIN
    assert win.sidebar_panel.minimumWidth() == SIDEBAR_MIN
    win.close()
