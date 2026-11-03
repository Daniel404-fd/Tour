from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QHBoxLayout, QInputDialog, QLineEdit, QMenu, QMessageBox, QPushButton, QVBoxLayout,
)

from .. import logic
from ..db import Database
from . import widgets as w
from .theme import repolish

HEAT_DAYS = 30


def streak_text(current: int, best: int) -> str:
    cur = f"Серия: {current} {logic.plural(current, 'день', 'дня', 'дней')}"
    return f"{cur} · рекорд {best}"


class HabitCard(w.Card):
    def __init__(self, page: "HabitsPage", habit: logic.Habit, marks: set[date], today: date):
        super().__init__()
        self.page, self.habit = page, habit
        self.body.setSpacing(12)

        head = QHBoxLayout()
        head.setSpacing(12)
        names = QVBoxLayout()
        names.setSpacing(2)
        title = w.label(habit.name, "section")
        title.setTextFormat(Qt.PlainText)
        names.addWidget(title)
        if habit.archived:
            names.addWidget(w.label("В архиве", "caption"))
        else:
            names.addWidget(w.label(streak_text(logic.current_streak(marks, today),
                                                logic.best_streak(marks)), "secondary"))
        head.addLayout(names, 1)

        if habit.archived:
            restore = w.button("Вернуть")
            restore.clicked.connect(lambda: self.page.set_archived(habit, False))
            head.addWidget(restore)
        menu_btn = w.menu_button(f"Действия с привычкой «{habit.name}»")
        menu = QMenu(menu_btn)
        if not habit.archived:
            menu.addAction("Переименовать…", self.rename)
            menu.addAction("Отправить в архив", lambda: self.page.set_archived(habit, True))
            menu.addSeparator()
        delete = QAction("Удалить навсегда…", menu)
        delete.triggered.connect(self.delete)
        menu.addAction(delete)
        menu_btn.setMenu(menu)
        head.addWidget(menu_btn, 0, Qt.AlignTop)
        self.body.addLayout(head)

        if not habit.archived:
            week = QHBoxLayout()
            week.setSpacing(6)
            for day in logic.last_days(today, logic.EDITABLE_DAYS):
                is_today = day == today
                top = "Сегодня" if is_today else w.WEEKDAYS_SHORT[day.weekday()]
                btn = QPushButton(f"{top}\n{day.day}")
                btn.setProperty("kind", "day")
                btn.setProperty("today", "true" if is_today else "false")
                btn.setCheckable(True)
                btn.setChecked(day in marks)
                btn.setCursor(Qt.PointingHandCursor)
                btn.setToolTip(f"{w.WEEKDAYS_FULL[day.weekday()]}, {w.human_date(day, today)}")
                btn.setAccessibleName(
                    f"{habit.name}, {w.human_date(day, today)}: "
                    + ("выполнено" if day in marks else "не выполнено"))
                btn.toggled.connect(lambda checked, d=day: self.page.set_mark(habit.id, d, checked))
                week.addWidget(btn, 1)
            self.body.addLayout(week)

        strip_row = QHBoxLayout()
        strip_row.setSpacing(10)
        days = logic.last_days(today, HEAT_DAYS)
        strip_row.addWidget(w.HeatStrip(days, marks, today))
        done = sum(1 for d in days if d in marks)
        strip_row.addWidget(w.label(f"{done} из {HEAT_DAYS} дней", "caption"))
        strip_row.addStretch()
        self.body.addLayout(strip_row)

    def rename(self) -> None:
        name, ok = QInputDialog.getText(self, "Переименовать привычку", "Название:",
                                        text=self.habit.name)
        if ok and name.strip():
            self.page.db.rename_habit(self.habit.id, name.strip())
            self.page.refresh()

    def delete(self) -> None:
        box = QMessageBox(QMessageBox.Warning, "Удалить привычку",
                          f"Удалить привычку «{self.habit.name}» вместе со всеми отметками?",
                          parent=self)
        box.setInformativeText("Это действие нельзя отменить. Чтобы просто убрать привычку "
                               "из списка, отправьте её в архив.")
        yes = box.addButton("Удалить", QMessageBox.DestructiveRole)
        box.addButton("Отмена", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is yes:
            self.page.db.delete_habit(self.habit.id)
            self.page.refresh()


class HabitsPage(w.Page):
    def __init__(self, db: Database, navigate=None):
        super().__init__("Привычки")
        self.db = db
        self.show_archive = False

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Новая привычка, например «Зарядка»")
        self.name_edit.setMinimumWidth(260)
        self.name_edit.returnPressed.connect(self.add_habit)
        add = w.button("Добавить", "primary", "plus")
        add.clicked.connect(self.add_habit)
        self.archive_chip = w.chip("Архив")
        self.archive_chip.setToolTip("Показать привычки в архиве")
        self.archive_chip.toggled.connect(self._toggle_archive)
        self.header.add_action(self.archive_chip)
        self.header.add_action(self.name_edit)
        self.header.add_action(add)

        self.list = QVBoxLayout()
        self.list.setSpacing(12)
        self.content.addLayout(self.list)
        self.content.addStretch()

    def new_item(self) -> None:
        self.name_edit.setFocus()

    def _toggle_archive(self, on: bool) -> None:
        self.show_archive = on
        self.refresh()

    def add_habit(self) -> None:
        name = self.name_edit.text().strip()
        if not name:
            self.name_edit.setFocus()
            return
        self.db.add_habit(name)
        self.name_edit.clear()
        if self.show_archive:
            self.archive_chip.setChecked(False)  # вызовет refresh
        else:
            self.refresh()

    def set_mark(self, habit_id: int, day: date, done: bool) -> None:
        if logic.can_mark(day, date.today()):
            self.db.set_mark(habit_id, day, done)
        self.refresh()

    def set_archived(self, habit: logic.Habit, archived: bool) -> None:
        self.db.archive_habit(habit.id, archived)
        self.refresh()

    def refresh(self) -> None:
        today = date.today()
        habits = [h for h in self.db.list_habits(include_archived=True)
                  if h.archived == self.show_archive]
        marks = self.db.all_marks()
        active = self.db.list_habits()
        done_today = sum(1 for h in active if today in marks.get(h.id, set()))
        self.header.set_subtitle(
            f"Сегодня отмечено {done_today} из {len(active)}" if active and not self.show_archive
            else ("Привычки в архиве не учитываются в статистике" if self.show_archive else ""))
        with self.keep_scroll():
            w.clear_layout(self.list)
            if not habits:
                text = ("В архиве пусто." if self.show_archive else
                        "Привычек пока нет.\nВведите название вверху и нажмите «Добавить» — "
                        "например, «Зарядка» или «Читать 20 минут».")
                empty = w.label(text, "empty", wrap=True)
                empty.setAlignment(Qt.AlignCenter)
                self.list.addWidget(empty)
            for habit in habits:
                self.list.addWidget(HabitCard(self, habit, marks.get(habit.id, set()), today))
        repolish(self.archive_chip)
