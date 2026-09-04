from meridian.sync_gate import MeridianSyncGate


def test_sync_gate_runs_read_sync_once_when_due():
    now = [100.0]
    calls = []
    gate = MeridianSyncGate(
        sync=lambda: calls.append(True) or {"status": "complete"},
        has_credentials=lambda: True,
        interval_seconds=300,
        clock=lambda: now[0],
    )

    assert gate.run_if_due()["status"] == "complete"
    assert gate.run_if_due() is None
    now[0] = 401.0
    assert gate.run_if_due()["status"] == "complete"
    assert calls == [True, True]


def test_sync_gate_skips_when_credentials_are_unavailable():
    calls = []
    gate = MeridianSyncGate(
        sync=lambda: calls.append(True),
        has_credentials=lambda: False,
        interval_seconds=300,
        clock=lambda: 100.0,
    )

    assert gate.run_if_due() is None
    assert calls == []


def test_sync_gate_records_failed_attempt_without_retrying_immediately():
    now = [100.0]
    calls = []
    gate = MeridianSyncGate(
        sync=lambda: calls.append(True) or None,
        has_credentials=lambda: True,
        interval_seconds=300,
        clock=lambda: now[0],
    )

    assert gate.run_if_due() is None
    assert gate.run_if_due() is None
    assert calls == [True]
