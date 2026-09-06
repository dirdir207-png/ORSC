"""Tests for the read-only Biller Monitor (R33).

Pure unit tests over meridian.billers.build_biller_monitor — no provider, no
network, no financial mutation. Verifies the honest boundary: it computes
bill state from commitments + charge history, tags provenance, and never
fabricates autopay/statement/biller-health fields.
"""


from datetime import date

import pytest

from meridian.billers import bill_status_for, build_biller_monitor
from meridian.commitments import Commitment, CommitmentStatus, CommitmentType
from meridian.models import TransactionRecord


def _bill(**overrides):
    base = dict(
        id=1,
        type=CommitmentType.BILL,
        name="Verizon",
        status=CommitmentStatus.ACTIVE,
        priority=3,
        currency="USD",
        target_amount=None,
        target_date=None,
        funded_amount=0.0,
        amount=101.57,
        due_date="2026-09-22",
        recurrence="monthly",
        cadence=None,
        minimum_payment=None,
        buffer_minimum=None,
        payoff_strategy=None,
        backing_account_id=None,
        legacy_source="crew",
        legacy_id="legacy-1",
        migration_version="005",
        created_at="2026-08-01T00:00:00Z",
        updated_at="2026-08-01T00:00:00Z",
    )
    return Commitment(**{**base, **overrides})


def _tx(**overrides):
    base = dict(
        id=1,
        provider="crew",
        external_id="tx-1",
        account_id=1,
        amount=-101.57,
        currency="USD",
        occurred_at="2026-08-22T12:00:00Z",
        posted_at=None,
        description="Verizon Wireless",
        merchant="Verizon",
        status="posted",
        raw_description=None,
        source_updated_at=None,
        classification_category=None,
        classification_kind=None,
        classification_confidence=None,
        classification_rule_id=None,
        classification_evidence=None,
        classification_method=None,
        classification_provider=None,
        classification_model=None,
        classification_version=0,
        synced_at="2026-08-22T12:00:00Z",
        created_at="2026-08-22T12:00:00Z",
        updated_at="2026-08-22T12:00:00Z",
    )
    return TransactionRecord(**{**base, **overrides})


def test_monitor_flags_due_soon_bill():
    bills = build_biller_monitor(
        [_bill(due_date="2026-09-24")], [], today=__import__("datetime").date(2026, 9, 22)
    )
    assert bills[0].status == "due_soon"
    assert bills[0].next_due == "2026-09-24"


def test_monitor_rolls_past_due_forward_by_recurrence():
    bill = _bill(due_date="2026-08-22", recurrence="monthly")
    bills = build_biller_monitor([bill], [], today=__import__("datetime").date(2026, 9, 22))
    # Past due (Aug 22) rolls forward to the next monthly occurrence (Sep 22).
    assert bills[0].next_due == "2026-09-22"


def test_monitor_matches_last_paid_and_reports_amount_change():
    bill = _bill(name="Verizon", amount=101.57)
    # A charge at 99.0 last month -> amount change +2.57 (below threshold).
    tx = _tx(merchant="Verizon", description="Verizon Wireless", amount=-99.0)
    bills = build_biller_monitor([bill], [tx], today=__import__("datetime").date(2026, 9, 22))
    assert bills[0].last_paid_amount == 99.0
    assert bills[0].amount_change == pytest.approx(2.57)
    assert bills[0].status != "changed"  # under 5.00 threshold


def test_monitor_is_best_effort_on_brand_alias_and_returns_no_match():
    # Bill "Xfinity" vs merchant "Comcast": a pure token matcher cannot bridge
    # the brand->corporate alias. The monitor must NOT fabricate a match; it
    # returns last_paid=None (best-effort) rather than a guessed value.
    bill = _bill(name="Xfinity", amount=93.0)
    tx = _tx(merchant="Comcast", description="Xfinity Internet", amount=-89.99)
    bills = build_biller_monitor([bill], [tx], today=__import__("datetime").date(2026, 9, 22))
    assert bills[0].last_paid_amount is None
    assert bills[0].amount_change is None


def test_monitor_flags_large_amount_change():
    bill = _bill(name="Eversource", amount=210.0)
    tx = _tx(merchant="Eversource", amount=-189.5)
    bills = build_biller_monitor([bill], [tx], today=__import__("datetime").date(2026, 9, 22))
    assert bills[0].amount_change == pytest.approx(20.5)
    assert bills[0].status == "changed"


def test_monitor_marks_unfunded_when_reserved_below_amount_and_not_due_soon():
    bill = _bill(name="Rent", amount=1442.0, funded_amount=500.0, due_date="2026-12-01")
    bills = build_biller_monitor([bill], [], today=__import__("datetime").date(2026, 9, 22))
    assert bills[0].status == "unfunded"


def test_monitor_marks_on_track_when_funded():
    bill = _bill(name="Rent", amount=1442.0, funded_amount=1500.0)
    bills = build_biller_monitor([bill], [], today=__import__("datetime").date(2026, 9, 22))
    assert bills[0].status == "on_track"


def test_monitor_ignores_non_negative_transactions_for_last_paid():
    bill = _bill(name="Verizon", amount=101.57)
    tx = _tx(amount=101.57)  # positive -> a credit/reversal, not a charge
    bills = build_biller_monitor([bill], [tx], today=__import__("datetime").date(2026, 9, 22))
    assert bills[0].last_paid_amount is None
    assert bills[0].last_paid_date is None


def test_monitor_does_not_invent_autopay_or_statement_fields():
    bills = build_biller_monitor([_bill()], [], today=__import__("datetime").date(2026, 9, 22))
    monitor_dict = bills[0]
    attrs = {f for f in dir(monitor_dict) if not f.startswith("_")}
    assert "autopay" not in attrs
    assert "statement" not in attrs
    assert "health" not in attrs


def test_monitor_tags_provenance_and_reuses_commitment_id():
    bills = build_biller_monitor([_bill(legacy_source="crew")], [], today=__import__("datetime").date(2026, 9, 22))
    assert bills[0].provenance["amount"] == "crew_bill"
    assert bills[0].provenance["last_paid"] == "computed"
    # No second bill identity: same commitment id.
    assert bills[0].commitment_id == 1


def test_monitor_sorts_by_next_due():
    a = _bill(id=1, name="Rent", due_date="2026-09-10")
    b = _bill(id=2, name="Verizon", due_date="2026-09-25")
    bills = build_biller_monitor([a, b], [], today=__import__("datetime").date(2026, 9, 1))
    assert [x.name for x in bills] == ["Rent", "Verizon"]


# ---- R33 Plan-card badge (bill_status_for) ----

def test_plan_badge_marks_unfunded_when_reserved_below_amount():
    bill = _bill(name="Xfinity", amount=93.0, funded_amount=0.0, due_date="2026-12-01")
    assert bill_status_for(bill, today=date(2026, 9, 22)) == "unfunded"


def test_plan_badge_marks_due_soon_when_unfunded_and_near():
    bill = _bill(name="Rent", amount=1442.0, funded_amount=710.98, due_date="2026-09-24")
    # Underfunded AND due within 7 days -> urgent "due soon", not generic underfund.
    assert bill_status_for(bill, today=date(2026, 9, 22)) == "due_soon"


def test_plan_badge_is_on_track_when_fully_funded_even_if_due():
    bill = _bill(name="Electric", amount=189.5, funded_amount=189.5, due_date="2026-09-24")
    assert bill_status_for(bill, today=date(2026, 9, 22)) == "on_track"


def test_plan_badge_is_on_track_when_unfunded_but_far_out():
    # Unfunded but due in 3+ weeks: covers the funding, badge stays neutral.
    bill = _bill(name="Verizon", amount=101.57, funded_amount=0.0, due_date="2026-10-20")
    assert bill_status_for(bill, today=date(2026, 9, 22)) == "unfunded"


# ---- R33 "changed" badge (amount drift) ----

def test_plan_badge_flags_changed_when_amount_drifted_and_funded():
    bill = _bill(name="Verizon", amount=101.57, funded_amount=101.57, due_date="2026-10-01")
    assert bill_status_for(bill, today=date(2026, 9, 22), last_paid_amount=85.0) == "changed"


def test_plan_badge_not_changed_below_threshold():
    bill = _bill(name="Verizon", amount=101.57, funded_amount=101.57, due_date="2026-10-01")
    assert bill_status_for(bill, today=date(2026, 9, 22), last_paid_amount=99.0) == "on_track"


def test_plan_badge_changed_wins_over_unfunded():
    # Underfunded AND amount drifted: the drift is the more actionable signal.
    bill = _bill(name="Eversource", amount=210.0, funded_amount=0.0, due_date="2026-12-01")
    assert bill_status_for(bill, today=date(2026, 9, 22), last_paid_amount=189.5) == "changed"


def test_plan_badge_changed_with_no_last_paid_returns_funding_status():
    # No last-paid supplied -> cannot claim changed; stays underfunded.
    bill = _bill(name="Eversource", amount=210.0, funded_amount=0.0, due_date="2026-12-01")
    assert bill_status_for(bill, today=date(2026, 9, 22)) == "unfunded"
