"""Чистая логика: стрики, статистика, сортировка задач. Без Qt и без БД."""
from __future__ import annotations

from dataclasses import dataclass, field
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
    board_id: int | None = None      # задача-карточка доски (канбан); в обычном списке задач её нет
    column_id: int | None = None
    position: float = 0.0
    repeat: str | None = None        # правило повтора, см. next_due(): "d:1", "w:1:0,2", "m:1:15", "m:1:-1", "y:1"
    labels: str = ""                 # метки через запятую: «срочно,ждёт ответа»
    goal_id: int | None = None       # шаг к цели: выполненная задача двигает прогресс цели
    note_id: int | None = None       # связанная заметка

    @property
    def label_list(self) -> list[str]:
        return parse_labels(self.labels)


@dataclass
class Board:
    id: int
    name: str
    color: str = "#0F6E6A"
    position: int = 0
    archived: bool = False


@dataclass
class BoardColumn:
    id: int
    board_id: int
    name: str
    position: int = 0
    is_done: bool = False


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


def goal_progress(goal: Goal, steps: list[GoalStep], saved: float = 0.0,
                  linked: Iterable[bool] = ()) -> float:
    """Доля 0..1.

    Обычная цель — по выполненным шагам (и привязанным к ней задачам — linked: выполнена ли каждая).
    Финансовая — по накопленной сумме, а если у неё есть шаги, то поровну: половина — деньги,
    половина — шаги. Достигнутая цель — всегда 1.
    """
    if goal.done:
        return 1.0
    marks = [s.done for s in steps] + list(linked)
    steps_part = sum(1 for d in marks if d) / len(marks) if marks else None
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
class Attachment:
    id: int
    note_id: int
    name: str
    file: str          # имя файла в папке attachments
    size: int = 0
    mime: str = ""
    created_at: str = ""


@dataclass
class Note:
    id: int
    title: str = ""
    body: str = ""
    pinned: bool = False
    created_at: str = ""
    updated_at: str = ""
    folder_id: int | None = None
    board_id: int | None = None

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


# ---------------------------------------------------------------- быстрое добавление задачи

_WEEKDAYS = {
    "пн": 0, "понедельник": 0, "вт": 1, "вторник": 1, "ср": 2, "среда": 2, "среду": 2,
    "чт": 3, "четверг": 3, "пт": 4, "пятница": 4, "пятницу": 4, "сб": 5, "суббота": 5, "субботу": 5,
    "вс": 6, "воскресенье": 6,
}
_WD_SHORT = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
_MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября",
               "октября", "ноября", "декабря"]
_REL = {"сегодня": 0, "завтра": 1, "послезавтра": 2}


@dataclass
class QuickTask:
    title: str
    deadline: date | None = None
    topic_id: int | None = None
    priority: int = PRIORITY_MEDIUM
    hints: list[str] = field(default_factory=list)   # что распознано — для подсказки под строкой
    repeat: str | None = None
    labels: list[str] = field(default_factory=list)


def _parse_date(word: str, today: date) -> date | None:
    import re
    m = re.fullmatch(r"(\d{1,2})\.(\d{1,2})(?:\.(\d{2}|\d{4}))?", word)
    if not m:
        return None
    d, mo, y = int(m.group(1)), int(m.group(2)), m.group(3)
    year = (2000 + int(y) if len(y) == 2 else int(y)) if y else today.year
    try:
        res = date(year, mo, d)
    except ValueError:
        return None
    if not y and res < today:          # «12.01» в ноябре — это следующий январь
        try:
            res = date(year + 1, mo, d)
        except ValueError:
            return None
    return res


def parse_quick_task(text: str, topics: Iterable[Topic], today: date,
                     default_topic: int | None = None) -> QuickTask:
    """«Купить молоко завтра #дом !» → задача со сроком, темой и высоким приоритетом.

    Понимает: сегодня / завтра / послезавтра, день недели («в пятницу», «пт» — ближайший
    следующий), дату «12.11» или «12.11.2026», «#тема» (по началу названия), «!» — высокий приоритет.
    Распознанные слова из названия убираются; остальное остаётся как есть.
    """
    topics = list(topics)
    words = text.split()
    keep: list[str] = []
    q = QuickTask("", topic_id=default_topic)
    i = 0
    while i < len(words):
        raw = words[i]
        low = raw.lower().strip(",.")
        nxt = words[i + 1].lower().strip(",.") if i + 1 < len(words) else ""
        rep_rule, used = _repeat_phrase(low, nxt)
        if rep_rule and q.repeat is None:
            q.repeat = rep_rule
            if used == 2:
                i += 1
            if rep_rule.startswith("w:1:") and q.deadline is None and "," not in rep_rule:
                q.deadline = _next_weekday(today, int(rep_rule.split(":")[2]))
        elif raw.startswith("@") and len(raw) > 1:
            q.labels.append(raw[1:].strip(",."))
        elif raw in ("!", "!!", "!!!"):
            q.priority = PRIORITY_HIGH
        elif low in _REL and q.deadline is None:
            q.deadline = today + timedelta(days=_REL[low])
        elif low in ("в", "во") and nxt in _WEEKDAYS and q.deadline is None:
            q.deadline = _next_weekday(today, _WEEKDAYS[nxt])
            i += 1
        elif low in _WEEKDAYS and q.deadline is None:
            q.deadline = _next_weekday(today, _WEEKDAYS[low])
        elif raw.startswith("#") and len(raw) > 1:
            name = raw[1:].lower()
            exact = [t for t in topics if t.name.lower().replace(" ", "") == name]
            starts = [t for t in topics if t.name.lower().startswith(name)]
            hit = (exact or starts or [None])[0]
            if hit is not None:
                q.topic_id = hit.id
            else:
                keep.append(raw)
        elif q.deadline is None and (d := _parse_date(raw.strip(","), today)) is not None:
            q.deadline = d
        else:
            keep.append(raw)
        i += 1
    q.title = " ".join(keep).strip()
    if q.repeat and q.deadline is None:
        q.deadline = today
    if q.deadline is not None:
        d = q.deadline
        q.hints.append(f"срок: {_WD_SHORT[d.weekday()]}, {d.day} {_MONTHS_GEN[d.month - 1]}"
                       + (f" {d.year}" if d.year != today.year else "") + f" ({due_text(d, today)})")
    if q.topic_id is not None:
        t = next((t for t in topics if t.id == q.topic_id), None)
        if t:
            q.hints.append("тема: " + t.name)
    if q.repeat:
        q.hints.append("повтор: " + repeat_text(q.repeat).lower())
    if q.labels:
        q.hints.append("метки: " + ", ".join(q.labels))
    if q.priority == PRIORITY_HIGH:
        q.hints.append("высокий приоритет")
    return q


_WD_ACC = {"понедельник": 0, "вторник": 1, "среду": 2, "четверг": 3, "пятницу": 4, "субботу": 5,
           "воскресенье": 6}
_EVERY_WD = {"каждый": ("понедельник", "вторник", "четверг"), "каждую": ("среду", "пятницу", "субботу"),
             "каждое": ("воскресенье",)}


def _repeat_phrase(w1: str, w2: str) -> tuple[str | None, int]:
    """«каждый день», «по будням», «еженедельно», «каждую пятницу» → (правило, сколько слов занято)."""
    single = {"ежедневно": "d:1", "еженедельно": "w:1", "ежемесячно": "m:1", "ежегодно": "y:1"}
    if w1 in single:
        return single[w1], 1
    pairs = {("каждый", "день"): "d:1", ("по", "будням"): "w:1:0,1,2,3,4", ("каждую", "неделю"): "w:1",
             ("каждый", "месяц"): "m:1", ("каждый", "год"): "y:1"}
    if (w1, w2) in pairs:
        return pairs[(w1, w2)], 2
    if w1 in _EVERY_WD and w2 in _EVERY_WD[w1]:
        return f"w:1:{_WD_ACC[w2]}", 2
    return None, 0


def _next_weekday(today: date, wd: int) -> date:
    delta = (wd - today.weekday()) % 7
    return today + timedelta(days=delta or 7)



# ---------------------------------------------------------------- повторяющиеся задачи и метки

REPEAT_CHOICES = [(None, "Не повторять"), ("d:1", "Каждый день"), ("w:1:0,1,2,3,4", "По будням"),
                  ("w:1", "Каждую неделю"), ("w:2", "Раз в две недели"), ("m:1", "Каждый месяц"),
                  ("m:1:-1", "В последний день месяца"), ("y:1", "Каждый год")]


def _parse_rule(rule: str) -> tuple[str, int, list[int]]:
    parts = rule.split(":")
    kind = parts[0]
    n = max(1, int(parts[1])) if len(parts) > 1 and parts[1].lstrip("-").isdigit() else 1
    extra = [int(x) for x in parts[2].split(",") if x.strip().lstrip("-").isdigit()] if len(parts) > 2 else []
    return kind, n, extra


def _add_months(d: date, months: int, day: int) -> date:
    import calendar
    y, m = divmod(d.month - 1 + months, 12)
    y, m = d.year + y, m + 1
    last = calendar.monthrange(y, m)[1]
    return date(y, m, last if day == -1 or day > last else day)


def next_due(rule: str, due: date | None, today: date) -> date:
    """Следующий срок повторяющейся задачи — первый после прежнего срока и не раньше сегодня.

    d:N — каждые N дней; w:N[:дни] — каждые N недель (дни 0=пн…6=вс, по умолчанию день срока);
    m:N[:число] — каждые N месяцев (−1 — последний день); y:N — каждые N лет.
    """
    kind, n, extra = _parse_rule(rule)
    base = due or today

    def step(d: date) -> date:
        if kind == "d":
            return d + timedelta(days=n)
        if kind == "w":
            days = sorted(set(extra)) or [base.weekday()]
            x = d + timedelta(days=1)
            for _ in range(7 * n + 7):
                weeks = ((x - timedelta(days=x.weekday())) - (base - timedelta(days=base.weekday()))).days // 7
                if x.weekday() in days and weeks % n == 0:
                    return x
                x += timedelta(days=1)
            return d + timedelta(weeks=n)
        if kind == "m":
            return _add_months(d, n, extra[0] if extra else base.day)
        if kind == "y":
            return _add_months(d, 12 * n, base.day)
        return d + timedelta(days=1)

    nxt = step(base)
    guard = 0
    while nxt < today and guard < 2000:        # давно просрочено — сразу на ближайший будущий срок
        nxt = step(nxt)
        guard += 1
    return nxt


def repeat_text(rule: str | None) -> str:
    if not rule:
        return "Не повторять"
    for r, name in REPEAT_CHOICES:
        if r == rule:
            return name
    kind, n, extra = _parse_rule(rule)
    wd = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
    if kind == "d":
        return f"Каждые {n} {plural(n, 'день', 'дня', 'дней')}" if n > 1 else "Каждый день"
    if kind == "w":
        days = ", ".join(wd[d] for d in sorted(set(extra)) if 0 <= d < 7)
        head = "Каждую неделю" if n == 1 else f"Раз в {n} {plural(n, 'неделю', 'недели', 'недель')}"
        return head + (f": {days}" if days else "")
    if kind == "m":
        head = "Каждый месяц" if n == 1 else f"Раз в {n} {plural(n, 'месяц', 'месяца', 'месяцев')}"
        return head + (", в последний день" if extra and extra[0] == -1 else f", {extra[0]}-го" if extra else "")
    if kind == "y":
        return "Каждый год" if n == 1 else f"Раз в {n} {plural(n, 'год', 'года', 'лет')}"
    return "Повтор"


def parse_labels(text: str) -> list[str]:
    seen, out = set(), []
    for part in (text or "").replace(";", ",").split(","):
        name = part.strip().lstrip("#").strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
    return out


LABEL_COLORS = ["#B42318", "#B45309", "#15803D", "#0F6E6A", "#1D4ED8", "#7E22CE", "#BE185D", "#374151"]


def label_color(name: str) -> str:
    """Цвет метки — один и тот же на всех устройствах (по названию)."""
    h = 0
    for ch in name.lower():
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return LABEL_COLORS[h % len(LABEL_COLORS)]
