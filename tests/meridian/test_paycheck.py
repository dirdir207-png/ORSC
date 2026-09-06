"""Tests for the configurable paycheck (funding source) module.

Pure unit tests over PaycheckRepository + future_paycheck_events, no provider,
no network, no financial mutation.
"""

from datetime import date

from meridian.paycheck import (
    PaycheckConfig,
    PaycheckRepository,
    build_cash_events,
    future_paycheck_events,
)


def _config(cadence="monthly", amount=2000.0, next_date="2026-09-15", active=True):
    return PaycheckConfig(cadence=cadence, amount=amount, next_date=next_date, active=active)


def test_repo_persists_and_roundtrips(tmp_path):
    repo = PaycheckRepository(str(tmp_path / "p.db"))
    cfg = _config(cadence="biweekly", amount=1200.0, next_date="2026-09-18")
    repo.save(cfg)
    got = repo.get()
    assert got == cfg


def test_repo_get_none_when_unset(tmp_path):
    repo = PaycheckRepository(str(tmp_path / "p.db"))
    assert repo.get() is None


def test_repo_clear_removes(tmp_path):
    repo = PaycheckRepository(str(tmp_path / "p.db"))
    repo.save(_config())
    repo.clear()
    assert repo.get() is None


def test_future_paycheck_events_generates_from_next_date():
    cfg = _config(cadence="monthly", amount=2000.0, next_date="2026-09-15")
    events = future_paycheck_events(cfg, as_of=date(2026, 9, 1), horizon_days=90)
    assert events[0] == (date(2026, 9, 15), 2000.0)
    assert len(events) >= 3  # ~3 monthly paychecks in 90 days


def test_future_paycheck_events_rolls_past_date_forward():
    # Configured next_date is in the past; roll to the next occurrence.
    cfg = _config(cadence="monthly", amount=1000.0, next_date="2026-08-15")
    events = future_paycheck_events(cfg, as_of=date(2026, 9, 20), horizon_days=60)
    assert events[0][0] == date(2026, 10, 15)
    assert events[0][1] == 1000.0


def test_future_paycheck_events_drops_when_inactive_or_zero():
    assert future_paycheck_events(_config(active=False), as_of=date(2026, 9, 1)) == []
    assert future_paycheck_events(_config(amount=0.0), as_of=date(2026, 9, 1)) == []


def test_build_cash_events_includes_current_cash_and_paychecks():
    cfg = _config(amount=2000.0, next_date="2026-09-15")
    events = build_cash_events(71.61, cfg, as_of=date(2026, 9, 6), horizon_days=30)
    assert events[0] == (date(2026, 9, 6), 71.61)
    assert any(d == date(2026, 9, 15) for d, _ in events)
