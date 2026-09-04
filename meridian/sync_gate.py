"""Cadence gate for safe, read-only provider-to-Meridian synchronization."""

from __future__ import annotations

from collections.abc import Callable


class MeridianSyncGate:
    def __init__(
        self,
        *,
        sync: Callable[[], object],
        has_credentials: Callable[[], bool],
        interval_seconds: float,
        clock: Callable[[], float],
    ):
        self._sync = sync
        self._has_credentials = has_credentials
        self._interval_seconds = interval_seconds
        self._clock = clock
        self._last_attempt: float | None = None

    def run_if_due(self):
        now = self._clock()
        if self._last_attempt is not None and now - self._last_attempt < self._interval_seconds:
            return None
        if not self._has_credentials():
            return None
        self._last_attempt = now
        return self._sync()
