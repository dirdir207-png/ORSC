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

    The paycheck is often NOT a single transfer: it arrives as multiple same-period
    chunks (e.g. Cash App's $500-per-transfer limit, or a PayPal->external->Crew
    route). So this:

    1. Collects positive income/transfer events from an income source (PayPal,
       Cash App, Capital One, Zelle — any recurring positive inflow).
    2. Bundles events within a ~4-day window into one "pay period" and SUMS them,
       so 2x $490.25 on adjacent days = one ~$980 pay.
    3. Averages those period totals over time (median + min/max range) so the
       forecast reflects what actually lands, not a single chunk.

    Returns {amount, min_amount, max_amount, cadence, cadence_interval,
    next_date, occurrences, sources, confidence}. None when no clear recurring
    income exists.
    """
    income = [t for t in transactions if _is_income(t)]
    if len(income) < _MIN_OCCURRENCES:
        return None

    # Identify the income source(s): group by merchant, keep merchants that look
    # like money movement (or any merchant with >=3 positive events).
    clusters: dict[str, list] = defaultdict(list)
    for txn in income:
        merchant = str(getattr(txn, "merchant", "") or getattr(txn, "description", "") or "").strip()
        clusters[merchant].append(txn)

    # Choose the best source: the one whose events form a recurring weekly pattern.
    best: tuple[str, list, list] | None = None
    for merchant, items in clusters.items():
        events = [_parse_date(x.occurred_at) for x in items]
        events = [e for e in events if e]
        if len(events) < _MIN_OCCURRENCES:
            continue
        if best is None or len(items) > len(best[1]):
            best = (merchant, items, events)

    if best is None:
        return None
    merchant, items, events = best

    # Bundle events that fall within a ~4-day window into a single pay period,
    # then SUM their amounts — the real per-paycheck figure.
    events.sort()
    periods: list[tuple[date, float]] = []
    for txn in items:
        ev_date = _parse_date(txn.occurred_at)
        if not ev_date:
            continue
        amount = abs(float(txn.amount))
        if periods and (ev_date - periods[-1][0]).days <= 4:
            # same pay period
            prev_date, prev_amount = periods[-1]
            periods[-1] = (prev_date, prev_amount + amount)
        else:
            periods.append((ev_date, amount))

    if len(periods) < _MIN_OCCURRENCES:
        return None
    period_totals = [round(total, 2) for _date, total in periods]
    period_dates = [d for d, _t in periods]
    # Exclude period totals that are absurdly small (partial windows) or huge.
    median_total = sorted(period_totals)[len(period_totals) // 2]
    if median_total <= 0 or median_total > _MAX_PAYCHECK_AMOUNT:
        return None
    # Cadence from median gap between pay periods.
    gaps = [(later - earlier).days for earlier, later in zip(period_dates, period_dates[1:])]
    if gaps and max(gaps) > _MAX_DAILY_RANGE_DAYS * 2:
        return None
    cadence, cadence_interval = _cadence_guess(gaps)
    next_date = period_dates[-1] + _period_delta(cadence, cadence_interval)
    return {
        "amount": median_total,
        "min_amount": min(period_totals),
        "max_amount": max(period_totals),
        "cadence": cadence,
        "cadence_interval": cadence_interval,
        "next_date": next_date.isoformat(),
        "occurrences": len(periods),
        "sources": [merchant],
        "source": merchant,
        "confidence": round(min(0.95, 0.5 + len(periods) * 0.1), 2),
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
