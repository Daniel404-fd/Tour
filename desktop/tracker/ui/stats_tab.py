from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCharts import (
    QBarCategoryAxis, QBarSeries, QBarSet, QCategoryAxis, QChart, QChartView, QLineSeries,
    QValueAxis,
)
from PySide6.QtCore import QMargins, Qt
from PySide6.QtGui import QBrush, QFont, QPainter, QPen
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QProgressBar, QVBoxLayout

from .. import logic
from ..db import Database
from . import widgets as w
from .theme import theme


def _style_chart(chart: QChart) -> None:
    chart.setBackgroundVisible(False)
    chart.setPlotAreaBackgroundVisible(False)
    chart.legend().hide()
    chart.setMargins(QMargins(4, 4, 22, 4))
    chart.layout().setContentsMargins(0, 0, 0, 0)
    chart.setAnimationOptions(QChart.NoAnimation)


def _style_axis(axis) -> None:
    f = QFont(w.label().font())
    from . import theme as _th
    f.setPointSizeF(8.5 * _th.BASE_PT / 10)
    axis.setLabelsFont(f)
    axis.setLabelsBrush(QBrush(theme.color("text2")))
    axis.setLinePen(QPen(theme.color("border")))
    axis.setGridLinePen(QPen(theme.color("border"), 1, Qt.DotLine))


class StatsPage(w.Page):
    def __init__(self, db: Database, navigate=None):
        super().__init__("Статистика")
        self.db = db
        self.summary = QHBoxLayout()
        self.summary.setSpacing(12)
        self.content.addLayout(self.summary)
        self.grid = QGridLayout()
        self.grid.setSpacing(12)
        self.content.addLayout(self.grid)
        self.content.addStretch()

    def _metric(self, caption: str, value: str, note: str = "", role: str | None = None) -> w.Card:
        card = w.Card()
        card.body.setSpacing(2)
        card.body.addWidget(w.label(caption, "secondary", wrap=True))
        v = w.label(value, "metric")
        if role:
            v.setProperty("tone", role)
        card.body.addWidget(v)
        if note:
            card.body.addWidget(w.label(note, "caption", wrap=True))
        card.setMinimumWidth(120)
        return card

    def refresh(self) -> None:
        today = date.today()
        habits = self.db.list_habits(include_archived=True)
        marks = self.db.all_marks()
        tasks = self.db.list_tasks(include_boards=True)
        goals = self.db.list_goals()

        w.clear_layout(self.summary)
        s = logic.summary(habits, marks, tasks, today)
        points = logic.completion_by_day(habits, marks, today, 28)
        avg = sum(v for _, v in points) / len(points) if points and s.active_habits else 0
        week_done = sum(1 for t in tasks if t.done and t.completed_on
                        and t.completed_on >= logic.week_start(today))
        active_goals = [g for g in goals if not g.done and not g.archived]
        self.summary.addWidget(self._metric(
            "Выполнение привычек", f"{avg:.0f}%", "в среднем за 4 недели"))
        self.summary.addWidget(self._metric(
            "Лучшая текущая серия", f"{s.best_current_streak}",
            logic.plural(s.best_current_streak, "день подряд", "дня подряд", "дней подряд")))
        self.summary.addWidget(self._metric(
            "Задач выполнено", f"{week_done}", "на этой неделе"))
        self.summary.addWidget(self._metric(
            "Просрочено задач", f"{s.overdue_tasks}",
            "всё в срок" if not s.overdue_tasks else "стоит заглянуть в «Задачи»",
            "danger" if s.overdue_tasks else None))
        if active_goals:
            steps = self.db.all_steps()
            saved = self.db.saved_amounts()
            g_avg = sum(logic.goal_progress(g, steps.get(g.id, []), saved.get(g.id, 0.0),
                                                 self.db.goal_task_flags().get(g.id, []))
                        for g in active_goals) / len(active_goals)
            self.summary.addWidget(self._metric(
                "Цели в работе", f"{len(active_goals)}", f"средний прогресс {g_avg * 100:.0f}%"))

        w.clear_layout(self.grid)
        habits_card = w.Card("Привычки по дням, %")
        habits_card.body.addWidget(w.label("Доля отмеченных привычек за каждый из последних 28 дней",
                                           "caption"))
        habits_card.body.addWidget(self._view(self._habits_chart(points)))
        tasks_card = w.Card("Выполненные задачи по неделям")
        weeks = logic.completed_tasks_by_week(tasks, today, 8)
        total = sum(c for _, c in weeks)
        tasks_card.body.addWidget(w.label(f"За 8 недель — {total}", "caption"))
        tasks_card.body.addWidget(self._view(self._tasks_chart(weeks)))
        topics_card = self._topics_card(tasks, today)
        self.grid.addWidget(habits_card, 0, 0, 1, 2)
        self.grid.addWidget(tasks_card, 1, 0)
        self.grid.addWidget(topics_card, 1, 1)
        self.grid.setColumnStretch(0, 3)
        self.grid.setColumnStretch(1, 2)

    def _view(self, chart: QChart) -> QChartView:
        view = QChartView(chart)
        view.setRenderHint(QPainter.Antialiasing)
        view.setMinimumHeight(240)
        view.setStyleSheet("background: transparent;")
        return view

    def _topics_card(self, tasks: list[logic.Task], today: date) -> w.Card:
        card = w.Card("По темам за 30 дней")
        since = today - timedelta(days=29)
        topics = self.db.list_topics()
        counts: dict[int | None, int] = {}
        for t in tasks:
            if t.done and t.completed_on and t.completed_on >= since:
                counts[t.topic_id] = counts.get(t.topic_id, 0) + 1
        rows = [(tp.name, tp.color, counts.get(tp.id, 0)) for tp in topics]
        if counts.get(None):
            rows.append(("Без темы", None, counts[None]))
        rows = [r for r in rows if r[2] > 0]
        rows.sort(key=lambda r: -r[2])
        if not rows:
            card.body.addWidget(w.label(
                "Здесь появится разбивка выполненных задач по темам. Заведите темы в разделе "
                "«Задачи» → «Темы…».", "secondary", wrap=True))
            card.body.addStretch()
            return card
        top = max(r[2] for r in rows)
        for name, color, n in rows:
            line = QHBoxLayout()
            lbl = w.label()
            lbl.setText(w.topic_html(name, color) if color else name)
            line.addWidget(lbl, 1)
            line.addWidget(w.label(str(n), "secondary"))
            card.body.addLayout(line)
            bar = QProgressBar()
            bar.setRange(0, top)
            bar.setValue(n)
            bar.setTextVisible(False)
            bar.setAccessibleName(f"{name}: {n}")
            card.body.addWidget(bar)
        card.body.addStretch()
        return card

    @staticmethod
    def _habits_chart(points: list[tuple[date, float]]) -> QChart:
        chart = QChart()
        _style_chart(chart)
        series = QLineSeries()
        for i, (_, pct) in enumerate(points):
            series.append(i, pct)
        series.setPen(QPen(theme.color("accent"), 2.5))
        chart.addSeries(series)
        axis_x = QCategoryAxis()
        axis_x.setLabelsPosition(QCategoryAxis.AxisLabelsPositionOnValue)
        for i, (day, _) in enumerate(points):
            if i % 7 == 0 or i == len(points) - 1:
                axis_x.append(day.strftime("%d.%m"), i)
        axis_x.setRange(0, max(len(points) - 1, 1))
        axis_y = QValueAxis()
        axis_y.setRange(0, 100)
        axis_y.setLabelFormat("%d%%")
        axis_y.setTickCount(5)
        for a in (axis_x, axis_y):
            _style_axis(a)
        chart.addAxis(axis_x, Qt.AlignBottom)
        chart.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_x)
        series.attachAxis(axis_y)
        return chart

    @staticmethod
    def _tasks_chart(weeks: list[tuple[date, int]]) -> QChart:
        chart = QChart()
        _style_chart(chart)
        bar_set = QBarSet("Выполнено")
        bar_set.setColor(theme.color("accent"))
        bar_set.setBorderColor(theme.color("accent"))
        for _, count in weeks:
            bar_set.append(count)
        series = QBarSeries()
        series.setBarWidth(0.6)
        series.append(bar_set)
        chart.addSeries(series)
        axis_x = QBarCategoryAxis()
        axis_x.append([start.strftime("%d.%m") for start, _ in weeks])
        axis_y = QValueAxis()
        top = max((c for _, c in weeks), default=0)
        step = max(1, -(-top // 5))           # целые деления, не больше 5
        upper = max(step, -(-top // step) * step)
        axis_y.setRange(0, upper)
        axis_y.setLabelFormat("%d")
        axis_y.setTickCount(upper // step + 1)
        for a in (axis_x, axis_y):
            _style_axis(a)
        chart.addAxis(axis_x, Qt.AlignBottom)
        chart.addAxis(axis_y, Qt.AlignLeft)
        series.attachAxis(axis_x)
        series.attachAxis(axis_y)
        return chart
