"""Self-learning paycheck detection tests."""
from datetime import datetime, timezone

from meridian.paycheck_learning import _cadence_guess, learn_paycheck


class Tx:
    def __init__(self, merchant, amount, occurred_at, classification_kind="income"):
        self.merchant = merchant
        self.description = merchant
        self.amount = amount
        self.occurred_at = occurred_at
        self.classification_kind = classification_kind


def _dt(day):
    return datetime(2026, 9, day, 12, 0, tzinfo=timezone.utc).isoformat()


def test_learns_recurring_cash_app_paycheck_collapsing_same_day_pairs():
    """Cash App records a transfer + a split on the same payday; collapse those
    so the cadence reflects the real biweekly period, and detect the amount."""
    txns = [
        Tx("Cash App", 490.25, "2026-07-22T20:01:59+00:00"),
        Tx("Cash App", 490.25, "2026-07-22T20:02:30+00:00"),
        Tx("Cash App", 490.25, "2026-07-22T20:03:00+00:00"),
        Tx("Cash App", 490.25, "2026-08-05T15:00:00+00:00"),
        Tx("Cash App", 490.25, "2026-08-05T15:01:00+00:00"),
        Tx("Cash App", 490.25, "2026-08-19T12:00:00+00:00"),
        Tx("Cash App", 490.25, "2026-08-19T12:01:00+00:00"),
    ]
    learned = learn_paycheck(txns)
    assert learned is not None
    assert learned["source"] == "Cash App"
    # Three pay periods (Jul 22, Aug 5, Aug 19) -> biweekly, ~$980-1470 per period.
    assert learned["cadence"] == "biweekly"
    assert learned["occurrences"] == 3


def test_ignores_one_off_income():
    """A single large deposit is not a paycheck (need >=3 occurrences)."""
    txns = [Tx("Some Employer", 2000.0, "2026-09-01T12:00:00+00:00") for _ in range(2)]
    learned = learn_paycheck(txns)
    assert learned is None


def test_ignores_tiny_or_reimbursement_credits():
    txns = [
        Tx("Splitwise", 59.99, "2026-09-05T02:50:03+00:00", "reimbursement"),
        Tx("Interest paid", 0.46, "2026-09-01T09:46:56+00:00", "income"),
        Tx("Cash App", 490.25, "2026-08-19T20:01:59+00:00", "transfer"),
    ]
    learned = learn_paycheck(txns)
    assert learned is None


def test_reports_amount_variability_range():
    """When the recurring amount varies, the learnt range reflects it."""
    txns = [
        Tx("Employer", 1500.0, "2026-08-01T12:00:00+00:00"),
        Tx("Employer", 1500.0, "2026-08-15T12:00:00+00:00"),
        Tx("Employer", 1750.0, "2026-09-01T12:00:00+00:00"),
    ]
    learned = learn_paycheck(txns)
    assert learned is not None
    assert learned["min_amount"] == 1500.0
    assert learned["max_amount"] == 1750.0
    assert learned["amount"] == 1500.0  # median


def test_cadence_guess_buckets():
    assert _cadence_guess([7, 7]) == ("weekly", 1)
    assert _cadence_guess([14, 14]) == ("biweekly", 1)
    assert _cadence_guess([30, 31]) == ("monthly", 1)
