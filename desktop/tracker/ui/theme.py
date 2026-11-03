"""Дизайн-токены и стили. Современная версия классического облика: бирюзовая боковая панель
и синие «кирпичики» прогресса остались, объёмные рамки сменились мягкими скруглениями.
Светлая и тёмная тема следуют системной настройке Windows.

Контраст текста (WCAG), светлая / тёмная:
  text 15.3 / 15.3, text2 7.1 / 9.0, text3 4.9 / 6.1 (на фоне окна);
  белый на бирюзовой панели и кнопках 6.1 / 9.4; accent (индиго) на белом 7.9, в тёмной 5.2;
  danger 6.6 / 7.1, warn 5.9 / 9.9, ссылки 6.1 / 8.8.

Смысл цветов один на всё приложение:
  accent (индиго) — «выполнено / прогресс»;  teal — навигация, главные кнопки и ссылки;
  danger — просрочено и удаление;  warn — срок скоро.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory

LIGHT = {
    "bg": "#F3F2EE", "surface": "#FFFFFF", "surface2": "#F7F6F3", "hover": "#EFEDE7",
    "text": "#1A1C1E", "text2": "#4D5156", "text3": "#666A70",
    "border": "#E1DFD8", "border_strong": "#CFCCC3",
    "light": "#FFFFFF", "shadow": "#CFCCC3", "dark": "#9C978C",
    "accent": "#4338CA", "accent_hover": "#3730A3", "accent_text": "#FFFFFF",
    "accent_soft": "#E8E7FB", "accent_on_soft": "#2E2795",
    "teal": "#0F6E6A", "teal_hover": "#0C5B57", "teal_text": "#FFFFFF",
    "teal_soft": "#E1F0EE", "teal_on_soft": "#0B4F4C", "link": "#0F6E6A",
    "danger": "#B42318", "danger_soft": "#FDECEA",
    "warn": "#8A5A00", "warn_soft": "#FFF3D6",
    "empty": "#E6E4DE", "selection": "#DDEFEC", "tip": "#1A1C1E", "tip_text": "#FFFFFF",
    "chunk_bg": "#ECEAE4", "today_bg": "#E7F3F2", "now": "#D93025",
}

DARK = {
    "bg": "#151719", "surface": "#1E2124", "surface2": "#24282C", "hover": "#2A2E33",
    "text": "#ECEDEE", "text2": "#B3B8BD", "text3": "#9AA0A6",
    "border": "#30343A", "border_strong": "#41464D",
    "light": "#41464D", "shadow": "#0E0F10", "dark": "#0A0A0B",
    "accent": "#8B85F7", "accent_hover": "#A09BF9", "accent_text": "#14123A",
    "accent_soft": "#2B2950", "accent_on_soft": "#CFCCFF",
    "teal": "#0E4F4C", "teal_hover": "#12605C", "teal_text": "#FFFFFF",
    "teal_soft": "#173634", "teal_on_soft": "#8EDBD4", "link": "#5FD1C9",
    "danger": "#FF8A80", "danger_soft": "#3D2220",
    "warn": "#F2C46D", "warn_soft": "#3A2F17",
    "empty": "#2E3237", "selection": "#1F3B39", "tip": "#ECEDEE", "tip_text": "#1A1C1E",
    "chunk_bg": "#2A2E33", "today_bg": "#17302E", "now": "#FF6B5E",
}

FONT_CANDIDATES = ["Segoe UI", "Inter", "Tahoma", "DejaVu Sans"]
FONT_FAMILY = "Segoe UI"
BASE_PT = 10
RADIUS = 10


class _Theme(QObject):
    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.dark = False
        self.t = dict(LIGHT)

    def __getitem__(self, key: str) -> str:
        return self.t[key]

    def color(self, key: str) -> QColor:
        return QColor(self.t[key])


theme = _Theme()


def topic_color(hex_color: str) -> QColor:
    """Цвет метки темы задач; в тёмной теме осветляется, чтобы метка была видна (≥3:1)."""
    c = QColor(hex_color)
    if theme.dark:
        h, s, l, a = c.getHslF()
        c = QColor.fromHslF(h, min(s, 0.7), max(l, 0.62), a)
    return c


def _system_is_dark() -> bool:
    try:
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except Exception:
        return False


def _palette(t: dict) -> QPalette:
    p = QPalette()
    c = lambda k: QColor(t[k])
    p.setColor(QPalette.Window, c("bg"))
    p.setColor(QPalette.WindowText, c("text"))
    p.setColor(QPalette.Base, c("surface"))
    p.setColor(QPalette.AlternateBase, c("surface2"))
    p.setColor(QPalette.Text, c("text"))
    p.setColor(QPalette.PlaceholderText, c("text3"))
    p.setColor(QPalette.Button, c("surface"))
    p.setColor(QPalette.ButtonText, c("text"))
    p.setColor(QPalette.Highlight, c("selection"))
    p.setColor(QPalette.HighlightedText, c("text"))
    p.setColor(QPalette.ToolTipBase, c("tip"))
    p.setColor(QPalette.ToolTipText, c("tip_text"))
    p.setColor(QPalette.Link, c("link"))
    p.setColor(QPalette.Light, c("surface"))
    p.setColor(QPalette.Midlight, c("border"))
    p.setColor(QPalette.Mid, c("border_strong"))
    p.setColor(QPalette.Dark, c("border_strong"))
    p.setColor(QPalette.Shadow, c("dark"))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, c("text3"))
    return p


def _qss(t: dict) -> str:
    return f"""
    QWidget {{ font-family: "{FONT_FAMILY}"; font-size: {BASE_PT}pt; color: {t['text']}; }}
    QMainWindow, QDialog {{ background: {t['bg']}; }}
    QToolTip {{ background: {t['tip']}; color: {t['tip_text']}; border: none; padding: 5px 8px;
                border-radius: 6px; }}

    /* ---- навигация: бирюзовая панель ---- */
    QListWidget#sidebar {{ background: {t['teal']}; border: none; padding: 16px 10px; outline: none; }}
    QListWidget#sidebar:focus {{ border: none; }}
    QListWidget#sidebar::item {{ height: 36px; padding-left: 10px; color: {t['teal_text']};
                                 margin-bottom: 2px; border-radius: 8px; }}
    QListWidget#sidebar::item:hover {{ background: rgba(255, 255, 255, 0.10); }}
    QListWidget#sidebar::item:selected {{ background: rgba(255, 255, 255, 0.20); color: {t['teal_text']};
                                          font-weight: 600; }}

    /* ---- типографика ---- */
    QLabel[role="title"] {{ font-size: 18pt; font-weight: 600; }}
    QLabel[role="subtitle"] {{ color: {t['text2']}; }}
    QLabel[role="section"] {{ font-size: 10.5pt; font-weight: 600; }}
    QLabel[role="secondary"] {{ color: {t['text2']}; }}
    QLabel[role="caption"] {{ color: {t['text2']}; font-size: 9pt; }}
    QLabel[role="danger"] {{ color: {t['danger']}; }}
    QLabel[role="warn"] {{ color: {t['warn']}; }}
    QLabel[role="accent"] {{ color: {t['accent']}; font-weight: 600; }}
    QLabel[role="metric"] {{ font-size: 20pt; font-weight: 600; }}
    QLabel[role="metric"][tone="danger"] {{ color: {t['danger']}; }}
    QLabel[role="empty"] {{ color: {t['text2']}; padding: 16px; }}

    /* ---- карточки ---- */
    QFrame#card {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: {RADIUS}px; }}
    QFrame#card QLabel, QFrame#paper QLabel {{ background: transparent; }}
    QFrame#paper {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: {RADIUS}px; }}
    QFrame#row {{ background: transparent; border: none; border-bottom: 1px solid {t['border']}; }}
    QFrame#rowLast {{ background: transparent; border: none; }}
    QFrame#rowClickable:hover, QFrame#row:hover {{ background: {t['surface2']}; border-radius: 6px; }}

    /* ---- кнопки ---- */
    QPushButton {{ background: {t['surface']}; border: 1px solid {t['border_strong']}; border-radius: 7px;
                   padding: 6px 14px; min-height: 18px; }}
    QPushButton:hover {{ background: {t['hover']}; }}
    QPushButton:pressed {{ background: {t['border']}; }}
    QPushButton:focus {{ border: 1px solid {t['teal']}; }}
    QPushButton:disabled {{ color: {t['text3']}; background: {t['surface2']}; border-color: {t['border']}; }}
    QPushButton[kind="primary"] {{ background: {t['teal']}; color: {t['teal_text']}; border: 1px solid {t['teal']};
                                   font-weight: 600; }}
    QPushButton[kind="primary"]:hover {{ background: {t['teal_hover']}; }}
    QPushButton[kind="primary"]:focus {{ border: 2px solid {t['teal_on_soft']}; }}
    QPushButton[kind="danger"] {{ color: {t['danger']}; }}
    QPushButton[kind="ghost"], QToolButton[kind="ghost"] {{ background: transparent;
        border: 1px solid transparent; border-radius: 7px; padding: 4px 8px; color: {t['link']}; }}
    QPushButton[kind="ghost"]:hover, QToolButton[kind="ghost"]:hover {{ background: {t['hover']}; }}
    QPushButton[kind="ghost"]:focus, QToolButton[kind="ghost"]:focus {{ border: 1px solid {t['teal']}; }}
    QToolButton::menu-indicator {{ image: none; width: 0; }}

    QPushButton[kind="chip"] {{ border-radius: 15px; padding: 5px 13px; min-height: 18px; }}
    QPushButton[kind="chip"]:checked {{ background: {t['teal_soft']}; color: {t['teal_on_soft']};
                                        border: 1px solid {t['teal']}; }}

    /* сегментный переключатель (День / Неделя / Месяц) */
    QPushButton[kind="seg"] {{ border-radius: 0; padding: 5px 14px; margin: 0; }}
    QPushButton[kind="seg"][pos="first"] {{ border-top-left-radius: 7px; border-bottom-left-radius: 7px; }}
    QPushButton[kind="seg"][pos="last"] {{ border-top-right-radius: 7px; border-bottom-right-radius: 7px; }}
    QPushButton[kind="seg"]:checked {{ background: {t['teal_soft']}; color: {t['teal_on_soft']};
                                       border-color: {t['teal']}; }}

    QPushButton[kind="day"] {{ border-radius: 8px; padding: 3px 0; min-width: 44px; min-height: 36px;
                               font-size: 9pt; }}
    QPushButton[kind="day"]:checked {{ background: {t['accent']}; color: {t['accent_text']};
                                       border: 1px solid {t['accent']}; font-weight: 600; }}
    QPushButton[kind="day"]:checked:hover {{ background: {t['accent_hover']}; }}
    QPushButton[kind="day"][today="true"] {{ border: 1px solid {t['text2']}; font-weight: 600; }}
    QPushButton[kind="day"][today="true"]:checked {{ border: 1px solid {t['accent']}; }}

    QPushButton[kind="check"] {{ min-width: 22px; max-width: 22px; min-height: 22px; max-height: 22px;
                                 padding: 0; border: 2px solid {t['border_strong']}; border-radius: 6px;
                                 background: {t['surface']}; color: transparent; font-weight: 700; }}
    QPushButton[kind="check"]:hover {{ border-color: {t['accent']}; }}
    QPushButton[kind="check"]:checked {{ background: {t['accent']}; border-color: {t['accent']};
                                         color: {t['accent_text']}; }}

    /* ---- поля ввода ---- */
    QLineEdit, QPlainTextEdit, QTextEdit, QDateEdit, QTimeEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
        background: {t['surface']}; border: 1px solid {t['border_strong']}; border-radius: 7px;
        padding: 5px 8px; selection-background-color: {t['selection']}; selection-color: {t['text']}; }}
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QDateEdit:focus, QTimeEdit:focus,
    QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border: 1px solid {t['teal']}; }}
    QComboBox::drop-down, QDateEdit::drop-down {{ width: 24px; border: none; }}
    QComboBox::down-arrow, QDateEdit::down-arrow {{ image: url({t['_arrow']}); width: 12px; height: 12px; }}
    QTimeEdit::up-button, QTimeEdit::down-button, QSpinBox::up-button, QSpinBox::down-button {{ width: 0; }}
    QLineEdit#noteTitle {{ font-size: 15pt; font-weight: 600; border: none; padding: 2px 0;
                           background: transparent; }}
    QPlainTextEdit#noteBody {{ border: none; padding: 0; background: transparent; font-size: 10.5pt; }}
    QComboBox QAbstractItemView {{ background: {t['surface']}; border: 1px solid {t['border_strong']};
        selection-background-color: {t['selection']}; selection-color: {t['text']}; outline: none; }}
    QCheckBox {{ spacing: 8px; }}
    QCheckBox::indicator {{ width: 16px; height: 16px; border: 2px solid {t['border_strong']};
                            border-radius: 5px; background: {t['surface']}; }}
    QCheckBox::indicator:hover {{ border-color: {t['accent']}; }}
    QCheckBox::indicator:checked {{ background: {t['accent']}; border-color: {t['accent']};
                                    image: url({t['_check']}); }}
    QCalendarWidget QAbstractItemView {{ selection-background-color: {t['teal']};
                                         selection-color: {t['teal_text']}; }}

    /* ---- списки и таблицы ---- */
    QTableWidget, QListWidget {{ background: {t['surface']}; alternate-background-color: {t['surface2']};
        border: 1px solid {t['border']}; border-radius: {RADIUS}px; gridline-color: {t['border']};
        selection-background-color: {t['selection']}; selection-color: {t['text']}; outline: none; }}
    QListWidget#noteList::item, QListWidget#folderList::item {{ padding: 8px 10px; border-radius: 6px;
                                                                margin: 1px 4px; }}
    QListWidget#noteList::item:selected, QListWidget#folderList::item:selected {{
        background: {t['selection']}; color: {t['text']}; }}
    QListWidget#noteList::item:hover, QListWidget#folderList::item:hover {{ background: {t['surface2']}; }}
    QHeaderView::section {{ background: {t['surface']}; color: {t['text2']}; border: none;
                            border-bottom: 1px solid {t['border']}; padding: 7px 8px; font-weight: 600; }}

    /* прогресс — синие «кирпичики» (фирменный элемент) */
    QProgressBar {{ background: {t['chunk_bg']}; border: none; border-radius: 4px; min-height: 10px;
                    max-height: 10px; padding: 0; }}
    QProgressBar::chunk {{ background: {t['accent']}; width: 8px; margin-right: 2px; border-radius: 2px; }}

    QScrollArea {{ background: transparent; border: none; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {t['border_strong']}; border-radius: 4px; min-height: 30px; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
    QScrollBar::handle:horizontal {{ background: {t['border_strong']}; border-radius: 4px; min-width: 30px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    QMenu {{ background: {t['surface']}; border: 1px solid {t['border_strong']}; border-radius: 8px; padding: 4px; }}
    QMenu::item {{ padding: 6px 22px; border-radius: 5px; }}
    QMenu::item:selected {{ background: {t['hover']}; color: {t['text']}; }}
    QMenu::separator {{ height: 1px; background: {t['border']}; margin: 4px 6px; }}
    QMessageBox QLabel {{ background: transparent; }}
    """


def _pick_font() -> str:
    available = set(QFontDatabase.families())
    return next((f for f in FONT_CANDIDATES if f in available), FONT_CANDIDATES[0])


def _arrow_file(color: str, name: str = "chevron-down") -> str:
    """Стрелка выпадающих списков — PNG во временной папке (QSS понимает только файлы)."""
    import tempfile
    from pathlib import Path
    from . import icons
    path = Path(tempfile.gettempdir()) / f"habittracker-{name}-{color.lstrip('#')}.png"
    if not path.exists():
        icons.pixmap(name, color, 12).save(str(path))
    return path.as_posix()


def apply_theme(app: QApplication) -> None:
    global FONT_FAMILY
    FONT_FAMILY = _pick_font()
    theme.dark = _system_is_dark()
    theme.t = dict(DARK if theme.dark else LIGHT)
    try:
        theme.t["_arrow"] = _arrow_file(theme.t["text2"])
        theme.t["_check"] = _arrow_file(theme.t["accent_text"], "check")
    except Exception:
        theme.t["_arrow"] = theme.t["_check"] = ""
    app.setStyle(QStyleFactory.create("Fusion"))
    app.setPalette(_palette(theme.t))
    app.setFont(QFont(FONT_FAMILY, BASE_PT))
    app.setStyleSheet(_qss(theme.t))
    theme.changed.emit()


class _DialogFixer(QObject):
    """При показе любого диалога: Enter нажимает главную (бирюзовую) кнопку, а не случайную,
    и её оформление точно применено (на Windows QDialogButtonBox оформляет кнопки раньше,
    чем им назначено свойство kind=primary)."""

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QDialog, QMessageBox, QPushButton
        if event.type() == QEvent.Show and isinstance(obj, QDialog) and not isinstance(obj, QMessageBox):
            buttons = obj.findChildren(QPushButton)
            primary = [b for b in buttons if b.property("kind") == "primary"]
            for b in buttons:
                b.setAutoDefault(False)
                b.setDefault(False)
            if primary:
                main = primary[-1]
                main.setDefault(True)
                repolish(main)
        return False


_fixer = _DialogFixer()


def install(app: QApplication) -> None:
    """Применяет тему и следит за переключением светлой/тёмной темы в системе."""
    from PySide6.QtCore import QLocale
    QLocale.setDefault(QLocale(QLocale.Russian, QLocale.Russia))   # даты и дни недели по-русски
    app.installEventFilter(_fixer)
    apply_theme(app)
    try:
        app.styleHints().colorSchemeChanged.connect(lambda *_: apply_theme(app))
    except Exception:
        pass


def repolish(widget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)
