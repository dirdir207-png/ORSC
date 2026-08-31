from meridian.context import ContextRepository, ContextSignal, scenario_assumptions
from meridian.repository import FinancialRepository


def test_context_repository_revokes_one_source_without_touching_another(tmp_path):
    repository = ContextRepository(str(tmp_path / "context.db"))
    calendar = repository.save(
        ContextSignal(
            id=None,
            source_kind="calendar",
            source_id="trip-1",
            kind="travel",
            occurred_on="2026-09-10",
            range_min=None,
            range_max=None,
            confidence=0.6,
            confirmed=False,
        )
    )
    payroll = repository.save(
        ContextSignal(
            id=None,
            source_kind="document",
            source_id="stub-1",
            kind="pay_stub",
            occurred_on="2026-09-01",
            range_min=2000,
            range_max=2000,
            confidence=0.99,
            confirmed=True,
        )
    )

    assert repository.revoke_source("calendar", "trip-1") == 1
    assert repository.get(calendar.id) is None
    assert repository.get(payroll.id) == payroll


def test_unconfirmed_calendar_event_never_infers_expense_amount(tmp_path):
    graph = FinancialRepository(str(tmp_path / "graph.db"))
    signal = ContextSignal(
        id=1,
        source_kind="calendar",
        source_id="trip-1",
        kind="travel",
        occurred_on="2026-09-10",
        range_min=None,
        range_max=None,
        confidence=0.6,
        confirmed=False,
    )

    assumptions = scenario_assumptions([signal], graph)

    assert assumptions[0].kind == "travel_pressure"
    assert assumptions[0].range_min is None
    assert assumptions[0].range_max is None
    assert assumptions[0].confirmation_state == "needs_confirmation"


def test_pay_stub_deposit_mismatch_is_a_sourced_hypothesis(tmp_path):
    graph = FinancialRepository(str(tmp_path / "graph.db"))
    account = graph.upsert_account(
        provider="crew",
        external_id="checking",
        name="Checking",
        account_type="checking",
        balance=1000,
    )
    graph.upsert_transaction(
        provider="crew",
        external_id="pay",
        account_id=account.id,
        amount=1900,
        occurred_at="2026-09-01T12:00:00Z",
        description="Payroll deposit",
        merchant="Employer payroll",
        status="posted",
    )
    signal = ContextSignal(
        id=2,
        source_kind="document",
        source_id="stub-1",
        kind="pay_stub",
        occurred_on="2026-09-01",
        range_min=2000,
        range_max=2000,
        confidence=0.99,
        confirmed=True,
    )

    assumptions = scenario_assumptions([signal], graph)

    assert assumptions[0].kind == "payroll_mismatch"
    assert assumptions[0].source_ids == ("document:stub-1",)
    assert assumptions[0].range_min == 100
    assert assumptions[0].range_max == 100
    assert assumptions[0].confirmation_state == "confirmed"
