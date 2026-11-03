"""Точка входа: python -m tracker.main"""
import sys
import traceback
from pathlib import Path

import hashlib

from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from .db import default_data_dir
from .paths import APP_VERSION, resource_path
from .ui import theme
from .ui.main_window import MainWindow
from .ui.security import open_session

APP_NAME = "HabitTracker"


def _set_windows_app_id() -> None:
    # Чтобы в панели задач Windows показывалась иконка приложения, а не Python.
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                f"HabitTracker.App.{APP_VERSION}")
        except Exception:
            pass


def _install_crash_handler() -> None:
    """Необработанные ошибки пишем в лог и показываем окно, а не молча падаем."""
    def handler(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            log = default_data_dir() / "error.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            with log.open("a", encoding="utf-8") as f:
                f.write(text + "\n")
        except Exception:
            log = None
        if QApplication.instance() is not None:
            QMessageBox.critical(
                None, "Ошибка",
                "Произошла непредвиденная ошибка.\n\n"
                f"{exc_type.__name__}: {exc}"
                + (f"\n\nПодробности записаны в:\n{log}" if log else ""))
        else:
            sys.__excepthook__(exc_type, exc, tb)
    sys.excepthook = handler


def main() -> int:
    _set_windows_app_id()
    _install_crash_handler()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    translator = QTranslator(app)
    if translator.load(QLocale("ru_RU"), "qtbase", "_",
                       QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
        app.installTranslator(translator)
    try:
        from .backup import Settings
        appearance = Settings(default_data_dir()).get("appearance")
    except Exception:
        appearance = None
    theme.install(app, appearance)
    icon = resource_path("icon.png")
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))

    data_dir = default_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)

    # Два открытых окна писали бы в один файл и затирали изменения друг друга.
    # Именованный канал исчезает вместе с процессом — «зависшего» замка не бывает.
    server_name = "HabitTracker-" + hashlib.sha1(str(data_dir).lower().encode()).hexdigest()[:12]
    probe = QLocalSocket()
    probe.connectToServer(server_name)
    if probe.waitForConnected(400):
        probe.write(b"show")
        probe.flush()
        probe.waitForBytesWritten(400)
        return 0  # уже открытое окно выйдет на передний план
    QLocalServer.removeServer(server_name)
    server = QLocalServer()
    server.listen(server_name)
    state: dict = {}

    def bring_to_front() -> None:
        conn = server.nextPendingConnection()
        win = state.get("window")
        if win is not None and win.isHidden() is False:
            win.showNormal()
            win.raise_()
            win.activateWindow()
        if conn is not None:
            conn.disconnectFromServer()

    server.newConnection.connect(bring_to_front)

    warned = []

    def on_save_error(e: Exception) -> None:
        if not warned:
            warned.append(True)
            QMessageBox.warning(
                None, "Не удалось сохранить",
                f"Изменения не записались на диск:\n{e}\n\nОни пока в памяти. Программа "
                "попробует снова при следующем изменении. Проверьте свободное место на диске.")

    session = open_session(data_dir, on_save_error)
    if session is None:
        return 0
    try:
        session.auto_backup()
    except OSError as e:
        log = data_dir / "error.log"
        with log.open("a", encoding="utf-8") as f:
            f.write(f"auto backup failed: {e}\n")

    window = MainWindow(session)
    state["window"] = window
    window.show()
    code = app.exec()
    session.db.close()
    server.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
