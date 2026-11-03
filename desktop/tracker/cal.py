"""Логика календаря: события, повторы, раскладка пересекающихся событий. Без Qt и без БД."""
from __future__ import annotations

import calendar as _cal
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

# Цвета событий (как в Google Календаре); белый текст на каждом ≥ 4.5:1.
EVENT_COLORS = [
    ("#0B6E69", "Бирюзовый"), ("#3F51B5", "Черничный"), ("#7B1FA2", "Виноградный"),
    ("#C2185B", "Фламинго"), ("#C62828", "Томатный"), ("#B4530A", "Мандариновый"),
    ("#2E7D32", "Базилик"), ("#455A64", "Графит"),
]

FREQ_NONE, FREQ_DAILY, FREQ_WEEKLY, FREQ_MONTHLY, FREQ_YEARLY = "", "daily", "weekly", "monthly", "yearly"
FREQ_NAMES = {FREQ_NONE: "Не повторять", FREQ_DAILY: "Каждый день", FREQ_WEEKLY: "Каждую неделю",
              FREQ_MONTHLY: "Каждый месяц", FREQ_YEARLY: "Каждый год"}

REMINDER_CHOICES = [(None, "Без напоминания"), (0, "В момент начала"), (5, "За 5 минут"),
                    (10, "За 10 минут"), (15, "За 15 минут"), (30, "За 30 минут"),
                    (60, "За 1 час"), (120, "За 2 часа"), (1440, "За 1 день")]


@dataclass
class CalendarInfo:
    id: int
    name: str
    color: str
    visible: bool = True


@dataclass
class Event:
    id: int
    title: str
    start: datetime
    end: datetime
    all_day: bool = False
    calendar_id: int | None = None
    color: str | None = None          # своё; иначе цвет календаря
    description: str = ""
    location: str = ""
    freq: str = FREQ_NONE
    interval: int = 1
    weekdays: list[int] = field(default_factory=list)   # 0=пн; для еженедельных
    until: date | None = None
    exdates: list[date] = field(default_factory=list)   # удалённые/изменённые вхождения
    reminder: int | None = None       # минут до начала

    @property
    def duration(self) -> timedelta:
        return self.end - self.start

    @property
    def recurring(self) -> bool:
        return self.freq != FREQ_NONE


@dataclass
class Occurrence:
    event: Event
    start: datetime
    end: datetime

    @property
    def key(self) -> tuple:
        return (self.event.id, self.start)


# ---------------------------------------------------------------- повторы

def _add_months(d: date, months: int) -> date | None:
    """Тот же день месяца через n месяцев; если такого дня нет (31-е) — None, как в Google."""
    m = d.month - 1 + months
    y, m = d.year + m // 12, m % 12 + 1
    if d.day > _cal.monthrange(y, m)[1]:
        return None
    return date(y, m, d.day)


def _start_dates(ev: Event, until: date):
    """Все даты начала вхождений по порядку до `until` включительно."""
    first = ev.start.date()
    limit = min(until, ev.until) if ev.until else until
    step = max(1, ev.interval)
    if ev.freq == FREQ_NONE:
        if first <= limit:
            yield first
        return
    if ev.freq == FREQ_DAILY:
        d = first
        while d <= limit:
            yield d
            d += timedelta(days=step)
    elif ev.freq == FREQ_WEEKLY:
        days = sorted(set(ev.weekdays)) or [first.weekday()]
        week0 = first - timedelta(days=first.weekday())
        k = 0
        while True:
            ws = week0 + timedelta(weeks=k * step)
            if ws > limit:
                return
            for wd in days:
                d = ws + timedelta(days=wd)
                if first <= d <= limit:
                    yield d
            k += 1
    elif ev.freq in (FREQ_MONTHLY, FREQ_YEARLY):
        months = step if ev.freq == FREQ_MONTHLY else 12 * step
        k = 0
        while True:
            d = _add_months(first, k * months)
            k += 1
            if d is None:
                if k > 2400:
                    return
                continue
            if d > limit:
                return
            yield d


def occurrences(events: list[Event], start: datetime, end: datetime) -> list[Occurrence]:
    """Вхождения, пересекающие [start, end), отсортированные по времени."""
    result = []
    for ev in events:
        dur = ev.duration
        lookback = start.date() - timedelta(days=max(0, dur.days) + 1)
        for d in _start_dates(ev, (end - timedelta(microseconds=1)).date()):
            if d < lookback:
                continue
            if d in ev.exdates:
                continue
            s = datetime.combine(d, ev.start.time())
            e = s + dur
            if e > start and s < end or (dur == timedelta(0) and start <= s < end):
                result.append(Occurrence(ev, s, e))
    result.sort(key=lambda o: (not o.event.all_day, o.start, -(o.end - o.start).total_seconds(), o.event.id))
    return result


def on_day(occs: list[Occurrence], day: date) -> list[Occurrence]:
    s = datetime.combine(day, time.min)
    e = s + timedelta(days=1)
    return [o for o in occs if o.end > s and o.start < e or (o.start == o.end and s <= o.start < e)]


# ---------------------------------------------------------------- раскладка дня

def layout_columns(items: list[tuple[float, float]]) -> list[tuple[int, int]]:
    """Пересекающиеся события делят ширину: для каждого (начало, конец) → (колонка, всего колонок).

    Как в Google: события группируются в «кластеры» пересечений, внутри — жадно по колонкам.
    """
    order = sorted(range(len(items)), key=lambda i: (items[i][0], -items[i][1]))
    result: list[tuple[int, int]] = [(0, 1)] * len(items)
    cluster: list[int] = []
    col_end: list[float] = []
    cluster_end = float("-inf")

    def close():
        n = len(col_end)
        for i in cluster:
            result[i] = (result[i][0], n)

    for i in order:
        s, e = items[i]
        e = max(e, s + 0.25)   # совсем короткие всё равно видны
        if s >= cluster_end and cluster:
            close()
            cluster, col_end = [], []
        for c, ce in enumerate(col_end):
            if ce <= s:
                col_end[c] = e
                break
        else:
            c = len(col_end)
            col_end.append(e)
        result[i] = (c, 0)
        cluster.append(i)
        cluster_end = max(cluster_end, e)
    if cluster:
        close()
    return result


# ---------------------------------------------------------------- даты

def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def month_grid(year: int, month: int) -> list[list[date]]:
    """6 недель × 7 дней, начиная с понедельника — как сетка месяца в Google."""
    first = date(year, month, 1)
    start = week_start(first)
    return [[start + timedelta(days=w * 7 + d) for d in range(7)] for w in range(6)]


def snap(dt: datetime, minutes: int = 15) -> datetime:
    total = dt.hour * 60 + dt.minute
    total = round(total / minutes) * minutes
    return datetime.combine(dt.date(), time.min) + timedelta(minutes=total)


def due_reminders(occs: list[Occurrence], now: datetime, window: timedelta,
                  done: set) -> list[Occurrence]:
    """Вхождения, чьё напоминание наступило в (now - window, now] и ещё не показано."""
    out = []
    for o in occs:
        if o.event.reminder is None or o.key in done:
            continue
        at = o.start - timedelta(minutes=o.event.reminder)
        if now - window < at <= now:
            out.append(o)
    return out


def recurrence_text(ev: Event) -> str:
    if not ev.recurring:
        return ""
    names = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
    n = ev.interval
    base = {
        FREQ_DAILY: "каждый день" if n == 1 else f"каждые {n} дн.",
        FREQ_WEEKLY: "каждую неделю" if n == 1 else f"каждые {n} нед.",
        FREQ_MONTHLY: f"каждый месяц, {ev.start.day}-го" if n == 1 else f"каждые {n} мес.",
        FREQ_YEARLY: "каждый год" if n == 1 else f"каждые {n} г.",
    }[ev.freq]
    if ev.freq == FREQ_WEEKLY and ev.weekdays:
        base += ": " + ", ".join(names[d] for d in sorted(ev.weekdays))
    if ev.until:
        base += f", до {ev.until:%d.%m.%Y}"
    return base.capitalize()
