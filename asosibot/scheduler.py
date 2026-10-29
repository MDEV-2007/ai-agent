"""Reminder scheduler — fon thread har 15 soniyada vaqti kelgan eslatmalarni
tekshiradi va callback orqali yetkazadi (masalan Telegramga yuboradi). Eslatma
bir marta ishga tushgach 'triggered' bo'ladi (takror yuborilmaydi).
"""
import threading
import time
from datetime import datetime
from typing import Callable

from . import store

CHECK_INTERVAL_SEC = 15


class ReminderScheduler:
    def __init__(self, on_due: Callable[[str, str], None]):
        """on_due(owner, message) — eslatma vaqti kelganda chaqiriladi."""
        self._on_due = on_due
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                for row in store.due_reminders(now_iso):
                    store.mark_reminder_triggered(row["id"])
                    try:
                        self._on_due(row["owner"], row["message"])
                    except Exception:
                        pass  # bitta yetkazish xatosi butun sikldni to'xtatmasin
            except Exception:
                pass
            self._stop.wait(CHECK_INTERVAL_SEC)
