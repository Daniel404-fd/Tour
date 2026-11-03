"""Настройки: пароль, резервные копии, где лежат данные."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QFileDialog, QHBoxLayout, QMessageBox, QVBoxLayout

from .. import backup, storage
from ..session import Session
from . import widgets as w
from .security import (
    ConfirmPasswordDialog, PasswordDialog, RecoveryCodeDialog, RestoreDialog, _Busy, human_when, load_backup,
)

EXTRA_SUBFOLDER = "HabitTracker backups"


def cloud_candidates() -> list[tuple[str, Path]]:
    """Папки облаков, которые уже есть на компьютере: туда копии уезжают автоматически."""
    home = Path.home()
    found = []
    for name, label in (("YandexDisk", "Яндекс Диск"), ("OneDrive", "OneDrive"),
                        ("Google Drive", "Google Диск"), ("Dropbox", "Dropbox")):
        p = home / name
        if p.is_dir():
            found.append((label, p / EXTRA_SUBFOLDER))
    return found


def _row(*widgets_) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(8)
    for x in widgets_:
        row.addWidget(x)
    row.addStretch()
    return row


class SettingsPage(w.Page):
    def __init__(self, db, navigate, session: Session, window):
        super().__init__("Настройки", "Пароль и сохранность данных")
        self.db, self.session, self.window = db, session, window
        self.box = QVBoxLayout()
        self.box.setSpacing(12)
        self.sync_status = None
        window.sync.statusChanged.connect(self._on_sync_status)
        self.content.addLayout(self.box)
        self.content.addStretch()

    # ---------------------------------------------------------------- отрисовка

    def refresh(self) -> None:
        with self.keep_scroll():
            w.clear_layout(self.box)
            self.box.addWidget(self._sync_card())
            self.box.addWidget(self._password_card())
            self.box.addWidget(self._backup_card())
            self.box.addWidget(self._storage_card())

    # ---------------------------------------------------------------- синхронизация

    def _sync_card(self) -> w.Card:
        card = w.Card("Синхронизация с телефоном")
        s = self.session.sync_settings
        if self.session.sync_enabled:
            card.body.addWidget(w.label(
                f"Данные синхронизируются через Яндекс Диск ({s.get('login')}) — с приложением на "
                "телефоне и другими компьютерами. Автоматически: при запуске, через 20 секунд после "
                "изменений, каждые 5 минут и при закрытии программы.", "secondary", wrap=True))
            ctl = self.window.sync
            self.sync_status = w.label(ctl.last_text or self._last_sync_text(),
                                       None if ctl.last_ok else "danger", wrap=True)
            card.body.addWidget(self.sync_status)
            now = w.button("Синхронизировать сейчас", "primary")
            now.clicked.connect(ctl.run)
            change = w.button("Изменить…")
            change.clicked.connect(self.setup_sync)
            off = w.button("Отключить", "ghost")
            off.clicked.connect(self.disable_sync)
            card.body.addLayout(_row(now, change, off))
            card.body.addWidget(w.label(
                f"Файлы синхронизации лежат на Диске в папке «HabitTracker-sync». Это устройство: "
                f"«{s.get('device_name') or 'ПК'}».", "caption", wrap=True))
        else:
            card.body.addWidget(w.label(
                "Подключите Яндекс Диск, чтобы привычки, задачи, календарь, цели и заметки были "
                "одинаковыми на компьютере и в приложении для Android. Изменения с разных "
                "устройств объединяются по записям — ничего не затирается.", "secondary", wrap=True))
            on = w.button("Подключить Яндекс Диск…", "primary")
            on.clicked.connect(self.setup_sync)
            card.body.addLayout(_row(on))
        return card

    def _last_sync_text(self) -> str:
        last = self.session.settings.get("last_sync")
        if not last:
            return "Ещё не синхронизировалось."
        from datetime import datetime, timezone
        try:
            dt = datetime.strptime(last, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc).astimezone()
            return f"Последняя синхронизация: {human_when(dt.replace(tzinfo=None))}"
        except ValueError:
            return ""

    def _on_sync_status(self, text: str, ok: bool) -> None:
        try:
            if self.sync_status is not None:
                self.sync_status.setText(text)
                self.sync_status.setProperty("role", None if ok else "danger")
                from .theme import repolish
                repolish(self.sync_status)
        except RuntimeError:     # карточку уже перестроили
            self.sync_status = None

    def setup_sync(self) -> None:
        dlg = SyncDialog(self, self.session.sync_settings)
        if dlg.exec() != QDialog.Accepted:
            return
        login, password, name = dlg.values()
        self.session.set_sync(login, password, name)
        self.refresh()
        self.window.sync.run()

    def disable_sync(self) -> None:
        box = QMessageBox(QMessageBox.Question, "Отключить синхронизацию",
                          "Отключить синхронизацию на этом компьютере?", parent=self)
        box.setInformativeText("Данные на компьютере и на Яндекс Диске останутся. Включить снова "
                               "можно в любой момент.")
        yes = box.addButton("Отключить", QMessageBox.AcceptRole)
        box.addButton("Отмена", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is yes:
            self.session.disable_sync()
            self.refresh()

    def _password_card(self) -> w.Card:
        card = w.Card("Пароль для входа")
        if self.session.encrypted:
            card.body.addWidget(w.label(
                "Вход по паролю включён. Файл данных и резервные копии зашифрованы (AES-256): "
                "без пароля или кода восстановления их не прочитать.", "secondary", wrap=True))
            change = w.button("Сменить пароль…")
            change.clicked.connect(self.change_password)
            code = w.button("Новый код восстановления…")
            code.clicked.connect(self.new_code)
            lock = w.button("Заблокировать сейчас", None, "lock", "Заблокировать (Ctrl+L)")
            lock.clicked.connect(self.window.lock)
            off = w.button("Отключить пароль…", "danger")
            off.clicked.connect(self.disable_password)
            card.body.addLayout(_row(change, code, lock))
            card.body.addLayout(_row(off))
        else:
            card.body.addWidget(w.label(
                "Пароль не задан: программу и файл данных может открыть любой, у кого есть доступ "
                "к этому компьютеру. С паролем данные и копии будут зашифрованы.",
                "secondary", wrap=True))
            on = w.button("Установить пароль…", "primary", "lock")
            on.clicked.connect(self.enable_password)
            card.body.addLayout(_row(on))
        return card

    def _backup_card(self) -> w.Card:
        card = w.Card("Резервные копии")
        folder = backup.backup_dir(self.session.data_dir)
        items = backup.list_backups(folder)
        last = items[0] if items else None
        text = ("Каждый день при первом запуске программа сохраняет копию данных; хранятся "
                f"последние {backup.KEEP_AUTO}. Перед восстановлением и сменой пароля "
                "делается ещё и страховочная копия.")
        card.body.addWidget(w.label(text, "secondary", wrap=True))
        card.body.addWidget(w.label(
            f"Последняя копия: {human_when(last.when)} · всего {len(items)}" if last
            else "Копий пока нет."))
        now = w.button("Сделать копию сейчас")
        now.clicked.connect(self.backup_now)
        restore = w.button("Восстановить из копии…")
        restore.clicked.connect(self.restore)
        export = w.button("Сохранить копию в файл…")
        export.clicked.connect(self.export)
        card.body.addLayout(_row(now, restore, export))

        card.body.addSpacing(6)
        card.body.addWidget(w.label("Копия вне компьютера", "section"))
        extra = self.session.settings.get("extra_backup_dir")
        if extra:
            card.body.addWidget(w.label(
                f"Копии также сохраняются в папку:\n{extra}", None, wrap=True))
            if not Path(extra).is_dir():
                card.body.addWidget(w.label("Папка сейчас недоступна — копии туда не попадут, "
                                            "пока она не появится снова.", "warn", wrap=True))
            change = w.button("Выбрать другую папку…")
            change.clicked.connect(self.choose_extra)
            stop = w.button("Не копировать туда", "ghost")
            stop.clicked.connect(lambda: self._set_extra(None))
            card.body.addLayout(_row(change, stop))
        else:
            card.body.addWidget(w.label(
                "Сейчас все копии лежат на этом же компьютере. Если диск сломается или Windows "
                "переустановят, пропадут и данные, и копии. Выберите папку облачного диска — "
                "копии будут автоматически уезжать в облако.", "warn", wrap=True))
            buttons = []
            for label, path in cloud_candidates():
                b = w.button(f"Копировать в {label}", "primary" if not buttons else None)
                b.setToolTip(str(path))
                b.clicked.connect(lambda _=False, p=path: self._set_extra(p))
                buttons.append(b)
            other = w.button("Выбрать папку…")
            other.clicked.connect(self.choose_extra)
            buttons.append(other)
            card.body.addLayout(_row(*buttons))
        return card

    def _storage_card(self) -> w.Card:
        card = w.Card("Где хранятся данные")
        path, _ = Session.locate(self.session.data_dir)
        card.body.addWidget(w.label(str(path), None, wrap=True))
        card.body.addWidget(w.label(
            "Каждое изменение сразу записывается на диск целиком и «одним движением», поэтому "
            "внезапное выключение компьютера не испортит файл.", "secondary", wrap=True))
        open_btn = w.button("Открыть папку")
        open_btn.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self.session.data_dir))))
        card.body.addLayout(_row(open_btn))
        from ..paths import APP_VERSION
        card.body.addWidget(w.label(f"Трекер привычек и задач, версия {APP_VERSION}", "caption"))
        return card

    # ---------------------------------------------------------------- пароль

    def enable_password(self) -> None:
        dlg = PasswordDialog(self, "Установить пароль",
                             "Пароль будет спрашиваться при каждом запуске. Данные и резервные "
                             "копии будут зашифрованы.", "Установить пароль")
        if dlg.exec() != QDialog.Accepted:
            return
        with _Busy():
            code = self.session.enable_password(dlg.password())
        RecoveryCodeDialog(self, code).exec()
        self.refresh()

    def change_password(self) -> None:
        dlg = PasswordDialog(self, "Сменить пароль", "Код восстановления останется прежним.",
                             "Сменить пароль", current=self.session.keyring)
        if dlg.exec() == QDialog.Accepted:
            with _Busy():
                self.session.change_password(dlg.password())
            QMessageBox.information(self, "Пароль изменён", "Новый пароль будет спрашиваться при входе.")

    def new_code(self) -> None:
        box = QMessageBox(QMessageBox.Question, "Новый код восстановления",
                          "Создать новый код восстановления?", parent=self)
        box.setInformativeText("Старый код перестанет работать для текущих данных.")
        yes = box.addButton("Создать код", QMessageBox.AcceptRole)
        box.addButton("Отмена", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is yes:
            with _Busy():
                code = self.session.new_recovery_code()
            RecoveryCodeDialog(self, code).exec()

    def disable_password(self) -> None:
        box = QMessageBox(QMessageBox.Warning, "Отключить пароль",
                          "Отключить пароль и шифрование?", parent=self)
        box.setInformativeText("Файл данных станет обычным, его сможет открыть любой, у кого "
                               "есть доступ к компьютеру. Уже сделанные зашифрованные копии "
                               "останутся зашифрованными.")
        yes = box.addButton("Отключить", QMessageBox.DestructiveRole)
        box.addButton("Отмена", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not yes:
            return
        dlg = ConfirmPasswordDialog(self, self.session.keyring,
                                    "Введите текущий пароль, чтобы отключить защиту.", "Отключить")
        if dlg.exec() != QDialog.Accepted:
            return
        self.session.disable_password()
        self.refresh()

    # ---------------------------------------------------------------- копии

    def backup_now(self) -> None:
        try:
            made = self.session.backup_now()
        except OSError as e:
            QMessageBox.warning(self, "Копия не сделана", f"Не удалось сохранить копию:\n{e}")
            return
        where = "\n".join(str(p.parent) for p in made)
        QMessageBox.information(self, "Копия сохранена", f"Копия сохранена в:\n{where}")
        self.refresh()

    def restore(self) -> None:
        dlg = RestoreDialog(self, self.session.folders(), "Восстановить из копии",
                            "Выберите копию. Текущие данные будут заменены, но перед этим "
                            "программа сохранит страховочную копию — отменить можно будет так же.")
        if dlg.exec() != QDialog.Accepted or dlg.chosen is None:
            return
        blob = load_backup(self, dlg.chosen, self.session.keyring)
        if blob is None:
            return
        box = QMessageBox(QMessageBox.Question, "Восстановить данные",
                          "Заменить текущие данные выбранной копией?", parent=self)
        box.setInformativeText("Текущее состояние сохранится в страховочную копию.")
        yes = box.addButton("Восстановить", QMessageBox.AcceptRole)
        box.addButton("Отмена", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not yes:
            return
        self.session.restore(blob)
        self.window.reload()
        QMessageBox.information(self.window, "Готово", "Данные восстановлены из копии.")

    def export(self) -> None:
        ext = "htenc" if self.session.encrypted else "sqlite3"
        name = f"{backup.PREFIX}{datetime.now():%Y-%m-%d_%H%M%S}_manual.{ext}"
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить копию", str(Path.home() / name),
                                              f"Копия трекера (*.{ext})")
        if not path:
            return
        try:
            storage.atomic_write(Path(path), self.session.db.store.wrap_for_backup(
                self.session.db.snapshot()))
        except OSError as e:
            QMessageBox.warning(self, "Не сохранено", str(e))
            return
        QMessageBox.information(self, "Копия сохранена", f"Сохранено:\n{path}")

    def choose_extra(self) -> None:
        start = str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Папка для копий (лучше — в облачном диске)", start)
        if folder:
            self._set_extra(Path(folder))

    def _set_extra(self, folder: Path | None) -> None:
        try:
            self.session.set_extra_dir(folder)
        except OSError as e:
            QMessageBox.warning(self, "Папка недоступна", f"Не удалось записать в папку:\n{e}")
            self.session.settings.set("extra_backup_dir", None)
        self.refresh()


class SyncDialog(QDialog):
    """Логин Яндекса и пароль приложения для WebDAV."""

    def __init__(self, parent, current: dict):
        super().__init__(parent)
        from PySide6.QtWidgets import QFormLayout, QLineEdit
        self.setWindowTitle("Подключить Яндекс Диск")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 16)
        lay.setSpacing(10)
        intro = w.label("", "secondary", wrap=True)
        intro.setTextFormat(Qt.RichText)
        intro.setOpenExternalLinks(True)
        intro.setTextInteractionFlags(Qt.TextBrowserInteraction)
        intro.setText(
            "Нужен не ваш обычный пароль, а <b>пароль приложения</b> — он даёт доступ только к "
            "файлам Диска и его можно отозвать в любой момент.<br><br>"
            "1. Откройте <a href='https://id.yandex.ru/security/app-passwords'>Яндекс ID → "
            "Пароли приложений</a>.<br>"
            "2. Выберите «Файлы» (доступ к Диску по WebDAV), назовите, например, «Трекер».<br>"
            "3. Скопируйте пароль и вставьте ниже. Тот же логин и пароль понадобятся в приложении на "
            "телефоне.")
        lay.addWidget(intro)
        form = QFormLayout()
        form.setVerticalSpacing(10)
        self.login = QLineEdit(current.get("login", ""))
        self.login.setPlaceholderText("name@yandex.ru")
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        self.password.setPlaceholderText("Пароль приложения" if not current.get("password")
                                         else "Оставьте пустым, чтобы не менять")
        self.name = QLineEdit(current.get("device_name") or "ПК")
        form.addRow("Логин Яндекса", self.login)
        form.addRow("Пароль приложения", self.password)
        form.addRow("Имя устройства", self.name)
        lay.addLayout(form)
        self.has_password = bool(current.get("password"))
        self.error = w.label("", "danger", wrap=True)
        self.error.hide()
        lay.addWidget(self.error)
        from PySide6.QtWidgets import QDialogButtonBox
        box = QDialogButtonBox()
        ok = box.addButton("Подключить", QDialogButtonBox.AcceptRole)
        ok.setProperty("kind", "primary")
        box.addButton("Отмена", QDialogButtonBox.RejectRole)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)
        self._old = current

    def accept(self) -> None:
        login = self.login.text().strip()
        if not login:
            self.error.setText("Введите логин Яндекса, например name@yandex.ru.")
            self.error.show()
            return
        if not self.password.text() and not self.has_password:
            self.error.setText("Вставьте пароль приложения.")
            self.error.show()
            return
        super().accept()

    def values(self) -> tuple[str, str, str]:
        from ..secret import unprotect
        pw = self.password.text() or unprotect(self._old.get("password"))
        return self.login.text().strip(), pw.replace(" ", ""), self.name.text().strip()
