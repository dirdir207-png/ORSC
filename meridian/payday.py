"""Conservative, deterministic recognition of recurring payday evidence."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from statistics import median


@dataclass(frozen=True)
class PaydayPattern:
    cadence: str
    next_date: date
    typical_amount: float
    confidence: float
    evidence_ids: tuple[int, ...]


def _transaction_date(transaction) -> date | None:
    value = getattr(transaction, "occurred_at", None)
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _next_monthly(last: date) -> date:
    year = last.year + (1 if last.month == 12 else 0)
    month = 1 if last.month == 12 else last.month + 1
    day = min(last.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _next_semimonthly(last: date) -> date:
    if last.day <= 15:
        return last.replace(day=calendar.monthrange(last.year, last.month)[1])
    year = last.year + (1 if last.month == 12 else 0)
    month = 1 if last.month == 12 else last.month + 1
    return date(year, month, 15)


def recognize_payday(transactions, *, as_of: date) -> PaydayPattern | None:
    """Recognize only well-supported recurring positive-income patterns."""
    evidence = []
    for transaction in transactions:
        occurred = _transaction_date(transaction)
        if (
            occurred is None
            or occurred > as_of
            or float(getattr(transaction, "amount", 0)) <= 0
            or getattr(transaction, "classification_kind", None) != "income"
        ):
            continue
        evidence.append((occurred, transaction))
    evidence.sort(key=lambda item: item[0])
    if len(evidence) < 4:
        return None

    intervals = [
        (current[0] - prior[0]).days
        for prior, current in zip(evidence, evidence[1:])
    ]
    cadence = None
    next_date = None
    if all(6 <= value <= 8 for value in intervals):
        cadence = "weekly"
        next_date = evidence[-1][0] + timedelta(days=7)
    elif all(13 <= value <= 15 for value in intervals):
        cadence = "biweekly"
        next_date = evidence[-1][0] + timedelta(days=14)
    elif all(27 <= value <= 33 for value in intervals):
        cadence = "monthly"
        next_date = _next_monthly(evidence[-1][0])
    elif all(13 <= value <= 18 for value in intervals):
        cadence = "semimonthly"
        next_date = _next_semimonthly(evidence[-1][0])
    if cadence is None or next_date is None:
        return None

    expected_interval = {
        "weekly": 7,
        "biweekly": 14,
        "semimonthly": 15,
        "monthly": round(median(intervals)),
    }[cadence]
    mean_deviation = sum(abs(value - expected_interval) for value in intervals) / len(
        intervals
    )
    confidence = max(0.55, min(0.95, 0.95 - mean_deviation * 0.08))
    return PaydayPattern(
        cadence=cadence,
        next_date=next_date,
        typical_amount=round(
            float(median(float(getattr(item, "amount")) for _day, item in evidence)),
            2,
        ),
        confidence=round(confidence, 2),
        evidence_ids=tuple(int(getattr(item, "id")) for _day, item in evidence),
    )
