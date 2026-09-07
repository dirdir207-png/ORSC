from datetime import datetime, timedelta, timezone

import pytest

from meridian.commitments import CommitmentRepository
from meridian.funding_repo import FundingRuleRepository
from meridian.providers.base import (
    NormalizedAccount,
    NormalizedTransaction,
    ProviderSnapshot,
)
from meridian.repository import FinancialRepository
from meridian.services.activity import get_activity
from meridian.services.today import build_today
from meridian.sync import sync_provider


@pytest.fixture
def repository(tmp_path):
    return FinancialRepository(str(tmp_path / "financial.db"))


def test_today_reports_cash_inputs_and_stale_graph_without_a_forecast(repository):
    run = repository.begin_sync_run(
        provider="crew",
        connection_external_id="crew-household",
        connection_name="Crew",
    )
    checking = repository.upsert_account(
        provider="crew",
        external_id="checking-raw-123456789",
        name="Checking",
        account_type="checking",
        balance=100.0,
        available_balance=80.0,
        connection_id=run.connection_id,
        source_updated_at="2026-08-20T08:00:00Z",
        synced_at="2026-08-20T08:00:00Z",
    )
    repository.upsert_account(
        provider="crew",
        external_id="savings-raw-987654321",
        name="Savings",
        account_type="savings",
        balance=300.0,
        connection_id=run.connection_id,
        source_updated_at="2026-08-20T08:00:00Z",
        synced_at="2026-08-20T08:00:00Z",
    )
    repository.upsert_transaction(
        provider="crew",
        external_id="transaction-raw-111",
        account_id=checking.id,
        amount=-12.5,
        occurred_at="2026-08-20T07:00:00Z",
        description="Coffee",
        status="posted",
        synced_at="2026-08-20T08:00:00Z",
    )
    repository.finish_sync_run(
        run.id,
        status="complete",
        accounts_synced=2,
        transactions_synced=1,
        errors=0,
    )

    result = build_today(
        repository,
        now=datetime.now(timezone.utc),
    )

    assert result["total_cash"] == {
        "amount": 400.0,
        "currency": "USD",
        "by_currency": {"USD": 400.0},
    }
    assert result["safe_to_spend"] == {
        "amount": 380.0,
        "status": "available",
        "inputs": {
            "available_cash": {
                "amount": 380.0,
                "currency": "USD",
                "by_currency": {"USD": 380.0},
            },
            "known_obligations": None,
            "reason": None,
        },
    }
    assert result["upcoming_events"] == []
    assert result["forecast"] is None
    assert result["data_freshness"] == {
        "status": "stale",
        "last_updated_at": "2026-08-20T08:00:00Z",
    }


def test_today_can_include_explainable_forecast_when_planning_repositories_are_supplied(repository):
    account = repository.upsert_account(
        provider="crew",
        external_id="checking",
        name="Checking",
        account_type="checking",
        balance=100,
    )
    for index in range(1, 4):
        repository.upsert_transaction(
            provider="crew",
            external_id=f"spend-{index}",
            account_id=account.id,
            amount=-10,
            occurred_at=f"2026-08-2{index}T10:00:00Z",
            description="Daily spend",
            status="posted",
        )
    commitments = CommitmentRepository(repository.db_path)
    rules = FundingRuleRepository(repository.db_path)

    result = build_today(
        repository,
        commitments,
        rules,
        now=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )

    assert result["forecast"]["available"] is True
    assert result["forecast"]["runway_days"] == 10


def test_today_excludes_pockets_liabilities_and_non_cash_from_cash_inputs(repository):
    for external_id, account_type, balance, available_balance in [
        ("checking", "checking", 100.0, 80.0),
        ("savings", "savings", 50.0, None),
        ("reserved", "pocket", 200.0, 200.0),
        ("credit", "credit_card", -500.0, 500.0),
        ("brokerage", "investment", 1000.0, 1000.0),
    ]:
        repository.upsert_account(
            provider="crew",
            external_id=external_id,
            name=external_id,
            account_type=account_type,
            balance=balance,
            available_balance=available_balance,
            synced_at="2026-08-27T08:00:00Z",
        )

    result = build_today(repository)

    assert result["total_cash"] == {
        "amount": 150.0,
        "currency": "USD",
        "by_currency": {"USD": 150.0},
    }
    assert result["safe_to_spend"]["inputs"]["available_cash"] == {
        "amount": 130.0,
        "currency": "USD",
        "by_currency": {"USD": 130.0},
    }


def test_today_does_not_add_cash_balances_across_currencies(repository):
    repository.upsert_account(
        provider="crew",
        external_id="usd-checking",
        name="USD checking",
        account_type="checking",
        balance=100.0,
        available_balance=80.0,
        currency="USD",
        synced_at="2026-08-27T08:00:00Z",
    )
    repository.upsert_account(
        provider="crew",
        external_id="eur-savings",
        name="EUR savings",
        account_type="savings",
        balance=50.0,
        available_balance=45.0,
        currency="EUR",
        synced_at="2026-08-27T08:00:00Z",
    )

    result = build_today(repository)

    assert result["total_cash"] == {
        "amount": None,
        "currency": None,
        "by_currency": {"EUR": 50.0, "USD": 100.0},
    }
    assert result["safe_to_spend"]["inputs"]["available_cash"] == {
        "amount": None,
        "currency": None,
        "by_currency": {"EUR": 45.0, "USD": 80.0},
    }


def test_today_treats_a_timezone_less_source_snapshot_as_stale(repository):
    run = repository.begin_sync_run(
        provider="crew",
        connection_external_id="crew-household",
        connection_name="Crew",
    )
    repository.upsert_account(
        provider="crew",
        external_id="checking",
        name="Checking",
        account_type="checking",
        balance=100.0,
        connection_id=run.connection_id,
        source_updated_at="2026-08-27T08:00:00",
        synced_at="2026-08-27T08:00:00",
    )
    repository.finish_sync_run(
        run.id,
        status="complete",
        accounts_synced=1,
        transactions_synced=0,
        errors=0,
    )

    result = build_today(
        repository,
        now=datetime(2026, 8, 27, 9, tzinfo=timezone.utc),
    )

    assert result["data_freshness"]["status"] == "stale"


def test_today_treats_a_future_source_snapshot_as_stale(repository):
    now = datetime.now(timezone.utc)
    run = repository.begin_sync_run(
        provider="crew",
        connection_external_id="crew-household",
        connection_name="Crew",
    )
    repository.upsert_account(
        provider="crew",
        external_id="checking",
        name="Checking",
        account_type="checking",
        balance=100.0,
        connection_id=run.connection_id,
        source_updated_at=(now + timedelta(days=1)).isoformat(),
    )
    repository.finish_sync_run(
        run.id,
        status="complete",
        accounts_synced=1,
        transactions_synced=0,
        errors=0,
    )

    result = build_today(
        repository,
        now=now + timedelta(minutes=1),
    )

    assert result["data_freshness"]["status"] == "stale"


def test_today_and_activity_stay_stale_after_partial_sync_until_a_complete_sync(repository):
    class SnapshotAdapter:
        provider_name = "crew"
        connection_external_id = "crew-household"
        connection_name = "Crew"

        def __init__(self, snapshot):
            self.snapshot = snapshot

        def fetch_snapshot(self):
            return self.snapshot

    observed_at = datetime.now(timezone.utc).replace(microsecond=0)
    observed_at_text = observed_at.isoformat().replace("+00:00", "Z")
    account = NormalizedAccount(
        external_id="checking",
        name="Checking",
        account_type="checking",
        balance=100.0,
        source_updated_at=observed_at_text,
    )
    transaction = NormalizedTransaction(
        external_id="coffee",
        account_external_id="checking",
        amount=-3.0,
        occurred_at=observed_at_text,
        description="Coffee",
        status="posted",
        source_updated_at=observed_at_text,
    )
    partial = ProviderSnapshot(
        connection_external_id="crew-household",
        connection_name="Crew",
        accounts=(account,),
        transactions=(transaction,),
        is_complete=False,
        errors=("transaction page unavailable",),
    )

    sync_provider(SnapshotAdapter(partial), repository)

    assert build_today(repository, now=observed_at)["data_freshness"]["status"] == "stale"
    assert get_activity(repository, now=observed_at)["data_freshness"]["status"] == "stale"

    complete = ProviderSnapshot(
        connection_external_id="crew-household",
        connection_name="Crew",
        accounts=(account,),
        transactions=(transaction,),
    )
    sync_provider(SnapshotAdapter(complete), repository)

    read_at = datetime.now(timezone.utc)
    assert build_today(repository, now=read_at)["data_freshness"]["status"] == "fresh"
    assert get_activity(repository, now=read_at)["data_freshness"]["status"] == "fresh"


def test_breakdown_reports_bills_and_goals(tmp_path):
    from meridian.commitments import CommitmentRepository, CommitmentType
    from meridian.db import run_migrations
    from meridian.repository import FinancialRepository
    from meridian.services.today import build_today

    db = str(tmp_path / "r20.db")
    run_migrations(db)
    repo = FinancialRepository(db)
    commitments = CommitmentRepository(db)
    commitments.create(type=CommitmentType.BILL, name="Rent", amount=1200.0, currency="USD", recurrence="monthly")
    commitments.create(type=CommitmentType.GOAL, name="Emergency Fund", target_amount=5000.0, currency="USD")
    from meridian.funding_repo import FundingRuleRepository

    result = build_today(repo, commitments, FundingRuleRepository(db))
    breakdown = result["breakdown"]
    assert breakdown["bills_total"] == 1200.0
    assert breakdown["goals_total"] == 5000.0
    assert breakdown["bills"][0]["name"] == "Rent"
    assert result["setup"]["state"] in ("ready", "in_progress")
    assert result["next_run"] is not None


def test_today_safe_to_spend_matches_free_to_spend_pocket(repository):
    """Safe-to-spend should reflect the 'Free to Spend' pocket's available
    (cleared) balance, not the primary holding Checking pocket."""
    run = repository.begin_sync_run(
        provider="crew",
        connection_external_id="crew-household",
        connection_name="Crew",
    )
    # Primary holding Checking: $0 available.
    repository.upsert_account(
        provider="crew",
        external_id="acct-checking",
        name="Checking",
        account_type="checking",
        balance=500.0,
        available_balance=0.0,
        connection_id=run.connection_id,
        source_updated_at="2026-09-06T08:00:00Z",
    )
    # Discretionary 'Free to Spend' pocket: $71.61 cleared/available.
    repository.upsert_account(
        provider="crew",
        external_id="acct-free-to-spend",
        name="Free to Spend",
        account_type="pocket",
        balance=71.61,
        available_balance=71.61,
        connection_id=run.connection_id,
        source_updated_at="2026-09-06T08:00:00Z",
    )
    repository.finish_sync_run(
        run.id, status="complete", accounts_synced=2, transactions_synced=0, errors=0
    )

    result = build_today(repository, now=datetime.now(timezone.utc))

    assert result["safe_to_spend"]["status"] == "available"
    assert result["safe_to_spend"]["amount"] == 71.61


def test_beacon_signal_notes_negative_safe_to_spend():
    from meridian.services.today import _build_beacon_signal

    forecast = {
        "available": True,
        "runway_days": 0,
        "daily_expense": 25.36,
        "first_shortfall": None,
        "paycheck_covers": False,
        "next_paycheck": "2026-09-15",
        "low_point": -200.0,
    }
    beacon = _build_beacon_signal(forecast, -20.20, "available")
    assert beacon["title"] == "You're spending faster than income."
    assert "restore" in beacon["detail"]


def test_beacon_signal_shortfall_covered_by_paycheck():
    from meridian.services.today import _build_beacon_signal

    forecast = {
        "available": True,
        "runway_days": 0,
        "daily_expense": 25.36,
        "first_shortfall": {
            "date": "2026-09-16",
            "amount": 984.63,
            "cause": "Rent",
        },
        "paycheck_covers": True,
        "next_paycheck": "2026-09-15",
        "low_point": -200.0,
    }
    beacon = _build_beacon_signal(forecast, 50.0, "available")
    assert "covered" in beacon["title"]
    assert "Rent" in beacon["detail"]


def test_virgil_brief_surfaces_negative_safe_to_spend():
    from meridian.services.today import _build_virgil_brief

    forecast = {
        "available": True,
        "runway_days": 0,
        "first_shortfall": None,
        "paycheck_covers": False,
        "next_paycheck": "2026-09-15",
        "factors": (),
        "low_point": -200.0,
    }
    brief = _build_virgil_brief(forecast, forecast, -20.20, "available")
    assert brief["title"] == "You're spending faster than income."
    assert "restore" in brief["summary"]


def test_virgil_brief_falls_back_when_unavailable():
    from meridian.services.today import _build_virgil_brief

    brief = _build_virgil_brief({"available": False}, None, None, "unavailable")
    assert brief["title"] == "A useful connection"
    assert "Nothing" in brief["summary"]


def test_beacon_signal_notes_guaranteed_base_vs_ot():
    from meridian.services.today import _build_beacon_signal

    forecast = {
        "available": True,
        "runway_days": 5,
        "first_shortfall": None,
        "paycheck_covers": False,
        "next_paycheck": "2026-09-16",
        "factors": (),
        "low_point": 100.0,
        "daily_expense": 25.0,
    }
    beacon = _build_beacon_signal(forecast, 100.0, "available", paycheck_amount=1663.0)
    assert "Base $1,663.00 is guaranteed" in beacon["detail"]
