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
    "bg": "#FBFBFA", "surface": "#FFFFFF", "surface2": "#F7F7F5", "hover": "#F1F1EF",
    "text": "#2F2E2B", "text2": "#55534E", "text3": "#6E6C67",
    "border": "#EAE9E6", "border_strong": "#D9D7D2",
    "sidebar_neutral": "#F7F7F5", "sidebar_neutral_text": "#3B3A36",
    "sidebar_neutral_hover": "#ECECEA", "sidebar_neutral_sel": "#E6E5E2",
    "light": "#FFFFFF", "shadow": "#CFCCC3", "dark": "#9C978C",
    "accent": "#4338CA", "accent_hover": "#3730A3", "accent_text": "#FFFFFF",
    "accent_soft": "#E8E7FB", "accent_on_soft": "#2E2795",
    "teal": "#0F6E6A", "teal_hover": "#0C5B57", "teal_text": "#FFFFFF",
    "teal_soft": "#E1F0EE", "teal_on_soft": "#0B4F4C", "link": "#0F6E6A",
    "danger": "#B42318", "danger_soft": "#FDECEA", "danger_on": "#FFFFFF",
    "warn": "#8A5A00", "warn_soft": "#FFF3D6",
    "empty": "#E6E4DE", "selection": "#DDEFEC", "tip": "#1A1C1E", "tip_text": "#FFFFFF",
    "chunk_bg": "#ECEAE4", "today_bg": "#E7F3F2", "now": "#D93025",
}

DARK = {
    "bg": "#191919", "surface": "#202020", "surface2": "#252525", "hover": "#2C2C2C",
    "text": "#E9E9E7", "text2": "#BDBCB8", "text3": "#A09F9B",
    "border": "#2F2F2F", "border_strong": "#444444",
    "sidebar_neutral": "#202020", "sidebar_neutral_text": "#D6D5D1",
    "sidebar_neutral_hover": "#2C2C2C", "sidebar_neutral_sel": "#333333",
    "light": "#41464D", "shadow": "#0E0F10", "dark": "#0A0A0B",
    "accent": "#8B85F7", "accent_hover": "#A09BF9", "accent_text": "#14123A",
    "accent_soft": "#2B2950", "accent_on_soft": "#CFCCFF",
    "teal": "#0E4F4C", "teal_hover": "#12605C", "teal_text": "#FFFFFF",
    "teal_soft": "#173634", "teal_on_soft": "#8EDBD4", "link": "#5FD1C9",
    "danger": "#FF8A80", "danger_soft": "#3D2220", "danger_on": "#3A0B07",
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
        # Оформление пользователя (settings.json → "appearance"):
        # primary — основной цвет (панель, кнопки, ссылки), accent — цвет «выполнено/прогресс»,
        # sidebar — {"mode": "neutral" (по умолчанию) | "primary" | "color" | "image", "color": "#…", "image": путь, "dim": 0..0.8},
        # mode — "system" | "light" | "dark".
        self.custom: dict = {}

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


# ---------------------------------------------------------------- свои цвета

PRIMARY_PRESETS = [("#0F6E6A", "Бирюзовый"), ("#1D4ED8", "Синий"), ("#4338CA", "Индиго"),
                   ("#7E22CE", "Фиолетовый"), ("#BE185D", "Малиновый"), ("#B91C1C", "Красный"),
                   ("#B45309", "Янтарный"), ("#15803D", "Зелёный"), ("#374151", "Графит")]
ACCENT_PRESETS = [("#4338CA", "Индиго"), ("#1D4ED8", "Синий"), ("#0F766E", "Бирюзовый"),
                  ("#15803D", "Зелёный"), ("#B45309", "Янтарный"), ("#BE185D", "Малиновый"),
                  ("#7E22CE", "Фиолетовый")]


def _lum(c: QColor) -> float:
    def ch(v: float) -> float:
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(c.redF()) + 0.7152 * ch(c.greenF()) + 0.0722 * ch(c.blueF())


def contrast(a: str | QColor, b: str | QColor) -> float:
    la, lb = _lum(QColor(a)), _lum(QColor(b))
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def mix(a: str, b: str, t: float) -> str:
    """Смесь цветов: t=0 → a, t=1 → b."""
    ca, cb = QColor(a), QColor(b)
    return QColor(round(ca.red() + (cb.red() - ca.red()) * t), round(ca.green() + (cb.green() - ca.green()) * t),
                  round(ca.blue() + (cb.blue() - ca.blue()) * t)).name().upper()


def _shift_light(color: str, against: str, target: float, lighter: bool) -> str:
    """Темнее/светлее цвет, пока контраст с against не станет ≥ target (оттенок сохраняется)."""
    c = QColor(color)
    h, s, l, _ = c.getHslF()
    h = max(h, 0.0)
    for _ in range(60):
        if contrast(c, against) >= target:
            break
        l = min(1.0, l + 0.02) if lighter else max(0.0, l - 0.02)
        c = QColor.fromHslF(h, s, l)
    return c.name().upper()


def derive(base: dict, dark: bool, custom: dict) -> dict:
    """Палитра с учётом своих цветов; контраст текста не опускается ниже 4.5:1."""
    t = dict(base)
    white, ink = "#FFFFFF", "#1A1C1E"
    primary = custom.get("primary")
    if primary:
        # фон кнопок и панели с белым текстом
        fill = _shift_light(primary, white, 4.8, lighter=False)
        if dark:
            fill = mix(fill, "#000000", 0.25)
        t.update(teal=fill, teal_hover=mix(fill, "#000000", 0.15), teal_text=white,
                 teal_soft=mix(t["surface"], fill, 0.16 if not dark else 0.35),
                 selection=mix(t["surface"], fill, 0.14 if not dark else 0.32),
                 today_bg=mix(t["bg"], fill, 0.10 if not dark else 0.22))
        t["teal_on_soft"] = _shift_light(primary, t["teal_soft"], 5.0, lighter=dark)
        t["link"] = _shift_light(primary, t["surface"], 4.8, lighter=dark)
    accent = custom.get("accent")
    if accent:
        if dark:
            a = _shift_light(accent, t["surface"], 5.0, lighter=True)
            t.update(accent=a, accent_hover=mix(a, white, 0.15), accent_text="#121212")
            if contrast(a, "#121212") < 4.5:
                t["accent_text"] = white
        else:
            a = _shift_light(accent, white, 5.0, lighter=False)
            t.update(accent=a, accent_hover=mix(a, "#000000", 0.15), accent_text=white)
        t["accent_soft"] = mix(t["surface"], t["accent"], 0.16 if not dark else 0.3)
        t["accent_on_soft"] = _shift_light(t["accent"], t["accent_soft"], 5.0, lighter=dark)
    # боковая панель
    sb = custom.get("sidebar") or {}
    mode = sb.get("mode", "neutral")
    if mode == "neutral":
        # как в Notion: спокойная светлая (в тёмной теме — тёмная) панель, цвет — только у акцентов
        t.update(sidebar_bg=t["sidebar_neutral"], sidebar_text=t["sidebar_neutral_text"],
                 sidebar_hover=t["sidebar_neutral_hover"], sidebar_sel=t["sidebar_neutral_sel"],
                 sidebar_image="", sidebar_dim=0.0, sidebar_icon=t["text3"])
        return t
    t["sidebar_image"] = ""
    t["sidebar_dim"] = 0.0
    if mode == "color" and sb.get("color"):
        bg = sb["color"]
    else:
        bg = t["teal"]
    if mode == "image" and sb.get("image"):
        t["sidebar_image"] = sb["image"]
        t["sidebar_dim"] = float(sb.get("dim", 0.4))
        bg = t["teal"]
    t["sidebar_bg"] = bg
    light_text = mode == "image" or contrast(white, bg) >= 4.5
    t["sidebar_text"] = white if light_text else ink
    t["sidebar_hover"] = "rgba(255, 255, 255, 0.12)" if light_text else "rgba(0, 0, 0, 0.07)"
    t["sidebar_sel"] = "rgba(255, 255, 255, 0.22)" if light_text else "rgba(0, 0, 0, 0.12)"
    t["sidebar_icon"] = t["sidebar_text"]
    return t


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
    QWidget {{ font-family: "{FONT_FAMILY}"; font-size: 10pt; color: {t['text']}; }}
    QMainWindow, QDialog {{ background: {t['bg']}; }}
    QToolTip {{ background: {t['tip']}; color: {t['tip_text']}; border: none; padding: 5px 8px;
                border-radius: 6px; }}

    /* ---- навигация: боковая панель (сворачивается до иконок, ширину можно тянуть) ---- */
    QListWidget#sidebar {{ background: transparent; border: none; padding: 8px 8px; outline: none; }}
    QListWidget#sidebar:focus {{ border: none; }}
    QListWidget#sidebar::item {{ height: 32px; padding-left: 8px; color: {t['sidebar_text']};
                                 margin-bottom: 1px; border-radius: 6px; }}
    QListWidget#sidebar[collapsed="true"]::item {{ padding-left: 13px; }}
    QLabel#appTitle {{ font-weight: 600; font-size: 10.5pt; }}
    QToolButton#collapseBtn {{ border: none; border-radius: 6px; padding: 4px; background: transparent; }}
    QToolButton#collapseBtn:hover {{ background: {t['sidebar_hover']}; }}
    QSplitter::handle {{ background: {t['border']}; }}
    QSplitter::handle:hover {{ background: {t['teal']}; }}
    QSplitter#mainSplit::handle {{ background: {t['border']}; }}
    QSplitter#pageSplit::handle {{ background: transparent; }}
    QSplitter#pageSplit::handle:hover {{ background: {t['teal_soft']}; border-radius: 4px; }}

    /* ---- доски (канбан) ---- */
    QFrame#kanbanColumn {{ background: {t['surface2']}; border: 1px solid {t['border']}; border-radius: 10px; }}
    QListWidget#kanbanList {{ background: transparent; border: none; }}
    QListWidget#kanbanList::item {{ background: transparent; border: none; padding: 0; margin: 0; }}
    QListWidget#kanbanList::item:selected {{ background: transparent; }}
    QFrame#kanbanCard {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 8px; }}
    QFrame#kanbanCard[sel="true"] {{ border: 1px solid {t['teal']}; background: {t['surface']}; }}
    QFrame#kanbanCard:hover {{ border-color: {t['border_strong']}; }}
    QLineEdit#kanbanAdd {{ background: transparent; border: 1px dashed {t['border_strong']}; color: {t['text2']}; }}
    QLineEdit#kanbanAdd:focus {{ background: {t['surface']}; border: 1px solid {t['teal']}; color: {t['text']}; }}
    QScrollArea#kanbanArea, QWidget#kanbanHolder {{ background: transparent; }}
    QListWidget#sidebar::item:hover {{ background: {t['sidebar_hover']}; }}
    QListWidget#sidebar::item:selected {{ background: {t['sidebar_sel']}; color: {t['sidebar_text']};
                                          font-weight: 600; }}

    /* ---- типографика ---- */
    QLabel[role="title"] {{ font-size: 20pt; font-weight: 700; }}
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
    QListWidget#subtasks::item {{ min-height: 26px; padding: 2px 4px; border-radius: 6px; }}
    QListWidget#subtasks::item:selected {{ background: {t['selection']}; color: {t['text']}; }}
    QListWidget#subtasks::indicator {{ width: 16px; height: 16px; border: 2px solid {t['border_strong']};
                                       border-radius: 5px; background: {t['surface']}; }}
    QListWidget#subtasks::indicator:checked {{ background: {t['accent']}; border-color: {t['accent']};
                                               image: url({t['_check']}); }}
    QHeaderView::section {{ background: {t['surface']}; color: {t['text2']}; border: none;
                            border-bottom: 1px solid {t['border']}; padding: 7px 8px; font-weight: 600; }}

    /* прогресс — синие «кирпичики» (фирменный элемент) */
    QProgressBar {{ background: {t['chunk_bg']}; border: none; border-radius: 4px; min-height: 10px;
                    max-height: 10px; padding: 0; }}
    QProgressBar::chunk {{ background: {t['accent']}; width: 8px; margin-right: 2px; border-radius: 2px; }}

    QScrollArea {{ background: transparent; border: none; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QScrollArea#chipStrip, QWidget#chipStripInner {{ background: transparent; }}
    QScrollArea#chipStrip QScrollBar:horizontal {{ height: 6px; margin: 0; }}
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
    QMessageBox {{ background: {t['surface']}; }}
    QMessageBox QLabel {{ background: transparent; }}
    QMessageBox QLabel#qt_msgbox_label {{ font-size: 11pt; font-weight: 600; min-width: 300px; padding: 6px 4px 2px 4px; }}
    QMessageBox QLabel#qt_msgbox_informativelabel {{ color: {t['text2']}; padding: 0 4px 8px 4px; }}
    QPushButton[kind="dangerSolid"] {{ background: {t['danger']}; color: {t['danger_on']}; border: 1px solid {t['danger']};
                                       font-weight: 600; }}
    QPushButton[kind="dangerSolid"]:hover {{ background: {t['danger']}; border-color: {t['text']}; }}
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


# шрифты на выбор в настройках (показываются только установленные в системе)
FONT_CHOICES = ["Segoe UI", "Inter", "Calibri", "Arial", "Verdana", "Tahoma", "Trebuchet MS", "Bahnschrift",
                "Georgia", "Cambria", "Times New Roman", "Consolas", "JetBrains Mono", "Roboto", "Open Sans",
                "PT Sans", "PT Serif", "Montserrat", "DejaVu Sans"]
SIZE_CHOICES = [(9, "Мелкий"), (10, "Обычный"), (11, "Крупнее"), (12, "Крупный"), (13, "Очень крупный")]


def available_fonts() -> list[str]:
    have = set(QFontDatabase.families())
    return [f for f in FONT_CHOICES if f in have]


def _scale_pt(qss: str, ratio: float) -> str:
    """Все размеры в pt — пропорционально выбранному размеру текста."""
    import re
    if abs(ratio - 1) < 1e-6:
        return qss
    return re.sub(r"(\d+(?:\.\d+)?)pt", lambda m: f"{float(m.group(1)) * ratio:.1f}pt", qss)


def apply_theme(app: QApplication) -> None:
    global FONT_FAMILY, BASE_PT
    chosen = theme.custom.get("font")
    FONT_FAMILY = chosen if chosen and chosen in set(QFontDatabase.families()) else _pick_font()
    BASE_PT = int(theme.custom.get("font_size") or 10)
    mode = theme.custom.get("mode", "system")
    theme.dark = _system_is_dark() if mode == "system" else mode == "dark"
    theme.t = derive(DARK if theme.dark else LIGHT, theme.dark, theme.custom)
    try:
        theme.t["_arrow"] = _arrow_file(theme.t["text2"])
        theme.t["_check"] = _arrow_file(theme.t["accent_text"], "check")
    except Exception:
        theme.t["_arrow"] = theme.t["_check"] = ""
    app.setStyle(QStyleFactory.create("Fusion"))
    app.setPalette(_palette(theme.t))
    app.setFont(QFont(FONT_FAMILY, BASE_PT))
    app.setStyleSheet(_scale_pt(_qss(theme.t), BASE_PT / 10))
    theme.changed.emit()


class _DialogFixer(QObject):
    """При показе любого диалога: Enter нажимает главную (бирюзовую) кнопку, а не случайную,
    и её оформление точно применено (на Windows QDialogButtonBox оформляет кнопки раньше,
    чем им назначено свойство kind=primary)."""

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QDialog, QMessageBox, QPushButton
        if event.type() == QEvent.Show and isinstance(obj, QMessageBox) and not obj.property("_styled"):
            # окна-вопросы в стиле программы: без системной синей иконки, понятные кнопки,
            # «Удалить» — красная, «Отмена» — спокойная
            obj.setProperty("_styled", True)
            if obj.icon() in (QMessageBox.Question, QMessageBox.Warning, QMessageBox.Information):
                obj.setIcon(QMessageBox.NoIcon)
            names = {QMessageBox.Yes: "Да", QMessageBox.No: "Отмена", QMessageBox.Ok: "Понятно",
                     QMessageBox.Cancel: "Отмена"}
            for b in obj.buttons():
                std = obj.standardButton(b)
                if std in names and b.text().replace("&", "") in ("Да", "Нет", "OK", "Yes", "No", "Cancel", "Отмена"):
                    b.setText(names[std])
                role = obj.buttonRole(b)
                title = obj.windowTitle().lower()
                destructive = role == QMessageBox.DestructiveRole or (
                    std == QMessageBox.Yes and any(x in title for x in ("удал", "отключ", "заменить")))
                if destructive:
                    b.setProperty("kind", "dangerSolid")
                    if std == QMessageBox.Yes and "удал" in title:
                        b.setText("Удалить")
                elif role in (QMessageBox.AcceptRole, QMessageBox.YesRole) or std in (QMessageBox.Ok, QMessageBox.Yes):
                    b.setProperty("kind", "primary")
                b.setMinimumWidth(96)
                b.setCursor(Qt.PointingHandCursor)
                repolish(b)
            safe = obj.button(QMessageBox.No) or obj.button(QMessageBox.Cancel)
            if safe is not None and any(b.property("kind") == "dangerSolid" for b in obj.buttons()):
                obj.setDefaultButton(safe)      # Enter не удаляет случайно
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


def set_appearance(custom: dict | None) -> None:
    """Сменить оформление на лету (из настроек)."""
    theme.custom = dict(custom or {})
    app = QApplication.instance()
    if app is not None:
        apply_theme(app)


def install(app: QApplication, custom: dict | None = None) -> None:
    """Применяет тему и следит за переключением светлой/тёмной темы в системе."""
    theme.custom = dict(custom or {})
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
