from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QDateEdit, QDialog, QFormLayout, QFrame, QHBoxLayout, QInputDialog,
    QLineEdit, QMenu, QMessageBox, QPlainTextEdit, QProgressBar, QScrollArea, QVBoxLayout,
    QWidget,
)

from .. import logic
from ..db import Database
from . import widgets as w
from .tasks_tab import _dialog_buttons
from .theme import theme

FILTERS = [("Активные", "active"), ("Достигнутые", "done"), ("Архив", "archived")]


def deadline_text(goal: logic.Goal, today: date) -> tuple[str, str | None]:
    """Текст про срок и роль цвета (warn/danger) для подписи."""
    if goal.done:
        when = w.human_date(goal.completed_on, today) if goal.completed_on else ""
        return (f"Достигнута {when}".strip(), "accent")
    if goal.target_date is None:
        return ("Без срока", None)
    days = (goal.target_date - today).days
    base = f"До {w.human_date(goal.target_date, today)}"
    if days < 0:
        return (f"{base} · срок прошёл", "danger")
    if days <= 14:
        return (f"{base} · {logic.due_text(goal.target_date, today)}", "warn")
    return (f"{base} · {logic.due_text(goal.target_date, today)}", None)


def progress_bar(value: float) -> QProgressBar:
    bar = QProgressBar()
    bar.setRange(0, 100)
    bar.setValue(round(value * 100))
    bar.setTextVisible(False)
    bar.setAccessibleName(f"Прогресс {round(value * 100)}%")
    return bar


class GoalDialog(QDialog):
    def __init__(self, parent: QWidget, goal: logic.Goal | None = None):
        super().__init__(parent)
        self.setWindowTitle("Цель" if goal else "Новая цель")
        self.setMinimumWidth(480)
        self.goal = goal or logic.Goal(0, "")
        form = QFormLayout(self)
        form.setContentsMargins(20, 20, 20, 16)
        form.setVerticalSpacing(12)
        self.title = QLineEdit(self.goal.title)
        self.title.setPlaceholderText("Например, «Сдать IELTS на 7.0»")
        self.error = w.label("", "danger")
        self.error.hide()
        self.desc = QPlainTextEdit(self.goal.description)
        self.desc.setPlaceholderText("Зачем это вам и как поймёте, что цель достигнута")
        self.desc.setFixedHeight(100)
        self.has_date = QCheckBox("Есть срок")
        self.date = QDateEdit()
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("dd.MM.yyyy")
        d = self.goal.target_date or date(date.today().year, 12, 31)
        self.date.setDate(QDate(d.year, d.month, d.day))
        self.has_date.setChecked(self.goal.target_date is not None)
        self.date.setEnabled(self.goal.target_date is not None)
        self.has_date.toggled.connect(self.date.setEnabled)
        row = QHBoxLayout()
        row.addWidget(self.has_date)
        row.addWidget(self.date, 1)
        self.financial = QCheckBox("Финансовая цель — копить деньги")
        self.financial.setChecked(self.goal.financial)
        self.target = QLineEdit(logic.format_money(self.goal.target_amount).replace("\u00a0₽", "")
                                if self.goal.target_amount else "")
        self.target.setPlaceholderText("Сколько нужно накопить, ₽")
        self.initial = QLineEdit()
        self.initial.setPlaceholderText("Уже отложено, ₽ — необязательно")
        money = QHBoxLayout()
        money.addWidget(self.target, 1)
        if not goal:
            money.addWidget(self.initial, 1)
        else:
            self.initial.hide()
        self.money_row = QWidget()
        self.money_row.setLayout(money)
        money.setContentsMargins(0, 0, 0, 0)
        self.money_row.setVisible(self.goal.financial)
        self.financial.toggled.connect(self.money_row.setVisible)
        form.addRow("Цель", self.title)
        form.addRow("", self.error)
        form.addRow("Описание", self.desc)
        form.addRow("Срок", row)
        form.addRow("", self.financial)
        form.addRow("", self.money_row)
        if not goal:
            self.steps = QPlainTextEdit()
            self.steps.setPlaceholderText("Шаги к цели — по одному на строку (можно добавить позже)")
            self.steps.setFixedHeight(90)
            form.addRow("Шаги", self.steps)
        else:
            self.steps = None
        form.addRow(_dialog_buttons(self, "Сохранить"))

    def accept(self) -> None:
        msg = ""
        if not self.title.text().strip():
            msg = "Сформулируйте цель."
        elif self.financial.isChecked():
            target = logic.parse_money(self.target.text())
            initial = logic.parse_money(self.initial.text()) if self.initial.text().strip() else 0
            if not target or target <= 0:
                msg = "Укажите сумму, которую нужно накопить, например 150 000."
            elif initial is None or initial < 0:
                msg = "Сумма «уже отложено» должна быть числом."
        if msg:
            self.error.setText(msg)
            self.error.show()
            return
        super().accept()

    def values(self) -> tuple[logic.Goal, list[str]]:
        g = self.goal
        qd = self.date.date()
        g.title = self.title.text().strip()
        g.description = self.desc.toPlainText().strip()
        g.target_date = date(qd.year(), qd.month(), qd.day()) if self.has_date.isChecked() else None
        g.financial = self.financial.isChecked()
        if g.financial:
            g.target_amount = logic.parse_money(self.target.text()) or 0.0
        self.initial_amount = (logic.parse_money(self.initial.text()) or 0.0) if g.financial else 0.0
        steps = []
        if self.steps is not None:
            steps = [s.strip() for s in self.steps.toPlainText().splitlines() if s.strip()]
        return g, steps


class ContributionDialog(QDialog):
    """Внести деньги в копилку цели или снять."""

    def __init__(self, parent: QWidget, goal: logic.Goal, withdraw: bool = False):
        super().__init__(parent)
        self.withdraw = withdraw
        self.setWindowTitle("Снять с накоплений" if withdraw else "Пополнить накопления")
        self.setMinimumWidth(400)
        form = QFormLayout(self)
        form.setContentsMargins(20, 20, 20, 16)
        form.setVerticalSpacing(12)
        form.addRow(w.label(f"Цель: {goal.title}", "secondary", wrap=True))
        self.amount = QLineEdit()
        self.amount.setPlaceholderText("Сумма, ₽")
        self.day = QDateEdit()
        self.day.setCalendarPopup(True)
        self.day.setDisplayFormat("dd.MM.yyyy")
        t = date.today()
        self.day.setDate(QDate(t.year, t.month, t.day))
        self.note = QLineEdit()
        self.note.setPlaceholderText("Комментарий — например, «с премии»")
        self.error = w.label("", "danger")
        self.error.hide()
        form.addRow("Сумма", self.amount)
        form.addRow("Дата", self.day)
        form.addRow("Комментарий", self.note)
        form.addRow("", self.error)
        form.addRow(_dialog_buttons(self, "Снять" if withdraw else "Внести"))
        self.amount.setFocus()

    def accept(self) -> None:
        v = logic.parse_money(self.amount.text())
        if v is None or v <= 0:
            self.error.setText("Введите сумму больше нуля, например 5 000.")
            self.error.show()
            return
        super().accept()

    def values(self) -> tuple[float, date, str]:
        v = logic.parse_money(self.amount.text()) or 0.0
        qd = self.day.date()
        return (-v if self.withdraw else v), date(qd.year(), qd.month(), qd.day()), self.note.text().strip()


class GoalsPage(w.Page):
    def __init__(self, db: Database, navigate=None):
        super().__init__("Цели", "Долгосрочные цели и шаги к ним", scroll=False)
        self.db = db
        self.filter = "active"
        self.selected_id: int | None = None

        new_btn = w.button("Новая цель", "primary", "plus", "Новая цель (Ctrl+N)")
        new_btn.clicked.connect(self.new_item)
        self.header.add_action(new_btn)

        chips = QHBoxLayout()
        chips.setSpacing(6)
        self.group = QButtonGroup(self)
        for name, value in FILTERS:
            c = w.chip(name, value == self.filter)
            c.setProperty("value", value)
            self.group.addButton(c)
            chips.addWidget(c)
        self.group.buttonClicked.connect(self._filter_changed)
        chips.addStretch()
        self.content.addLayout(chips)

        body = QHBoxLayout()
        body.setSpacing(16)
        # список слева
        self.list_scroll = QScrollArea()
        self.list_scroll.setWidgetResizable(True)
        self.list_scroll.setFixedWidth(340)
        holder = QWidget()
        self.list = QVBoxLayout(holder)
        self.list.setContentsMargins(0, 0, 6, 0)
        self.list.setSpacing(8)
        self.list_scroll.setWidget(holder)
        body.addWidget(self.list_scroll)
        # подробности справа
        self.detail_scroll = QScrollArea()
        self.detail_scroll.setWidgetResizable(True)
        dholder = QWidget()
        self.detail = QVBoxLayout(dholder)
        self.detail.setContentsMargins(0, 0, 0, 0)
        self.detail_scroll.setWidget(dholder)
        body.addWidget(self.detail_scroll, 1)
        self.content.addLayout(body, 1)

    def _filter_changed(self, btn) -> None:
        self.filter = btn.property("value")
        self.selected_id = None
        self.refresh()

    def new_item(self) -> None:
        dlg = GoalDialog(self)
        if dlg.exec() == QDialog.Accepted:
            goal, steps = dlg.values()
            gid = self.db.add_goal(goal)
            for s in steps:
                self.db.add_step(gid, s)
            if goal.financial and dlg.initial_amount:
                self.db.add_contribution(gid, dlg.initial_amount, note="уже было отложено")
            self.selected_id = gid
            if self.filter != "active":
                for b in self.group.buttons():
                    b.setChecked(b.property("value") == "active")
                self.filter = "active"
            self.refresh()

    def focus_item(self, goal_id: int | None = None) -> None:
        goal = self.db.get_goal(goal_id) if goal_id else None
        if goal:
            self.filter = "archived" if goal.archived else ("done" if goal.done else "active")
            for b in self.group.buttons():
                b.setChecked(b.property("value") == self.filter)
            self.selected_id = goal_id
            self.refresh()

    def _visible_goals(self) -> list[logic.Goal]:
        goals = self.db.list_goals()
        if self.filter == "archived":
            goals = [g for g in goals if g.archived]
        elif self.filter == "done":
            goals = [g for g in goals if g.done and not g.archived]
        else:
            goals = [g for g in goals if not g.done and not g.archived]
        return sorted(goals, key=logic.goal_sort_key)

    def refresh(self) -> None:
        today = date.today()
        goals = self._visible_goals()
        steps = self.db.all_steps()
        self.saved = self.db.saved_amounts()
        all_goals = self.db.list_goals()
        active = [g for g in all_goals if not g.done and not g.archived]
        achieved = [g for g in all_goals if g.done]
        self.header.set_subtitle(
            f"{len(active)} в работе · {len(achieved)} "
            f"{logic.plural(len(achieved), 'достигнута', 'достигнуты', 'достигнуто')}"
            if all_goals else "Долгосрочные цели и шаги к ним")
        if goals and self.selected_id not in {g.id for g in goals}:
            self.selected_id = goals[0].id
        if not goals:
            self.selected_id = None

        w.clear_layout(self.list)
        for g in goals:
            self.list.addWidget(self._goal_tile(g, steps.get(g.id, []), today))
        self.list.addStretch()

        w.clear_layout(self.detail)
        goal = next((g for g in goals if g.id == self.selected_id), None)
        if goal:
            self.detail.addWidget(self._detail_card(goal, steps.get(goal.id, []), today))
        else:
            text = {
                "active": "Целей пока нет.\n\nЦели — то, к чему вы идёте месяцами: «Выучить "
                          "английский до B2», «Пробежать полумарафон».\nРазбейте цель на шаги — "
                          "прогресс будет считаться сам.\n\nНажмите «Новая цель».",
                "done": "Здесь появятся достигнутые цели.",
                "archived": "В архиве пусто.",
            }[self.filter]
            empty = w.label(text, "empty", wrap=True)
            empty.setAlignment(Qt.AlignCenter)
            self.detail.addWidget(empty)
        self.detail.addStretch()
        self.list_scroll.setVisible(bool(goals))

    def _goal_tile(self, g: logic.Goal, steps: list[logic.GoalStep], today: date) -> QWidget:
        tile = w.ClickableFrame("card")
        tile.setProperty("selected", g.id == self.selected_id)
        if g.id == self.selected_id:
            tile.setStyleSheet(f"QFrame#card {{ border: 2px solid {theme['teal']}; }}")
        lay = QVBoxLayout(tile)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(6)
        title = w.label(g.title, None, wrap=True)
        title.setTextFormat(Qt.PlainText)
        f = title.font(); f.setWeight(f.Weight.DemiBold); title.setFont(f)
        lay.addWidget(title)
        saved = self.saved.get(g.id, 0.0)
        prog = logic.goal_progress(g, steps, saved)
        lay.addWidget(progress_bar(prog))
        done = sum(1 for s in steps if s.done)
        info = f"{round(prog * 100)}%"
        if g.financial:
            info += f" · {logic.format_money(saved)} из {logic.format_money(g.target_amount)}"
        if steps:
            info += f" · {done} из {len(steps)} {logic.plural(len(steps), 'шага', 'шагов', 'шагов')}"
        lay.addWidget(w.label(info, "caption", wrap=True))
        text, role = deadline_text(g, today)
        lay.addWidget(w.label(text, role or "caption"))
        tile.setAccessibleName(f"{g.title}, {round(prog * 100)}%, {text}")
        tile.clicked.connect(lambda gid=g.id: self._select(gid))
        return tile

    def _select(self, goal_id: int) -> None:
        self.selected_id = goal_id
        self.refresh()

    def _detail_card(self, g: logic.Goal, steps: list[logic.GoalStep], today: date) -> QWidget:
        card = w.Card(margins=22)
        card.body.setSpacing(12)
        head = QHBoxLayout()
        title = w.label(g.title, "title", wrap=True)
        title.setTextFormat(Qt.PlainText)
        head.addWidget(title, 1)
        more_btn = w.menu_button("Другие действия с целью")
        menu = QMenu(more_btn)
        menu.addAction("Изменить…", lambda: self._edit(g))
        menu.addAction("Вернуть из архива" if g.archived else "Отправить в архив",
                       lambda: self._archive(g))
        menu.addSeparator()
        menu.addAction("Удалить навсегда…", lambda: self._delete(g))
        more_btn.setMenu(menu)
        head.addWidget(more_btn, 0, Qt.AlignTop)
        card.body.addLayout(head)

        text, role = deadline_text(g, today)
        card.body.addWidget(w.label(text, role or "secondary"))
        if g.description:
            desc = w.label(g.description, None, wrap=True)
            desc.setTextFormat(Qt.PlainText)
            desc.setTextInteractionFlags(Qt.TextSelectableByMouse)
            card.body.addWidget(desc)

        saved = self.saved.get(g.id, 0.0)
        prog = logic.goal_progress(g, steps, saved)
        prow = QHBoxLayout()
        prow.addWidget(progress_bar(prog), 1)
        prow.addWidget(w.label(f"{round(prog * 100)}%", "accent"))
        card.body.addSpacing(4)
        card.body.addLayout(prow)
        if g.financial and g.target_amount > 0 and steps and not g.done:
            m = logic.money_progress(g, saved)
            s_done = sum(1 for s in steps if s.done) / len(steps)
            card.body.addWidget(w.label(
                f"Прогресс считается поровну: накопления {round(m * 100)}% и шаги {round(s_done * 100)}%.",
                "caption", wrap=True))

        actions = QHBoxLayout()
        actions.setSpacing(8)
        if not g.archived:
            if g.done:
                again = w.button("Вернуть в работу")
                again.clicked.connect(lambda: self._set_done(g, False))
                actions.addWidget(again)
            else:
                done_btn = w.button("Цель достигнута", "primary" if prog >= 1 else None, "check")
                done_btn.clicked.connect(lambda: self._set_done(g, True))
                actions.addWidget(done_btn)
        edit = w.button("Изменить…", None, "edit")
        edit.clicked.connect(lambda: self._edit(g))
        actions.addWidget(edit)
        actions.addStretch()
        card.body.addLayout(actions)

        if g.financial:
            self._money_section(card, g, saved, today)

        card.body.addSpacing(6)
        done = sum(1 for s in steps if s.done)
        card.body.addWidget(w.label(
            f"Шаги · {done} из {len(steps)}" if steps else "Шаги", "section"))
        if not steps:
            card.body.addWidget(w.label("Разбейте цель на конкретные шаги — так проще начать "
                                        "и видно, сколько осталось.", "secondary", wrap=True))
        for s in steps:
            row = QHBoxLayout()
            row.setSpacing(6)
            cb = QCheckBox(s.title)
            cb.setChecked(s.done)
            cb.setEnabled(not g.archived)
            cb.setCursor(Qt.PointingHandCursor)
            if s.done:
                f = cb.font(); f.setStrikeOut(True); cb.setFont(f)
                cb.setStyleSheet(f"color: {theme['text2']};")
            cb.toggled.connect(lambda on, sid=s.id: self._toggle_step(sid, on))
            row.addWidget(cb, 1)
            if not g.archived:
                mb = w.menu_button(f"Действия с шагом «{s.title}»")
                mb.setFixedSize(28, 28)
                m = QMenu(mb)
                m.addAction("Переименовать…", lambda sid=s.id, t=s.title: self._rename_step(sid, t))
                m.addAction("Удалить шаг", lambda sid=s.id: self._delete_step(sid))
                mb.setMenu(m)
                row.addWidget(mb)
            card.body.addLayout(row)
        if not g.archived and not g.done:
            add_row = QHBoxLayout()
            field = QLineEdit()
            field.setPlaceholderText("Новый шаг и Enter")
            add = w.button("Добавить шаг", None, "plus")

            def add_step():
                t = field.text().strip()
                if t:
                    self.db.add_step(g.id, t)
                    self.refresh()
            field.returnPressed.connect(add_step)
            add.clicked.connect(add_step)
            add_row.addWidget(field, 1)
            add_row.addWidget(add)
            card.body.addLayout(add_row)
        if g.created_on:
            card.body.addSpacing(6)
            card.body.addWidget(w.label(f"Цель поставлена {w.human_date(g.created_on, today)}",
                                        "caption"))
        return card

    def _money_section(self, card: w.Card, g: logic.Goal, saved: float, today: date) -> None:
        card.body.addSpacing(6)
        box = QFrame()
        box.setObjectName("money")
        box.setStyleSheet(f"QFrame#money {{ background: {theme['surface2']}; border: 1px solid {theme['border']};"
                          f" border-radius: 8px; }} QFrame#money QLabel {{ background: transparent; }}")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(16, 12, 16, 14)
        lay.setSpacing(8)
        head = QHBoxLayout()
        head.addWidget(w.label("Накопления", "section"))
        head.addStretch()
        if not g.archived:
            minus = w.button("Снять…")
            minus.clicked.connect(lambda: self._contribute(g, True))
            plus = w.button("Пополнить…", "primary", "plus")
            plus.clicked.connect(lambda: self._contribute(g, False))
            head.addWidget(minus)
            head.addWidget(plus)
        lay.addLayout(head)
        amount = w.label(f"{logic.format_money(saved)}  из  {logic.format_money(g.target_amount)}", "metric")
        lay.addWidget(amount)
        mp = logic.money_progress(g, saved)
        bar = progress_bar(mp)
        bar.setAccessibleName(f"Накоплено {round(mp * 100)}%")
        lay.addWidget(bar)
        left = g.target_amount - saved
        if left > 0:
            hint = f"Осталось {logic.format_money(left)}"
            if g.target_date and g.target_date > today and not g.done:
                months = max(1.0, (g.target_date - today).days / 30.44)
                hint += f" · чтобы успеть к сроку, откладывайте ≈ {logic.format_money(round(left / months, -2) or left / months)} в месяц"
            lay.addWidget(w.label(hint, "secondary", wrap=True))
        else:
            lay.addWidget(w.label("Нужная сумма накоплена", "accent"))
        history = self.db.contributions(g.id)
        if history:
            lay.addSpacing(4)
            lay.addWidget(w.label("История", "caption"))
            for c in history[:8]:
                row = QHBoxLayout()
                row.setSpacing(10)
                row.addWidget(w.label(c.day.strftime("%d.%m.%Y"), "caption"))
                amt = w.label(("+" if c.amount > 0 else "") + logic.format_money(c.amount),
                              None if c.amount > 0 else "danger")
                amt.setMinimumWidth(110)
                row.addWidget(amt)
                note = w.label(c.note, "secondary")
                note.setTextFormat(Qt.PlainText)
                row.addWidget(note, 1)
                if not g.archived:
                    mb = w.menu_button("Действия с записью")
                    mb.setFixedSize(26, 26)
                    m = QMenu(mb)
                    m.addAction("Удалить запись", lambda cid=c.id: self._delete_contribution(cid))
                    mb.setMenu(m)
                    row.addWidget(mb)
                lay.addLayout(row)
            if len(history) > 8:
                lay.addWidget(w.label(f"и ещё {len(history) - 8} записей", "caption"))
        card.body.addWidget(box)

    def _contribute(self, g: logic.Goal, withdraw: bool) -> None:
        dlg = ContributionDialog(self, g, withdraw)
        if dlg.exec() == QDialog.Accepted:
            amount, day, note = dlg.values()
            self.db.add_contribution(g.id, amount, day, note)
            self.refresh()

    def _delete_contribution(self, cid: int) -> None:
        self.db.delete_contribution(cid)
        self.refresh()

    # ---- действия ----

    def _toggle_step(self, step_id: int, on: bool) -> None:
        self.db.set_step_done(step_id, on)
        self.refresh()

    def _rename_step(self, step_id: int, title: str) -> None:
        text, ok = QInputDialog.getText(self, "Переименовать шаг", "Шаг:", text=title)
        if ok and text.strip():
            self.db.rename_step(step_id, text.strip())
            self.refresh()

    def _delete_step(self, step_id: int) -> None:
        self.db.delete_step(step_id)
        self.refresh()

    def _set_done(self, g: logic.Goal, done: bool) -> None:
        g.done = done
        g.completed_on = None
        self.db.update_goal(g)
        self.selected_id = g.id
        self.refresh()

    def _edit(self, g: logic.Goal) -> None:
        dlg = GoalDialog(self, g)
        if dlg.exec() == QDialog.Accepted:
            goal, _ = dlg.values()
            self.db.update_goal(goal)
            self.refresh()

    def _archive(self, g: logic.Goal) -> None:
        g.archived = not g.archived
        self.db.update_goal(g)
        self.refresh()

    def _delete(self, g: logic.Goal) -> None:
        box = QMessageBox(QMessageBox.Warning, "Удалить цель",
                          f"Удалить цель «{g.title}» вместе с шагами?", parent=self)
        box.setInformativeText("Это действие нельзя отменить. Чтобы убрать цель из списка, "
                               "отправьте её в архив.")
        yes = box.addButton("Удалить", QMessageBox.DestructiveRole)
        box.addButton("Отмена", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is yes:
            self.db.delete_goal(g.id)
            self.selected_id = None
            self.refresh()
