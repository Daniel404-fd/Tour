"""Настройки: пароль, резервные копии, где лежат данные."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QColorDialog, QComboBox, QDialog, QFileDialog, QHBoxLayout, QMessageBox, QPushButton, QSlider, QVBoxLayout,
)

from .. import backup, storage
from ..session import Session
from . import theme as theme_mod
from . import widgets as w
from .theme import theme
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
        super().__init__("Настройки", "Синхронизация, оформление и сохранность данных")
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
            self.box.addWidget(self._appearance_card())
            self.box.addWidget(self._password_card())
            self.box.addWidget(self._backup_card())
            self.box.addWidget(self._storage_card())

    # ---------------------------------------------------------------- оформление

    def _appearance(self) -> dict:
        return dict(self.session.settings.get("appearance") or {})

    def _set_appearance(self, cfg: dict) -> None:
        cfg = {k: v for k, v in cfg.items() if v not in (None, "", {})}
        self.session.settings.set("appearance", cfg or None)
        theme_mod.set_appearance(cfg)           # окно перекрасится сразу

    def _swatches(self, presets, current: str | None, default: str, on_pick, what: str) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)
        cur = (current or default).upper()
        if cur not in {c.upper() for c, _ in presets}:
            presets = list(presets) + [(cur, "Свой цвет")]
        for color, name in presets:
            b = QPushButton("✓" if color.upper() == cur else "")
            b.setFixedSize(28, 28)
            b.setToolTip(name)
            b.setAccessibleName(f"{what}: {name}")
            b.setStyleSheet(f"QPushButton {{ background: {color}; border-radius: 14px; color: white; "
                            f"font-weight: 700; border: 2px solid "
                            f"{theme['text'] if color.upper() == cur else 'transparent'}; padding: 0; }}")
            b.clicked.connect(lambda _=False, c=color: on_pick(None if c.upper() == default.upper() else c))
            row.addWidget(b)
        other = w.button("Другой…", "ghost")

        def custom():
            c = QColorDialog.getColor(QColor(cur), self, f"{what} — свой цвет")
            if c.isValid():
                on_pick(c.name().upper())
        other.clicked.connect(custom)
        row.addWidget(other)
        row.addStretch()
        return row

    def _appearance_card(self) -> w.Card:
        cfg = self._appearance()
        card = w.Card("Оформление")
        card.body.addWidget(w.label("Основной цвет — боковая панель, главные кнопки и ссылки.", "secondary", wrap=True))
        card.body.addLayout(self._swatches(theme_mod.PRIMARY_PRESETS, cfg.get("primary"), "#0F6E6A",
                                           lambda c: self._set_appearance({**cfg, "primary": c}), "Основной цвет"))
        card.body.addWidget(w.label("Цвет отметок и прогресса — выполненные привычки, «кирпичики».",
                                    "secondary", wrap=True))
        card.body.addLayout(self._swatches(theme_mod.ACCENT_PRESETS, cfg.get("accent"), "#4338CA",
                                           lambda c: self._set_appearance({**cfg, "accent": c}), "Цвет прогресса"))

        # боковая панель
        sb = dict(cfg.get("sidebar") or {})
        card.body.addWidget(w.label("Фон боковой панели", "section"))
        mode = QComboBox()
        for key, name in (("neutral", "Светлая, как в Notion"), ("primary", "Основной цвет"),
                          ("color", "Свой цвет"), ("image", "Картинка")):
            mode.addItem(name, key)
        mode.setCurrentIndex(max(0, mode.findData(sb.get("mode", "neutral"))))
        mode.setAccessibleName("Фон боковой панели")
        row = [mode]
        if sb.get("mode") == "color":
            pick = w.button("Выбрать цвет…")
            pick.clicked.connect(lambda: self._pick_sidebar_color(cfg, sb))
            row.append(pick)
        if sb.get("mode") == "image":
            pick = w.button("Выбрать картинку…")
            pick.clicked.connect(lambda: self._pick_sidebar_image(cfg, sb))
            row.append(pick)
        card.body.addLayout(_row(*row))

        def mode_changed(_i):
            key = mode.currentData()
            new = {**sb, "mode": key}
            if key == "color" and not sb.get("color"):
                return self._pick_sidebar_color(cfg, new)
            if key == "image" and not sb.get("image"):
                return self._pick_sidebar_image(cfg, new)
            self._set_appearance({**cfg, "sidebar": new if key != "neutral" else None})
        mode.currentIndexChanged.connect(mode_changed)

        if sb.get("mode") == "image" and sb.get("image"):
            dim = QSlider(Qt.Horizontal)
            dim.setRange(0, 75)
            dim.setValue(int(float(sb.get("dim", 0.4)) * 100))
            dim.setFixedWidth(220)
            dim.setAccessibleName("Затемнение картинки")
            dim.setToolTip("Чем темнее, тем лучше читаются названия разделов")
            dim.sliderReleased.connect(lambda: self._set_appearance(
                {**cfg, "sidebar": {**sb, "dim": dim.value() / 100}}))
            card.body.addLayout(_row(w.label("Затемнение", "secondary"), dim))

        # тема
        tm = QComboBox()
        for key, name in (("system", "Как в Windows"), ("light", "Светлая"), ("dark", "Тёмная")):
            tm.addItem(name, key)
        tm.setCurrentIndex(max(0, tm.findData(cfg.get("mode", "system"))))
        tm.setAccessibleName("Тема")
        tm.currentIndexChanged.connect(lambda _i: self._set_appearance(
            {**cfg, "mode": None if tm.currentData() == "system" else tm.currentData()}))
        reset = w.button("Вернуть как было", "ghost")
        reset.clicked.connect(lambda: self._set_appearance({}))
        reset.setEnabled(bool(cfg))
        card.body.addLayout(_row(w.label("Тема", "secondary"), tm, reset))
        card.body.addWidget(w.label("Цвета подбираются так, чтобы текст оставался читаемым и в тёмной теме. "
                                    "На телефоне оформление настраивается отдельно.", "caption", wrap=True))
        return card

    def _pick_sidebar_color(self, cfg: dict, sb: dict) -> None:
        c = QColorDialog.getColor(QColor(sb.get("color") or theme["teal"]), self, "Цвет боковой панели")
        if c.isValid():
            self._set_appearance({**cfg, "sidebar": {**sb, "mode": "color", "color": c.name().upper()}})
        else:
            self.refresh()

    def _pick_sidebar_image(self, cfg: dict, sb: dict) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Картинка для боковой панели", str(Path.home()),
                                              "Изображения (*.png *.jpg *.jpeg *.bmp *.webp)")
        if not path:
            self.refresh()
            return
        from PySide6.QtGui import QImage
        img = QImage(path)
        if img.isNull():
            QMessageBox.warning(self, "Картинка", "Не удалось открыть этот файл как изображение.")
            self.refresh()
            return
        # копия рядом с данными: картинка не пропадёт, если исходный файл удалят или переместят
        if img.height() > 1600:
            img = img.scaledToHeight(1600, Qt.SmoothTransformation)
        dest = self.session.data_dir / "sidebar.png"
        img.save(str(dest), "PNG")
        self._set_appearance({**cfg, "sidebar": {**sb, "mode": "image", "image": str(dest),
                                                 "dim": sb.get("dim", 0.4)}})

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
            "Изменения записываются на диск целиком и «одним движением» (не позже чем через полсекунды), "
            "поэтому внезапное выключение компьютера не испортит файл.", "secondary", wrap=True))
        open_btn = w.button("Открыть папку")
        open_btn.clicked.connect(lambda: QDesktopServices.openUrl(
            QUrl.fromLocalFile(str(self.session.data_dir))))
        move_btn = w.button("Выбрать другую папку…")
        move_btn.setToolTip("Например, другой диск или папка, которую сохраняет облако")
        move_btn.clicked.connect(self.change_data_dir)
        row = [open_btn, move_btn]
        from ..relocate import home_dir
        if self.session.data_dir.resolve() != home_dir().resolve():
            back = w.button("Вернуть обычную папку", "ghost")
            back.clicked.connect(lambda: self.change_data_dir(home_dir()))
            row.append(back)
        card.body.addLayout(_row(*row))
        from ..paths import APP_VERSION
        card.body.addWidget(w.label(f"Трекер привычек и задач, версия {APP_VERSION}", "caption"))
        return card

    # ---------------------------------------------------------------- папка данных

    def change_data_dir(self, folder=None) -> None:
        from .. import relocate
        cur = self.session.data_dir
        if folder is None:
            path = QFileDialog.getExistingDirectory(self, "Папка для данных трекера", str(cur.parent))
            if not path:
                return
            folder = Path(path)
            if folder.name != relocate.APP_DIR_NAME and not relocate.has_data(folder) and any(folder.iterdir()):
                folder = folder / relocate.APP_DIR_NAME     # в непустую чужую папку — своей подпапкой
        folder = Path(folder)
        if folder.resolve() == cur.resolve():
            return
        use_existing = False
        if relocate.has_data(folder):
            box = QMessageBox(QMessageBox.Question, "В папке уже есть данные",
                              f"В папке «{folder}» уже лежат данные трекера.", parent=self)
            box.setInformativeText("Открыть их вместо текущих или заменить их текущими данными?\n"
                                   "(Заменённые файлы не пропадут — они попадут в резервные копии этой папки.)")
            open_b = box.addButton("Открыть те данные", QMessageBox.AcceptRole)
            repl_b = box.addButton("Заменить текущими", QMessageBox.DestructiveRole)
            box.addButton("Отмена", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is open_b:
                use_existing = True
            elif box.clickedButton() is not repl_b:
                return
            else:
                from .. import backup
                for name in (relocate.PLAIN_NAME, relocate.ENCRYPTED_NAME):
                    f = folder / name
                    if f.exists():
                        bdir = backup.backup_dir(folder)
                        bdir.mkdir(parents=True, exist_ok=True)
                        f.replace(bdir / f"replaced-{datetime.now():%Y%m%d-%H%M%S}-{name}")
        if hasattr(self.window(), "_flush"):
            self.window()._flush()
        self.session.db.flush_save()
        if not use_existing:
            try:
                with _Busy():
                    relocate.copy_data(cur, folder)
            except (OSError, ValueError) as e:
                QMessageBox.warning(self, "Не удалось перенести", f"Данные остались на месте.\n\n{e}")
                return
        relocate.set_location(folder)
        QMessageBox.information(self, "Папка изменена",
                                f"Теперь данные хранятся здесь:\n{folder}\n\n"
                                + ("" if use_existing else
                                   f"В прежней папке осталась копия — её можно удалить, когда убедитесь, что всё на месте:\n{cur}\n\n")
                                + "Программа сейчас перезапустится.")
        from PySide6.QtCore import QProcess
        from PySide6.QtWidgets import QApplication
        import sys
        args = sys.argv[1:] if getattr(sys, "frozen", False) else sys.argv
        QProcess.startDetached(sys.executable, args)
        QApplication.instance().quit()

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
