"""Окна безопасности: вход, пароль, код восстановления, восстановление из копии."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from .. import backup, storage
from ..db import CorruptDatabase
from ..session import MIN_PASSWORD, Session
from . import widgets as w
from .theme import theme


class _Busy:
    """Песочные часы на время scrypt (≈0.1–0.3 с)."""

    def __enter__(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()

    def __exit__(self, *exc):
        QApplication.restoreOverrideCursor()


def _icon_label(size: int = 56) -> QLabel:
    from ..paths import resource_path
    lbl = QLabel()
    pm = QPixmap(str(resource_path("icon.png")))
    if not pm.isNull():
        lbl.setPixmap(pm.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    lbl.setAlignment(Qt.AlignTop)
    return lbl


def _buttons(dlg: QDialog, ok: str, cancel: str = "Отмена") -> QDialogButtonBox:
    box = QDialogButtonBox()
    okb = box.addButton(ok, QDialogButtonBox.AcceptRole)
    okb.setProperty("kind", "primary")
    okb.setDefault(True)
    if cancel:
        box.addButton(cancel, QDialogButtonBox.RejectRole)
    box.accepted.connect(dlg.accept)
    box.rejected.connect(dlg.reject)
    return box


def _password_field(placeholder: str) -> QLineEdit:
    f = QLineEdit()
    f.setEchoMode(QLineEdit.Password)
    f.setPlaceholderText(placeholder)
    f.setMinimumWidth(260)
    return f


def human_size(n: int) -> str:
    return f"{n / 1024:.0f} КБ" if n < 1024 * 1024 else f"{n / 1024 / 1024:.1f} МБ"


def human_when(dt: datetime) -> str:
    return f"{w.human_date(dt.date())}, {dt:%H:%M}"


# ---------------------------------------------------------------- вход

class LoginDialog(QDialog):
    """Вход по паролю или по коду восстановления. Результат — открытая Session."""

    def __init__(self, data_dir: Path, unlock_only: storage.Keyring | None = None):
        super().__init__()
        self.data_dir = Path(data_dir)
        self.unlock_only = unlock_only     # режим блокировки: только проверить пароль
        self.session: Session | None = None
        self.corrupt: Exception | None = None   # пароль верный, но файл повреждён
        self.keyring: storage.Keyring | None = None
        self.used_recovery = False
        self.recovery_mode = False
        self.setWindowTitle("Трекер привычек и задач — вход")
        self.setMinimumWidth(460)

        root = QHBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 16)
        root.setSpacing(16)
        root.addWidget(_icon_label())
        col = QVBoxLayout()
        col.setSpacing(8)
        self.title = w.label("", "section")
        self.hint = w.label("", "secondary", wrap=True)
        self.field = _password_field("")
        self.error = w.label("", "danger", wrap=True)
        self.error.hide()
        self.switch = w.button("", "ghost")
        self.switch.setFocusPolicy(Qt.TabFocus)
        self.switch.clicked.connect(self._toggle_mode)
        col.addWidget(self.title)
        col.addWidget(self.hint)
        col.addSpacing(4)
        col.addWidget(self.field)
        col.addWidget(self.error)
        col.addWidget(self.switch, 0, Qt.AlignLeft)
        col.addSpacing(6)
        col.addWidget(_buttons(self, "Войти", "Выход"))
        root.addLayout(col, 1)
        self.field.textChanged.connect(lambda: self.error.hide())
        self._apply_mode()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.activateWindow()
        self.field.setFocus()

    def _toggle_mode(self) -> None:
        self.recovery_mode = not self.recovery_mode
        self.field.clear()
        self.error.hide()
        self._apply_mode()

    def _apply_mode(self) -> None:
        if self.recovery_mode:
            self.title.setText("Вход по коду восстановления")
            self.hint.setText("Введите код, который программа показала при установке пароля. "
                              "После входа задайте новый пароль.")
            self.field.setEchoMode(QLineEdit.Normal)
            self.field.setPlaceholderText("XXXX-XXXX-XXXX-XXXX-XXXX-XXXX")
            self.switch.setText("← Войти по паролю")
        else:
            self.title.setText("Программа заблокирована" if self.unlock_only else
                               "Данные защищены паролем")
            self.hint.setText("Введите пароль, чтобы открыть привычки, задачи и заметки.")
            self.field.setEchoMode(QLineEdit.Password)
            self.field.setPlaceholderText("Пароль")
            self.switch.setText("Забыли пароль? Войти по коду восстановления")
        self.field.setFocus()

    def accept(self) -> None:
        secret = self.field.text()
        if not secret:
            self._fail("Введите пароль." if not self.recovery_mode else "Введите код восстановления.")
            return
        try:
            with _Busy():
                if self.unlock_only is not None:
                    if self.recovery_mode:
                        storage.Keyring.unlock(self.unlock_only.header, recovery=secret)
                    elif not self.unlock_only.check_password(secret):
                        raise storage.WrongPassword()
                else:
                    kw = {"recovery": secret} if self.recovery_mode else {"password": secret}
                    blob = (self.data_dir / storage.ENCRYPTED_NAME).read_bytes()
                    self.keyring = storage.Keyring.unlock(storage.read_header(blob), **kw)
                    self.session = Session.open_with_keyring(self.data_dir, self.keyring)
        except storage.WrongPassword:
            self._fail("Код не подходит. Проверьте, что ввели его полностью." if self.recovery_mode
                       else "Неверный пароль. Проверьте раскладку и Caps Lock.")
            return
        except (storage.CorruptFile, CorruptDatabase) as e:
            self.corrupt = e      # разберётся open_session: предложит восстановить из копии
        self.used_recovery = self.recovery_mode
        super().accept()

    def _fail(self, text: str) -> None:
        self.error.setText(text)
        self.error.show()
        self.field.selectAll()
        self.field.setFocus()


# ---------------------------------------------------------------- пароль

class PasswordDialog(QDialog):
    """Задать или сменить пароль (с подтверждением)."""

    def __init__(self, parent: QWidget | None, title: str, intro: str, ok: str,
                 current: storage.Keyring | None = None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(440)
        self.current = current
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 16)
        lay.setSpacing(8)
        lay.addWidget(w.label(intro, "secondary", wrap=True))
        lay.addSpacing(4)
        self.old = None
        if current is not None:
            lay.addWidget(w.label("Текущий пароль"))
            self.old = _password_field("")
            lay.addWidget(self.old)
        lay.addWidget(w.label("Новый пароль"))
        self.new = _password_field(f"Не короче {MIN_PASSWORD} символов")
        lay.addWidget(self.new)
        lay.addWidget(w.label("Повторите пароль"))
        self.repeat = _password_field("")
        lay.addWidget(self.repeat)
        self.error = w.label("", "danger", wrap=True)
        self.error.hide()
        lay.addWidget(self.error)
        lay.addSpacing(6)
        lay.addWidget(_buttons(self, ok))
        for f in (self.old, self.new, self.repeat):
            if f is not None:
                f.textChanged.connect(lambda: self.error.hide())
        (self.old or self.new).setFocus()

    def accept(self) -> None:
        msg = ""
        if self.old is not None:
            with _Busy():
                ok = self.current.check_password(self.old.text())
            if not ok:
                msg = "Текущий пароль введён неверно."
        if not msg and len(self.new.text()) < MIN_PASSWORD:
            msg = f"Пароль должен быть не короче {MIN_PASSWORD} символов."
        elif not msg and self.new.text() != self.repeat.text():
            msg = "Пароли не совпадают."
        if msg:
            self.error.setText(msg)
            self.error.show()
            return
        super().accept()

    def password(self) -> str:
        return self.new.text()


class ConfirmPasswordDialog(QDialog):
    """Подтвердить текущий пароль перед опасным действием."""

    def __init__(self, parent: QWidget | None, keyring: storage.Keyring, intro: str, ok: str):
        super().__init__(parent)
        self.keyring = keyring
        self.setWindowTitle("Подтвердите пароль")
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 16)
        lay.setSpacing(8)
        lay.addWidget(w.label(intro, "secondary", wrap=True))
        self.field = _password_field("Текущий пароль")
        lay.addWidget(self.field)
        self.error = w.label("", "danger")
        self.error.hide()
        lay.addWidget(self.error)
        lay.addWidget(_buttons(self, ok))
        self.field.textChanged.connect(lambda: self.error.hide())

    def accept(self) -> None:
        with _Busy():
            ok = self.keyring.check_password(self.field.text())
        if not ok:
            self.error.setText("Неверный пароль.")
            self.error.show()
            self.field.selectAll()
            return
        super().accept()


class RecoveryCodeDialog(QDialog):
    """Показать код восстановления один раз; закрыть можно, только подтвердив, что сохранён."""

    def __init__(self, parent: QWidget | None, code: str):
        super().__init__(parent)
        self.code = code
        self.setWindowTitle("Код восстановления")
        self.setMinimumWidth(500)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 16)
        lay.setSpacing(10)
        lay.addWidget(w.label("Сохраните этот код", "section"))
        lay.addWidget(w.label(
            "Если вы забудете пароль, войти можно будет только с этим кодом. Без пароля и без "
            "кода данные не сможет открыть никто — даже разработчик. Запишите код на бумаге или "
            "сохраните в надёжном месте (не в той же папке, что и данные).", "secondary", wrap=True))
        box = QFrame()
        box.setObjectName("paper")
        bl = QVBoxLayout(box)
        bl.setContentsMargins(14, 12, 14, 12)
        lbl = QLabel(code)
        f = QFont("Consolas")
        f.setStyleHint(QFont.Monospace)
        f.setPointSize(15)
        f.setBold(True)
        lbl.setFont(f)
        lbl.setStyleSheet("font-family: Consolas, 'Courier New', monospace; font-size: 15pt;")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        bl.addWidget(lbl)
        lay.addWidget(box)
        row = QHBoxLayout()
        copy = w.button("Копировать")
        copy.clicked.connect(lambda: (self._copy(), copy.setText("Скопировано ✓")))
        save = w.button("Сохранить в файл…")
        save.clicked.connect(self._save)
        row.addWidget(copy)
        row.addWidget(save)
        row.addStretch()
        lay.addLayout(row)
        self.confirm = QCheckBox("Я сохранил(а) код в надёжном месте")
        lay.addWidget(self.confirm)
        self.box = _buttons(self, "Готово", "")
        self.ok = self.box.buttons()[0]
        self.ok.setEnabled(False)
        self.confirm.toggled.connect(self.ok.setEnabled)
        lay.addWidget(self.box)

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self.code)

    def _save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить код восстановления",
                                              str(Path.home() / "Код восстановления трекера.txt"),
                                              "Текст (*.txt)")
        if path:
            Path(path).write_text(
                "Код восстановления «Трекера привычек и задач»\n"
                f"Создан: {datetime.now():%d.%m.%Y %H:%M}\n\n{self.code}\n\n"
                "Храните отдельно от компьютера с данными.\n", encoding="utf-8")

    def reject(self) -> None:     # Esc не закрывает, пока код не подтверждён
        if self.confirm.isChecked():
            super().reject()


class SecretDialog(QDialog):
    """Пароль или код для зашифрованной копии, сделанной при другом пароле."""

    def __init__(self, parent: QWidget | None, path: Path):
        super().__init__(parent)
        self.setWindowTitle("Копия защищена паролем")
        self.setMinimumWidth(440)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 16)
        lay.setSpacing(8)
        lay.addWidget(w.label("Эта копия зашифрована паролем, который действовал при её создании. "
                              "Введите тот пароль или код восстановления того времени.",
                              "secondary", wrap=True))
        self.field = _password_field("Пароль или код восстановления")
        lay.addWidget(self.field)
        self.error = w.label("", "danger")
        self.error.hide()
        lay.addWidget(self.error)
        lay.addWidget(_buttons(self, "Открыть"))
        self.path = path
        self.blob: bytes | None = None

    def accept(self) -> None:
        secret = self.field.text()
        try:
            with _Busy():
                try:
                    self.blob = backup.read_backup(self.path, password=secret)
                except storage.WrongPassword:
                    self.blob = backup.read_backup(self.path, recovery=secret)
        except storage.WrongPassword:
            self.error.setText("Не подходит ни как пароль, ни как код.")
            self.error.show()
            return
        except storage.CorruptFile as e:
            self.error.setText(str(e))
            self.error.show()
            return
        super().accept()


def load_backup(parent: QWidget | None, path: Path, current: storage.Keyring | None) -> bytes | None:
    """Прочитать копию, при необходимости спросив пароль. None — отмена или ошибка (уже показана)."""
    try:
        with _Busy():
            return backup.read_backup(path, current=current)
    except backup.NeedsSecret:
        dlg = SecretDialog(parent, path)
        return dlg.blob if dlg.exec() == QDialog.Accepted else None
    except (storage.CorruptFile, OSError) as e:
        QMessageBox.warning(parent, "Копия не подходит", f"Не удалось прочитать копию:\n{e}")
        return None


# ---------------------------------------------------------------- выбор копии

class RestoreDialog(QDialog):
    def __init__(self, parent: QWidget | None, folders: list[Path], title: str, intro: str,
                 ok_text: str = "Восстановить", cancel_text: str = "Отмена"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(540, 400)
        self.chosen: Path | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 16)
        lay.setSpacing(8)
        lay.addWidget(w.label(intro, "secondary", wrap=True))
        self.list = QListWidget()
        items = []
        for folder in folders:
            items += backup.list_backups(folder)
        items.sort(key=lambda b: b.when, reverse=True)
        for b in items:
            where = "доп. папка" if len(folders) > 1 and b.path.parent == Path(folders[1]) else ""
            parts = [human_when(b.when), b.kind_name]
            if b.encrypted:
                parts.append("зашифрована")
            parts.append(human_size(b.size))
            if where:
                parts.append(where)
            it = QListWidgetItem("   ·   ".join(parts))
            it.setData(Qt.UserRole, str(b.path))
            it.setToolTip(str(b.path))
            self.list.addItem(it)
        if not items:
            it = QListWidgetItem("Копий пока нет")
            it.setFlags(Qt.NoItemFlags)
            self.list.addItem(it)
        else:
            self.list.setCurrentRow(0)
        self.list.itemDoubleClicked.connect(lambda *_: self.accept())
        lay.addWidget(self.list, 1)
        row = QHBoxLayout()
        other = w.button("Другой файл…")
        other.clicked.connect(self._pick)
        row.addWidget(other)
        row.addStretch()
        box = _buttons(self, ok_text, cancel_text)
        row.addWidget(box)
        lay.addLayout(row)

    def _pick(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Выберите копию", str(Path.home()),
                                              "Копии трекера (*.htenc *.sqlite3);;Все файлы (*)")
        if path:
            self.chosen = Path(path)
            super().accept()

    def accept(self) -> None:
        it = self.list.currentItem()
        if it is None or not it.data(Qt.UserRole):
            return
        self.chosen = Path(it.data(Qt.UserRole))
        super().accept()


# ---------------------------------------------------------------- запуск

def _repair(data_dir: Path, reason: str, keyring: storage.Keyring | None = None) -> bool:
    """Файл данных повреждён: предложить восстановление из копии. True — можно пробовать снова."""
    folders = [backup.backup_dir(data_dir)]
    extra = backup.Settings(data_dir).get("extra_backup_dir")
    if extra:
        folders.append(Path(extra))
    dlg = RestoreDialog(None, folders, "Файл данных повреждён",
                        "Не удалось прочитать файл с данными (" + reason + "). Ничего страшного: "
                        "выберите резервную копию — обычно подходит самая свежая. Повреждённый "
                        "файл не удаляется, а сохраняется рядом с пометкой «corrupt».",
                        "Восстановить", "Выход")
    if dlg.exec() != QDialog.Accepted or dlg.chosen is None:
        return False
    blob = load_backup(None, dlg.chosen, keyring)
    if blob is None:
        return False
    path, encrypted = storage.current_file(data_dir)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    if path is not None:
        path.rename(path.with_name(f"{path.name}.corrupt-{stamp}"))
    if keyring is not None:   # пароль уже проверен — данные остаются зашифрованными тем же ключом
        storage.EncryptedStore(Path(data_dir) / storage.ENCRYPTED_NAME, keyring).save(blob)
        note = "\n\nВойдите тем же паролем."
    else:
        storage.atomic_write(Path(data_dir) / storage.PLAIN_NAME, blob)
        note = ("\n\nПароль был снят — задайте его снова в разделе «Настройки»."
                if encrypted else "")
    QMessageBox.information(None, "Данные восстановлены", "Данные восстановлены из копии." + note)
    return True


def open_session(data_dir: Path, on_save_error=None) -> Session | None:
    """Открыть данные: вход по паролю, проверка целостности, помощь при повреждении."""
    for _ in range(3):
        _, encrypted = Session.locate(data_dir)
        keyring = None
        try:
            if encrypted:
                dlg = LoginDialog(data_dir)
                if dlg.exec() != QDialog.Accepted:
                    return None
                keyring = dlg.keyring
                if dlg.corrupt is not None:
                    raise dlg.corrupt
                session = dlg.session
                if dlg.used_recovery:
                    pw = PasswordDialog(None, "Новый пароль",
                                        "Вы вошли по коду восстановления. Задайте новый пароль.",
                                        "Сохранить пароль")
                    if pw.exec() == QDialog.Accepted:
                        session.change_password(pw.password())
            else:
                session = Session.open_plain(data_dir)
            session.db.on_save_error = on_save_error
            if not session.db.quick_check():
                raise CorruptDatabase("проверка целостности не пройдена")
            return session
        except (storage.CorruptFile, CorruptDatabase) as e:
            if not _repair(data_dir, str(e), keyring):
                return None
    return None
