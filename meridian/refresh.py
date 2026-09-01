"""Automatic live-data refresh: periodically pull a CrewWorkAssistant snapshot
and sync it into the Meridian graph, with on-demand single-flight support."""

import threading
import time
from typing import Callable, Optional

from .sync import SyncReport


class MeridianRefreshService:
    """Run the live-provider sync loop in a background daemon thread.

    - ``interval_seconds``: how often to refresh (default 300s = 5 minutes).
    - ``sync_once``: zero-arg callable returning ``SyncReport`` or None.
    - Each tick is best-effort: failures are logged via ``logger`` and never
      crash the thread. A failed tick leaves the prior good graph intact.
    """

    def __init__(
        self,
        sync_once: Callable[[], Optional[SyncReport]],
        *,
        interval_seconds: int = 300,
        logger: Optional[Callable[[str], None]] = None,
    ):
        if interval_seconds < 30:
            raise ValueError("refresh interval must be at least 30 seconds")
        self._sync_once = sync_once
        self._interval_seconds = interval_seconds
        self._logger = logger or (lambda _: None)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def refresh_once(self) -> Optional[SyncReport]:
        """Single-flight on-demand refresh. Returns the report (or None)."""
        with self._lock:
            return self._sync_once()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                report = self.refresh_once()
                if report is not None:
                    self._logger(
                        f"meridian refresh provider={report.provider} "
                        f"status={report.status} accounts={report.accounts_synced} "
                        f"transactions={report.transactions_synced} errors={report.errors}"
                    )
            except Exception as exc:  # noqa: BLE001 - never kill the loop
                self._logger(f"meridian refresh failed: {type(exc).__name__}: {exc}")
            self._stop.wait(self._interval_seconds)

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, daemon=True, name="meridian-refresh")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()
