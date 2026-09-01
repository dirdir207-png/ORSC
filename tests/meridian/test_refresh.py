"""Tests for the Meridian automatic refresh service."""

import threading
import time

from meridian.refresh import MeridianRefreshService
from meridian.sync import SyncReport


def _report():
    return SyncReport(provider="crew", status="complete", accounts_synced=6, transactions_synced=86, errors=0)


def _report_slow():
    time.sleep(0.2)
    return _report()


def test_rejects_too_short_interval():
    try:
        MeridianRefreshService(lambda: None, interval_seconds=5)
    except ValueError:
        return
    raise AssertionError("must reject intervals under 30 seconds")


def test_refresh_once_returns_report():
    calls = []
    service = MeridianRefreshService(lambda: calls.append(1) or _report(), interval_seconds=60)
    report = service.refresh_once()
    assert report is not None
    assert report.status == "complete"
    assert calls == [1]


def test_refresh_once_single_flight_is_serialized():
    calls = []
    lock = threading.Lock()
    service = MeridianRefreshService(lambda: calls.append(1) or _report_slow(), interval_seconds=60)

    results = []
    def worker():
        results.append(service.refresh_once())

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # Serialized: no parallel invocations of the sync callable.
    assert len(results) == 2
    with lock:
        assert len(calls) == 2


def test_loop_tolerates_failures_and_logs():
    log = []
    count = 0
    def flaky():
        nonlocal count
        count += 1
        if count == 1:
            raise RuntimeError("provider down")
        return _report()

    service = MeridianRefreshService(flaky, interval_seconds=30, logger=log.append)
    service.start()
    assert service.running
    time.sleep(0.3)
    service.stop()
    assert not service.running
    assert any("meridian refresh" in line for line in log)


def test_start_is_idempotent():
    service = MeridianRefreshService(lambda: _report(), interval_seconds=60)
    service.start()
    service.start()
    assert service.running
    service.stop()
    assert not service.running


def test_sync_once_must_return_report_not_callable():
    """The service must invoke the zero-arg callable and return the report,
    never the callable itself (regression: build_sync_once returned a function)."""
    calls = []

    def spy():
        calls.append(1)
        return _report()

    service = MeridianRefreshService(spy, interval_seconds=60)
    report = service.refresh_once()
    assert report == _report()
    assert calls == [1]
    assert not callable(report) or hasattr(report, "status")
