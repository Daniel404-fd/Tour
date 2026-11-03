from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QDialog, QHBoxLayout, QListWidget, QListWidgetItem, QMainWindow, QMenu,
    QStackedWidget, QSystemTrayIcon, QWidget,
)

from .. import cal
from ..db import Database
from . import icons
from .calendar_tab import CalendarPage
from .goals_tab import GoalsPage
from .habits_tab import HabitsPage
from .home_tab import HomePage
from .notes_tab import NotesPage
from .security import LoginDialog
from .settings_tab import SettingsPage
from .sync_controller import SyncController
from .stats_tab import StatsPage
from .tasks_tab import TasksPage
from .theme import theme

SECTIONS = [
    ("home", "Главная", HomePage),
    ("calendar", "Календарь", CalendarPage),
    ("habits", "Привычки", HabitsPage),
    ("tasks", "Задачи", TasksPage),
    ("goals", "Цели", GoalsPage),
    ("notes", "Заметки", NotesPage),
    ("stats", "Статистика", StatsPage),
    ("settings", "Настройки", SettingsPage),
]
HOME, CALENDAR, HABITS, TASKS, GOALS, NOTES, STATS, SETTINGS = range(len(SECTIONS))
KEY_INDEX = {key: i for i, (key, _, _) in enumerate(SECTIONS)}


class MainWindow(QMainWindow):
    def __init__(self, session):
        super().__init__()
        self.session = session
        self.db: Database = session.db
        self.setWindowTitle("Трекер привычек и задач")
        self.resize(1180, 780)
        self.setMinimumSize(820, 600)

        central = QWidget()
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFrameShape(QListWidget.NoFrame)
        self.sidebar.setFixedWidth(200)
        self.sidebar.setIconSize(QSize(20, 20))
        self.sidebar.setAccessibleName("Разделы")
        self.sidebar.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        for i, (_, title, _) in enumerate(SECTIONS):
            item = QListWidgetItem(title)
            item.setToolTip(f"{title} (Ctrl+{i + 1})")
            self.sidebar.addItem(item)
        lay.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)
        self.setCentralWidget(central)

        self.pages: list[QWidget] = []
        self.sync = SyncController(session, self._flush)
        self.sync.dataChanged.connect(self._on_remote_changes)
        self._build_pages()
        self.sidebar.currentRowChanged.connect(self._on_section_changed)
        self.sidebar.setCurrentRow(HOME)

        for i in range(len(SECTIONS)):
            QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self,
                      activated=lambda i=i: self.sidebar.setCurrentRow(i))
        QShortcut(QKeySequence.New, self, activated=self._new_item)
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self.lock)
        theme.changed.connect(self._on_theme_changed)
        self._setup_reminders()
        QTimer.singleShot(1500, self.sync.run)   # синхронизация вскоре после запуска

    # ---- напоминания календаря ----

    def _setup_reminders(self) -> None:
        """Пока программа открыта, раз в 30 с проверяем напоминания и показываем уведомление Windows."""
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(QApplication.windowIcon() or QIcon(), self)
            self.tray.setToolTip("Трекер привычек и задач")
            menu = QMenu()
            menu.addAction("Открыть", self._bring_to_front)
            menu.addAction("Календарь", lambda: (self._bring_to_front(), self.navigate("calendar")))
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(lambda reason: self._bring_to_front()
                                        if reason == QSystemTrayIcon.Trigger else None)
            self.tray.messageClicked.connect(lambda: (self._bring_to_front(), self.navigate("calendar")))
            self.tray.show()
        self._reminded: set = set()
        self._last_check = datetime.now()
        self.reminder_timer = QTimer(self)
        self.reminder_timer.timeout.connect(self.check_reminders)
        self.reminder_timer.start(30_000)

    def check_reminders(self) -> None:
        now = datetime.now()
        window = max(timedelta(seconds=35), now - self._last_check + timedelta(seconds=5))
        self._last_check = now
        visible = {c.id for c in self.db.list_calendars() if c.visible}
        events = [e for e in self.db.list_events() if e.reminder is not None and e.calendar_id in visible]
        if not events:
            return
        occs = cal.occurrences(events, now - timedelta(days=1), now + timedelta(days=2))
        for o in cal.due_reminders(occs, now, window, self._reminded):
            self._reminded.add(o.key)
            when = "весь день" if o.event.all_day else f"{o.start:%H:%M}–{o.end:%H:%M}"
            mins = o.event.reminder
            lead = ("Сейчас" if mins == 0 else f"Через {mins} мин" if mins < 60
                    else f"Через {mins // 60} ч" if mins < 1440 else "Завтра")
            title = o.event.title or "(без названия)"
            text = f"{lead}: {when}" + (f", {o.event.location}" if o.event.location else "")
            if self.tray is not None:
                self.tray.showMessage(title, text, QSystemTrayIcon.Information, 15_000)
            QApplication.alert(self, 0)

    def _bring_to_front(self) -> None:
        if self.isHidden():
            return   # заблокировано — окно входа уже на экране
        self.showNormal()
        self.raise_()
        self.activateWindow()

    # ---- страницы ----

    def _build_pages(self) -> None:
        current = self.stack.currentIndex()
        for page in self.pages:
            self.stack.removeWidget(page)
            page.deleteLater()
        self.pages = [cls(self.db, self.navigate, self.session, self) if cls is SettingsPage
                      else cls(self.db, self.navigate) for _, _, cls in SECTIONS]
        for page in self.pages:
            self.stack.addWidget(page)
        for i, (key, _, _) in enumerate(SECTIONS):
            self.sidebar.item(i).setIcon(
                icons.icon(key, theme["teal_text"], selected=theme["teal_text"]))
        if current >= 0:
            self.stack.setCurrentIndex(current)

    def _on_theme_changed(self) -> None:
        self._flush()
        self._build_pages()
        self.pages[self.stack.currentIndex()].refresh()

    def _on_section_changed(self, index: int) -> None:
        if index < 0:
            return
        self._flush()
        self.stack.setCurrentIndex(index)
        # Обновляем при каждом открытии: данные могли поменяться на другой странице
        # или наступил новый день.
        self.pages[index].refresh()

    def navigate(self, index: int | str, **kwargs) -> None:
        """Переход в раздел (номер или ключ: "tasks", "calendar"…); kwargs передаются странице."""
        if isinstance(index, str):
            index = KEY_INDEX[index]
        self.sidebar.setCurrentRow(index)
        if kwargs and hasattr(self.pages[index], "focus_item"):
            self.pages[index].focus_item(**kwargs)

    def reload(self) -> None:
        """Данные заменены (восстановление из копии) — пересобрать все разделы."""
        self._build_pages()
        self.pages[self.stack.currentIndex()].refresh()

    def lock(self) -> None:
        """Скрыть данные до ввода пароля (Ctrl+L). Работает, если пароль задан."""
        if not self.session.encrypted:
            self.sidebar.setCurrentRow(SETTINGS)
            return
        self._flush()
        self.hide()
        dlg = LoginDialog(self.session.data_dir, unlock_only=self.session.keyring)
        if dlg.exec() == QDialog.Accepted:
            self.show()
            self.raise_()
            self.activateWindow()
        else:
            self.close()

    def _new_item(self) -> None:
        page = self.pages[self.stack.currentIndex()]
        if hasattr(page, "new_item"):
            page.new_item()

    def _flush(self) -> None:
        for page in self.pages:
            if hasattr(page, "flush"):
                page.flush()

    def _on_remote_changes(self) -> None:
        page = self.pages[self.stack.currentIndex()]
        page.refresh()

    def closeEvent(self, event) -> None:
        self._flush()
        self.sync.sync_blocking()
        super().closeEvent(event)
