"""Чистая логика: стрики, статистика, сортировка задач. Без Qt и без БД."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

PRIORITY_HIGH = 0
PRIORITY_MEDIUM = 1
PRIORITY_LOW = 2
PRIORITY_NAMES = {PRIORITY_HIGH: "Высокий", PRIORITY_MEDIUM: "Средний", PRIORITY_LOW: "Низкий"}

# Сколько последних дней (включая сегодня) можно отмечать.
EDITABLE_DAYS = 7


@dataclass
class Habit:
    id: int
    name: str
    archived: bool
    created_on: date


@dataclass
class Task:
    id: int
    title: str
    description: str = ""
    deadline: date | None = None
    priority: int = PRIORITY_MEDIUM
    done: bool = False
    completed_on: date | None = None
    archived: bool = False
    topic_id: int | None = None


# ---------- Привычки ----------

def last_days(today: date, n: int) -> list[date]:
    """Последние n дней по возрастанию, последний — today."""
    return [today - timedelta(days=i) for i in range(n - 1, -1, -1)]


def can_mark(day: date, today: date) -> bool:
    """Отметку можно ставить/снимать только за последние EDITABLE_DAYS дней."""
    return today - timedelta(days=EDITABLE_DAYS - 1) <= day <= today


def current_streak(marks: Iterable[date], today: date) -> int:
    """Дней подряд до сегодня включительно.

    Если сегодня ещё не отмечено, серия считается до вчера и не сбрасывается.
    """
    days = set(marks)
    day = today if today in days else today - timedelta(days=1)
    streak = 0
    while day in days:
        streak += 1
        day -= timedelta(days=1)
    return streak


def best_streak(marks: Iterable[date]) -> int:
    """Самая длинная серия подряд идущих дней за всё время."""
    days = sorted(set(marks))
    best = run = 0
    prev: date | None = None
    for d in days:
        run = run + 1 if prev is not None and d - prev == timedelta(days=1) else 1
        best = max(best, run)
        prev = d
    return best


def completion_by_day(
    habits: list[Habit], marks: dict[int, set[date]], today: date, days: int = 28
) -> list[tuple[date, float]]:
    """Процент выполнения активных привычек по дням.

    В знаменатель входят активные привычки, созданные не позже этого дня.
    """
    active = [h for h in habits if not h.archived]
    result = []
    for day in last_days(today, days):
        existing = [h for h in active if h.created_on <= day]
        if not existing:
            result.append((day, 0.0))
            continue
        done = sum(1 for h in existing if day in marks.get(h.id, set()))
        result.append((day, 100.0 * done / len(existing)))
    return result


# ---------- Задачи ----------

def task_sort_key(task: Task) -> tuple:
    """Сначала по дедлайну (без дедлайна — в конце), затем по приоритету."""
    return (task.deadline is None, task.deadline or date.max, task.priority, task.id)


def sort_tasks(tasks: Iterable[Task]) -> list[Task]:
    return sorted(tasks, key=task_sort_key)


def is_overdue(task: Task, today: date) -> bool:
    return (not task.done and not task.archived
            and task.deadline is not None and task.deadline < today)


def is_due_today(task: Task, today: date) -> bool:
    return not task.done and not task.archived and task.deadline == today


FILTER_ACTIVE = "active"
FILTER_DONE = "done"
FILTER_ALL = "all"
FILTER_ARCHIVED = "archived"


def filter_tasks(tasks: Iterable[Task], mode: str) -> list[Task]:
    """Активные / выполненные / все — без архивных; «Архив» — только архивные."""
    if mode == FILTER_ARCHIVED:
        return [t for t in tasks if t.archived]
    visible = [t for t in tasks if not t.archived]
    if mode == FILTER_ACTIVE:
        return [t for t in visible if not t.done]
    if mode == FILTER_DONE:
        return [t for t in visible if t.done]
    return visible


def week_start(day: date) -> date:
    """Понедельник недели, в которую входит day."""
    return day - timedelta(days=day.weekday())


def completed_tasks_by_week(
    tasks: Iterable[Task], today: date, weeks: int = 8
) -> list[tuple[date, int]]:
    """Количество выполненных задач по неделям (пн–вс), последние weeks недель."""
    current = week_start(today)
    starts = [current - timedelta(weeks=i) for i in range(weeks - 1, -1, -1)]
    counts = {s: 0 for s in starts}
    for t in tasks:
        if t.done and t.completed_on is not None:
            s = week_start(t.completed_on)
            if s in counts:
                counts[s] += 1
    return [(s, counts[s]) for s in starts]


# ---------- Сводка ----------

@dataclass
class Summary:
    active_habits: int
    best_current_streak: int
    overdue_tasks: int


def summary(
    habits: list[Habit], marks: dict[int, set[date]], tasks: Iterable[Task], today: date
) -> Summary:
    active = [h for h in habits if not h.archived]
    best = max((current_streak(marks.get(h.id, set()), today) for h in active), default=0)
    overdue = sum(1 for t in tasks if is_overdue(t, today))
    return Summary(len(active), best, overdue)


# ---------- Темы задач ----------

# Палитра тем: различимые оттенки, у каждой темы рядом всегда показывается название,
# поэтому цвет никогда не единственный носитель смысла.
TOPIC_COLORS = ["#008000", "#000080", "#800000", "#C05800", "#800080", "#008080",
                "#808000", "#505050"]


@dataclass
class Topic:
    id: int
    name: str
    color: str = TOPIC_COLORS[0]


TOPIC_ALL = -1    # фильтр «Все темы»
TOPIC_NONE = 0    # фильтр «Без темы»


def filter_by_topic(tasks: Iterable[Task], topic_id: int) -> list[Task]:
    if topic_id == TOPIC_ALL:
        return list(tasks)
    if topic_id == TOPIC_NONE:
        return [t for t in tasks if t.topic_id is None]
    return [t for t in tasks if t.topic_id == topic_id]


def upcoming_tasks(tasks: Iterable[Task], today: date, days: int = 4) -> list[Task]:
    """Просроченные и задачи с дедлайном в ближайшие `days` дней (включая сегодня)."""
    limit = today + timedelta(days=days)
    result = [t for t in tasks
              if not t.done and not t.archived and t.deadline is not None and t.deadline <= limit]
    return sort_tasks(result)


# ---------- Цели ----------

@dataclass
class Subtask:
    id: int
    task_id: int
    title: str
    done: bool = False
    position: int = 0


@dataclass
class GoalStep:
    id: int
    goal_id: int
    title: str
    done: bool = False
    position: int = 0


@dataclass
class Goal:
    id: int
    title: str
    description: str = ""
    target_date: date | None = None
    done: bool = False
    archived: bool = False
    created_on: date | None = None
    completed_on: date | None = None
    financial: bool = False
    target_amount: float = 0.0


@dataclass
class Contribution:
    """Взнос (или снятие, если сумма отрицательная) в финансовую цель."""
    id: int
    goal_id: int
    day: date
    amount: float
    note: str = ""


def money_progress(goal: Goal, saved: float) -> float:
    if not goal.financial or goal.target_amount <= 0:
        return 0.0
    return max(0.0, min(1.0, saved / goal.target_amount))


def goal_progress(goal: Goal, steps: list[GoalStep], saved: float = 0.0) -> float:
    """Доля 0..1.

    Обычная цель — по выполненным шагам. Финансовая — по накопленной сумме, а если у неё
    есть шаги, то поровну: половина — деньги, половина — шаги. Достигнутая цель — всегда 1.
    """
    if goal.done:
        return 1.0
    steps_part = sum(1 for s in steps if s.done) / len(steps) if steps else None
    if goal.financial and goal.target_amount > 0:
        money = money_progress(goal, saved)
        return money if steps_part is None else (money + steps_part) / 2
    return steps_part or 0.0


def format_money(amount: float) -> str:
    """12 500 ₽ / 1 234,50 ₽ — с неразрывными пробелами между разрядами."""
    neg = amount < 0
    amount = abs(round(amount, 2))
    whole = int(amount)
    frac = round((amount - whole) * 100)
    s = f"{whole:,}".replace(",", "\u00a0")
    if frac:
        s += f",{frac:02d}"
    return ("−" if neg else "") + s + "\u00a0₽"


def parse_money(text: str) -> float | None:
    t = text.replace("\u00a0", "").replace(" ", "").replace("₽", "").replace(",", ".").strip()
    if t.startswith("−"):
        t = "-" + t[1:]
    try:
        return round(float(t), 2)
    except ValueError:
        return None


def goal_sort_key(goal: Goal) -> tuple:
    """Активные выше достигнутых, затем ближайший срок, без срока — в конце."""
    return (goal.done, goal.target_date is None, goal.target_date or date.max, goal.id)


def active_goals(goals: Iterable[Goal]) -> list[Goal]:
    return sorted((g for g in goals if not g.archived and not g.done), key=goal_sort_key)


# ---------- Заметки ----------

@dataclass
class NoteFolder:
    id: int
    name: str


FOLDER_ALL = -1     # «Все заметки»
FOLDER_NONE = 0     # «Без папки»


@dataclass
class Note:
    id: int
    title: str = ""
    body: str = ""
    pinned: bool = False
    created_at: str = ""
    updated_at: str = ""
    folder_id: int | None = None

    @property
    def display_title(self) -> str:
        if self.title.strip():
            return self.title.strip()
        first = next((ln.strip() for ln in self.body.splitlines() if ln.strip()), "")
        return first[:60] or "Без названия"


def sort_notes(notes: Iterable[Note]) -> list[Note]:
    """Закреплённые сверху, затем по времени изменения (новые выше)."""
    newest_first = sorted(notes, key=lambda n: (n.updated_at, n.id), reverse=True)
    return sorted(newest_first, key=lambda n: not n.pinned)  # сортировка устойчивая


def filter_by_folder(notes: Iterable[Note], folder_id: int) -> list[Note]:
    if folder_id == FOLDER_ALL:
        return list(notes)
    if folder_id == FOLDER_NONE:
        return [n for n in notes if n.folder_id is None]
    return [n for n in notes if n.folder_id == folder_id]


UPCOMING_CHOICES = [(4, "4 дня"), (7, "Неделя"), (14, "Две недели")]


def search_notes(notes: Iterable[Note], query: str) -> list[Note]:
    q = query.strip().lower()
    if not q:
        return list(notes)
    return [n for n in notes if q in n.title.lower() or q in n.body.lower()]


# ---------- Тексты ----------

def plural(n: int, one: str, few: str, many: str) -> str:
    """plural(3, 'день', 'дня', 'дней') -> 'дня'."""
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def due_text(deadline: date, today: date) -> str:
    """Человеческое описание срока: «сегодня», «завтра», «через 3 дня», «просрочено на 2 дня»."""
    delta = (deadline - today).days
    if delta == 0:
        return "сегодня"
    if delta == 1:
        return "завтра"
    if delta > 1:
        return f"через {delta} {plural(delta, 'день', 'дня', 'дней')}"
    late = -delta
    return f"просрочено на {late} {plural(late, 'день', 'дня', 'дней')}"
