"""Self-learning paycheck detection over real income transactions.

The owner's paycheck isn't necessarily a clean "direct deposit" — it can land as
a Cash App transfer, or be routed through PayPal and moved in. Rather than rely
on a fixed manual amount that goes stale, learn the real source from the recent
transaction graph: cluster positive (income/transfer) transactions by merchant +
amount, take the dominant recurring cluster, and derive its typical amount,
variability, and cadence. This feeds the forecast/beacon with what actually
happens (and a range for the uncertainty), and can auto-update over time.

Never guesses when there is no clear recurring income: returns None so the
app keeps the owner's explicit config (or no paycheck).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Optional

# The recurring cluster must appear at least this many times / span this many
# weeks to be trusted as a paycheck rather than a one-off transfer.
_MIN_OCCURRENCES = 3
_MAX_DAILY_RANGE_DAYS = 40  # max gap between paychecks to count as recurring
_MAX_PAYCHECK_AMOUNT = 10_000.0  # sanity guard; ignore absurd outliers


def _parse_date(value) -> Optional[date]:
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except Exception:  # noqa: BLE001 - unknown date form
        return None


def _is_income(txn) -> bool:
    """A positive amount that isn't a reimbursement / tiny fee / refund."""
    amount = float(getattr(txn, "amount", 0) or 0)
    if amount <= 0:
        return False
    kind = str(getattr(txn, "classification_kind", "") or "").lower()
    if kind in {"reimbursement", "fee", "refund"}:
        return False
    if amount < 50.0:  # ignore grocery refunds / tag-along credits
        return False
    return True


def _cadence_guess(offsets: list[int]) -> tuple[str, int]:
    """Guess cadence from the common gap between deposit dates."""
    if not offsets:
        return "monthly", 1
    avg = sum(offsets) / len(offsets)
    if avg <= 9:
        return "weekly", 1
    if avg <= 16:
        return "biweekly", 1
    if avg <= 21:
        return "semimonthly", 1
    return "monthly", 1


def learn_paycheck(transactions) -> dict | None:
    """Return a learned paycheck dict, or None if no clear recurring income.

    Returns {amount, min_amount, max_amount, cadence, cadence_interval,
    next_date, occurrences, confidence}. ``amount`` is the median typical
    amount; min/max capture variability so the forecast can show a range.
    """
    income = [t for t in transactions if _is_income(t)]
    if len(income) < _MIN_OCCURRENCES:
        return None
    # Cluster by source merchant (not exact amount) so a variable paycheck from
    # the same source groups together; the median amount filters outliers.
    clusters: dict[str, list] = defaultdict(list)
    for txn in income:
        merchant = str(getattr(txn, "merchant", "") or getattr(txn, "description", "") or "").strip()
        clusters[merchant].append(txn)

    best: tuple[str, list, list] | None = None
    for merchant, items in clusters.items():
        if len(items) < _MIN_OCCURRENCES:
            continue
        amounts = [round(abs(float(x.amount)), 2) for x in items]
        median = sorted(amounts)[len(amounts) // 2]
        if median > _MAX_PAYCHECK_AMOUNT:
            continue
        # Keep transactions within ~30% of the median to drop stray one-offs.
        band = [x for x, a in zip(items, amounts) if a >= median * 0.7 and a <= median * 1.3]
        if len(band) < _MIN_OCCURRENCES:
            continue
        dates = sorted(d for d in (_parse_date(x.occurred_at) for x in band) if d)
        if len(dates) < _MIN_OCCURRENCES:
            continue
        if best is None or len(band) > len(best[1]):
            best = (merchant, band, dates)

    if best is None:
        return None
    merchant, items, dates = best
    # Collapse dates that sit within ~2 days of each other (Cash App can record
    # a transfer + a split on the same payday) so the cadence reflects the real
    # weekly/biweekly period, not intra-day pairs.
    collapsed: list[date] = []
    for d in dates:
        if collapsed and (d - collapsed[-1]).days <= 2:
            # same payday group; keep the later date as the payday
            collapsed[-1] = d
        else:
            collapsed.append(d)
    dates = collapsed
    # Cadence from median gap between consecutive deposit dates.
    gaps = [(later - earlier).days for earlier, later in zip(dates, dates[1:])]
    if gaps and max(gaps) > _MAX_DAILY_RANGE_DAYS * 2:
        # Too irregular; treat as one-off, not a paycheck.
        return None
    cadence, cadence_interval = _cadence_guess(gaps)
    all_amounts = [round(abs(float(x.amount)), 2) for x in items]
    median_amount = sorted(all_amounts)[len(all_amounts) // 2]
    # Next expected deposit: last date + one cadence period.
    next_date = dates[-1] + _period_delta(cadence, cadence_interval)
    return {
        "amount": median_amount,
        "min_amount": min(all_amounts),
        "max_amount": max(all_amounts),
        "cadence": cadence,
        "cadence_interval": cadence_interval,
        "next_date": next_date.isoformat(),
        "occurrences": len(items),
        "source": merchant,
        "confidence": round(min(0.95, 0.5 + len(items) * 0.1), 2),
    }


def _period_delta(cadence: str, interval: int) -> timedelta:
    if cadence == "weekly":
        return timedelta(days=7 * interval)
    if cadence == "biweekly":
        return timedelta(days=14 * interval)
    if cadence == "semimonthly":
        return timedelta(days=15 * interval)
    # monthly
    import calendar

    anchor = date.today()
    year = anchor.year + (1 if anchor.month == 12 else 0)
    month = 1 if anchor.month == 12 else anchor.month + 1
    day = min(anchor.day, calendar.monthrange(year, month)[1])
    return date(year, month, day) - anchor
