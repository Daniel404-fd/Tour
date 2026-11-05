from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication, QDialog, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMainWindow, QMenu, QSplitter, QStackedWidget, QSystemTrayIcon, QToolButton, QVBoxLayout, QWidget,
)

from .. import cal
from ..db import Database
from . import icons
from .calendar_tab import CalendarPage
from .goals_tab import GoalsPage
from .habits_tab import HabitsPage
from .boards_tab import BoardsPage
from .home_tab import HomePage
from .notes_tab import NotesPage
from .security import LoginDialog
from .settings_tab import SettingsPage
from .sync_controller import SyncController
from .stats_tab import StatsPage
from .tasks_tab import TasksPage
from .theme import repolish as theme_repolish, theme

SECTIONS = [
    ("home", "Главная", HomePage),
    ("calendar", "Календарь", CalendarPage),
    ("habits", "Привычки", HabitsPage),
    ("tasks", "Задачи", TasksPage),
    ("boards", "Доски", BoardsPage),
    ("goals", "Цели", GoalsPage),
    ("notes", "Заметки", NotesPage),
    ("stats", "Статистика", StatsPage),
    ("settings", "Настройки", SettingsPage),
]
HOME, CALENDAR, HABITS, TASKS, BOARDS, GOALS, NOTES, STATS, SETTINGS = range(len(SECTIONS))
SIDEBAR_MIN, SIDEBAR_DEFAULT, SIDEBAR_MAX, SIDEBAR_ICONS = 150, 210, 340, 60
KEY_INDEX = {key: i for i, (key, _, _) in enumerate(SECTIONS)}


class SidebarPanel(QWidget):
    """Подложка боковой панели: цвет или картинка (с затемнением, чтобы читались подписи)."""

    def __init__(self):
        super().__init__()
        self._path = None
        self._pix: QPixmap | None = None

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme["sidebar_bg"]))
        path = theme.t.get("sidebar_image") or ""
        import os
        key = (path, os.path.getmtime(path) if path and os.path.exists(path) else 0)
        if key != self._path:
            self._path = key
            pix = QPixmap(path) if path else QPixmap()
            self._pix = None if pix.isNull() else pix
        if self._pix is not None:
            # «заполнить»: масштаб с сохранением пропорций, лишнее обрезается по центру
            scaled = self._pix.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            x = (scaled.width() - self.width()) // 2
            y = (scaled.height() - self.height()) // 2
            p.drawPixmap(0, 0, scaled, x, y, self.width(), self.height())
            dim = float(theme.t.get("sidebar_dim", 0.4))
            if dim > 0:
                p.fillRect(self.rect(), QColor(0, 0, 0, int(255 * dim)))
        p.end()


class MainWindow(QMainWindow):
    def __init__(self, session):
        super().__init__()
        self.session = session
        self.db: Database = session.db
        self.setWindowTitle("Трекер привычек и задач")
        self.resize(1180, 780)
        self.setMinimumSize(820, 600)

        # отложенная запись на диск: много правок подряд — одна запись (плавнее), не позже чем через 0,4 с
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(400)
        self.save_timer.timeout.connect(self.db.flush_save)
        self.db.save_later = self.save_timer.start

        # окно = боковая панель | разделы; границу можно тянуть мышью, панель — свернуть до иконок
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setObjectName("mainSplit")
        self.splitter.setHandleWidth(1)
        self.splitter.setChildrenCollapsible(True)

        self.sidebar = QListWidget()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFrameShape(QListWidget.NoFrame)
        self.sidebar.setIconSize(QSize(18, 18))
        self.sidebar.setAccessibleName("Разделы")
        self.sidebar.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.sidebar.viewport().setAutoFillBackground(False)
        for i, (_, title, _) in enumerate(SECTIONS):
            item = QListWidgetItem(title)
            item.setToolTip(f"{title} (Ctrl+{i + 1})" if i < 9 else title)
            self.sidebar.addItem(item)
        self.sidebar_panel = SidebarPanel()
        self.sidebar_panel.setMinimumWidth(SIDEBAR_ICONS)
        self.sidebar_panel.setMaximumWidth(SIDEBAR_MAX)
        sp = QVBoxLayout(self.sidebar_panel)
        sp.setContentsMargins(0, 0, 0, 0)
        sp.setSpacing(0)
        top = QHBoxLayout()
        top.setContentsMargins(16, 14, 8, 0)
        self.app_title = QLabel("Трекер")
        self.app_title.setObjectName("appTitle")
        self.collapse_btn = QToolButton()
        self.collapse_btn.setObjectName("collapseBtn")
        self.collapse_btn.setAutoRaise(True)
        self.collapse_btn.setCursor(Qt.PointingHandCursor)
        self.collapse_btn.clicked.connect(self.toggle_sidebar)
        top.addWidget(self.app_title, 1)
        top.addWidget(self.collapse_btn)
        sp.addLayout(top)
        sp.addWidget(self.sidebar, 1)
        self.splitter.addWidget(self.sidebar_panel)

        self.stack = QStackedWidget()
        self.splitter.addWidget(self.stack)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setCollapsible(1, False)
        self.setCentralWidget(self.splitter)
        self._fade = None
        try:
            w0, collapsed = self.db.get_pref("ui_sidebar", f"{SIDEBAR_DEFAULT}:0").split(":")
            self._sidebar_w = max(SIDEBAR_MIN, min(SIDEBAR_MAX, int(w0)))
            self._collapsed = collapsed == "1"
        except ValueError:
            self._sidebar_w, self._collapsed = SIDEBAR_DEFAULT, False
        self.splitter.setSizes([SIDEBAR_ICONS if self._collapsed else self._sidebar_w, 1000])
        self._apply_sidebar_mode()
        self.splitter.splitterMoved.connect(self._sidebar_dragged)

        self.pages: list[QWidget] = []
        self.sync = SyncController(session, self._flush)
        self.sync.dataChanged.connect(self._on_remote_changes)
        self._build_pages()
        self.sidebar.currentRowChanged.connect(self._on_section_changed)
        self.sidebar.setCurrentRow(HOME)

        for i in range(min(9, len(SECTIONS))):
            QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self,
                      activated=lambda i=i: self.sidebar.setCurrentRow(i))
        QShortcut(QKeySequence("Ctrl+\\"), self, activated=self.toggle_sidebar)
        QShortcut(QKeySequence.New, self, activated=self._new_item)
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self.lock)
        theme.changed.connect(self._on_theme_changed)
        self._setup_reminders()
        QTimer.singleShot(1500, self.sync.run)   # синхронизация вскоре после запуска

    # ---- боковая панель: свернуть до иконок, тянуть мышью ----

    def _apply_sidebar_mode(self) -> None:
        c = self._collapsed
        for i, (key, title, _) in enumerate(SECTIONS):
            self.sidebar.item(i).setText("" if c else title)
            self.sidebar.item(i).setTextAlignment(Qt.AlignCenter if c else Qt.AlignLeft | Qt.AlignVCenter)
        self.sidebar.setProperty("collapsed", "true" if c else "false")
        # развёрнутая панель не бывает уже SIDEBAR_MIN — иначе подписи обрезаются («Гл», «Тре»)
        self.sidebar_panel.setMinimumWidth(SIDEBAR_ICONS if c else SIDEBAR_MIN)
        theme_repolish(self.sidebar)
        self.app_title.setVisible(not c)
        self.collapse_btn.setIcon(icons.icon("chevrons-right" if c else "chevrons-left", theme["sidebar_icon"]))
        self.collapse_btn.setToolTip(("Развернуть" if c else "Свернуть") + " боковую панель (Ctrl+\\)")
        self.collapse_btn.setAccessibleName(self.collapse_btn.toolTip())

    def toggle_sidebar(self) -> None:
        self._collapsed = not self._collapsed
        start = self.splitter.sizes()[0]
        end = SIDEBAR_ICONS if self._collapsed else self._sidebar_w
        if not self._collapsed:
            self._apply_sidebar_mode()          # подписи появляются сразу, панель плавно раскрывается
        else:
            self.sidebar_panel.setMinimumWidth(SIDEBAR_ICONS)   # чтобы панель могла плавно сузиться
        anim = QVariantAnimation(self)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setDuration(180)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        total = sum(self.splitter.sizes())
        anim.valueChanged.connect(lambda v: self.splitter.setSizes([int(v), total - int(v)]))
        if self._collapsed:
            anim.finished.connect(self._apply_sidebar_mode)
        anim.start(QVariantAnimation.DeleteWhenStopped)
        self._save_sidebar()

    def _sidebar_dragged(self, pos: int, _index: int) -> None:
        total = sum(self.splitter.sizes())
        if self._collapsed:
            if pos > SIDEBAR_ICONS + 50:          # вытянули из свёрнутой — разворачиваем
                self._collapsed = False
                self._apply_sidebar_mode()
                self._sidebar_w = max(SIDEBAR_MIN, min(SIDEBAR_MAX, pos))
                self.splitter.setSizes([self._sidebar_w, total - self._sidebar_w])
            else:
                self.splitter.setSizes([SIDEBAR_ICONS, total - SIDEBAR_ICONS])
        elif pos <= SIDEBAR_MIN - 10 or self.splitter.sizes()[0] == 0:
            # протянули к краю (Qt «схлопнул» панель) — оставляем полосу иконок
            self._collapsed = True
            self._apply_sidebar_mode()
            self.splitter.setSizes([SIDEBAR_ICONS, total - SIDEBAR_ICONS])
        else:
            self._sidebar_w = max(SIDEBAR_MIN, min(SIDEBAR_MAX, pos))
        self._save_sidebar()

    def _save_sidebar(self) -> None:
        self.db.set_pref("ui_sidebar", f"{self._sidebar_w}:{int(self._collapsed)}")

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
                icons.icon(key, theme["sidebar_icon"], selected=theme["sidebar_text"]))
        self.sidebar_panel.update()
        self.app_title.setStyleSheet(f"color: {theme['sidebar_text']};")
        self._apply_sidebar_mode()
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
        self._fade_in(self.pages[index])

    def _fade_in(self, page: QWidget) -> None:
        """Короткое плавное появление раздела (120 мс) — переход не «дёргается»."""
        if self._fade is not None:
            self._fade.stop()
        eff = QGraphicsOpacityEffect(page)
        page.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(120)
        anim.setEasingCurve(QEasingCurve.OutQuad)

        def done():
            if page.graphicsEffect() is eff:
                page.setGraphicsEffect(None)     # без эффекта страница рисуется быстрее
        anim.finished.connect(done)
        anim.start()
        self._fade = anim

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
        self.db.flush_save()

    def _on_remote_changes(self) -> None:
        page = self.pages[self.stack.currentIndex()]
        page.refresh()

    def closeEvent(self, event) -> None:
        self._flush()
        self.sync.sync_blocking()
        super().closeEvent(event)
