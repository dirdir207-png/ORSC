from datetime import date
from types import SimpleNamespace

import pytest

from meridian.payday import recognize_payday


def income_transactions(dates, amounts=None):
    values = amounts or [2800.0] * len(dates)
    return [
        SimpleNamespace(
            id=index,
            amount=amount,
            occurred_at=f"{day}T12:00:00Z",
            classification_kind="income",
        )
        for index, (day, amount) in enumerate(zip(dates, values), start=1)
    ]


@pytest.mark.parametrize(
    ("dates", "cadence", "next_date"),
    [
        (
            ["2026-07-10", "2026-07-24", "2026-08-07", "2026-08-21"],
            "biweekly",
            date(2026, 9, 4),
        ),
        (
            ["2026-05-29", "2026-06-30", "2026-07-31", "2026-08-31"],
            "monthly",
            date(2026, 9, 30),
        ),
    ],
)
def test_recognize_payday_uses_literal_date_sequences(dates, cadence, next_date):
    pattern = recognize_payday(
        income_transactions(dates), as_of=date(2026, 8, 31)
    )

    assert pattern.cadence == cadence
    assert pattern.next_date == next_date
    assert pattern.typical_amount == 2800.0
    assert pattern.evidence_ids == (1, 2, 3, 4)


def test_recognize_payday_refuses_irregular_or_insufficient_evidence():
    irregular = income_transactions(["2026-06-02", "2026-06-19", "2026-07-31"])

    assert recognize_payday(irregular, as_of=date(2026, 8, 31)) is None
    assert (
        recognize_payday(irregular[:2], as_of=date(2026, 8, 31)) is None
    )
