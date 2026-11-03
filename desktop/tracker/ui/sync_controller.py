"""Синхронизация в фоне: сеть — в отдельном потоке, слияние с базой — в основном."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, QTimer, Signal

from ..webdav import SyncError

AUTO_INTERVAL_MS = 5 * 60 * 1000     # раз в 5 минут
AFTER_EDIT_MS = 20 * 1000            # и через 20 с после изменений


class SyncController(QObject):
    statusChanged = Signal(str, bool)    # текст, всё ли хорошо
    dataChanged = Signal()               # пришли изменения с другого устройства

    def __init__(self, session, flush):
        super().__init__()
        self.session = session
        self.flush = flush                 # сохранить открытую заметку перед слиянием
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.busy = False
        self.future = None
        self.stage = ""
        self.poll = QTimer(self)
        self.poll.setInterval(150)
        self.poll.timeout.connect(self._check)
        self.periodic = QTimer(self)
        self.periodic.timeout.connect(lambda: self.run())
        self.periodic.start(AUTO_INTERVAL_MS)
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.timeout.connect(lambda: self.run())
        self.last_text, self.last_ok = "", True
        session.db.on_commit = self._local_change

    def _local_change(self) -> None:
        if not self.busy and self.session.sync_enabled:
            self.debounce.start(AFTER_EDIT_MS)

    def run(self) -> None:
        if self.busy or not self.session.sync_enabled:
            return
        self.busy = True
        self._status("Синхронизация…", True)
        self.stage = "fetch"
        self.device_id = self.session.db.device_id()     # база — только в основном потоке
        self.future = self.pool.submit(self.session.sync_fetch, self.device_id)
        self.poll.start()

    def _check(self) -> None:
        if not self.future.done():
            return
        try:
            result = self.future.result()
        except SyncError as e:
            return self._finish(str(e), False)
        except Exception as e:  # noqa: BLE001 — показать, а не упасть
            return self._finish(f"Не удалось синхронизировать: {e}", False)
        if self.stage == "fetch":
            payloads, cache = result
            try:
                self.flush()
                stats, blob, cache = self.session.sync_apply(payloads, cache)
            except Exception as e:  # noqa: BLE001
                return self._finish(f"Не удалось объединить данные: {e}", False)
            self.stats = stats
            if stats.changed:
                self.dataChanged.emit()
            self.stage = "upload"
            self.future = self.pool.submit(self.session.sync_upload, blob, cache, self.device_id)
        else:
            s = self.stats
            parts = []
            if s.added:
                parts.append(f"добавлено {s.added}")
            if s.updated:
                parts.append(f"обновлено {s.updated}")
            if s.deleted:
                parts.append(f"удалено {s.deleted}")
            self._finish("Синхронизировано" + (f": {', '.join(parts)}" if parts else ""), True)

    def _finish(self, text: str, ok: bool) -> None:
        self.poll.stop()
        self.busy = False
        self._status(text, ok)

    def _status(self, text: str, ok: bool) -> None:
        self.last_text, self.last_ok = text, ok
        self.statusChanged.emit(text, ok)

    def sync_blocking(self) -> None:
        """При закрытии программы — отправить последние изменения (ошибки не мешают выйти)."""
        if not self.session.sync_enabled or self.busy:
            return
        try:
            self.flush()
            self.session.sync_now()
        except Exception:  # noqa: BLE001
            pass
