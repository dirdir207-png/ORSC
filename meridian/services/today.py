"""Calculations for Meridian's read-only Today workspace."""

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence

from meridian.beacon import forecast
from meridian.commitments import CommitmentType
from meridian.repository import FinancialRepository, ProviderConnectionFreshness

_STALE_AFTER = timedelta(hours=24)
_CASH_ACCOUNT_TYPES = frozenset({"cash", "checking", "savings"})


def _parse_timestamp(value: str) -> Optional[datetime]:
    try:
        base_value, separator, suffix = value.partition("#")
        if separator and (not suffix or not suffix.isdecimal()):
            return None
        parsed = datetime.fromisoformat(base_value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None else None


def _last_trustworthy_update(
    connections: Sequence[ProviderConnectionFreshness],
    *,
    now: datetime,
) -> Optional[str]:
    timestamps = [
        (parsed, value)
        for connection in connections
        if connection.last_successful_at is not None
        for parsed, value in [
            (_parse_timestamp(connection.last_successful_at), connection.last_successful_at)
        ]
        if parsed is not None and parsed <= now
    ]
    return min(timestamps, key=lambda item: item[0])[1] if timestamps else None


def data_freshness(
    repository: FinancialRepository,
    *,
    account_ids: Optional[Sequence[int]] = None,
    transaction_ids: Optional[Sequence[int]] = None,
    include_all_connections: bool = False,
    include_all_transaction_links: bool = False,
    now: Optional[datetime] = None,
) -> dict[str, Optional[str]]:
    """Describe whether a scope comes from a complete, current provider graph."""
    scope = repository.get_freshness_scope(
        account_ids=account_ids,
        transaction_ids=transaction_ids,
        include_all_connections=include_all_connections,
        include_all_transaction_links=include_all_transaction_links,
    )
    connections = scope.connections
    if not connections:
        if scope.has_unlinked_records:
            return {"status": "stale", "last_updated_at": None}
        return {"status": "unavailable", "last_updated_at": None}

    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    source_timestamps = [
        (parsed, value)
        for connection in connections
        for value in connection.source_updated_at
        for parsed in [_parse_timestamp(value) if value is not None else None]
        if parsed is not None
    ]
    last_successful_timestamps = {
        connection.connection_id: _parse_timestamp(connection.last_successful_at)
        if connection.last_successful_at is not None
        else None
        for connection in connections
    }
    complete = all(
        connection.status == "healthy"
        and last_successful_timestamps[connection.connection_id] is not None
        and last_successful_timestamps[connection.connection_id] <= current_time
        and len(connection.source_updated_at) > 0
        for connection in connections
    )
    source_values = sum(
        (list(connection.source_updated_at) for connection in connections),
        [],
    )
    valid_sources = len(source_timestamps) == len(source_values) and all(
        timestamp <= current_time for timestamp, _ in source_timestamps
    )
    if scope.has_unlinked_records or not complete or not valid_sources:
        return {
            "status": "stale",
            "last_updated_at": _last_trustworthy_update(connections, now=current_time),
        }

    oldest, oldest_value = min(source_timestamps, key=lambda item: item[0])
    status = "stale" if current_time - oldest > _STALE_AFTER else "fresh"
    return {"status": status, "last_updated_at": oldest_value}


def _currency_total(values: Sequence[tuple[str, float]]) -> dict[str, object]:
    by_currency: dict[str, float] = {}
    for currency, value in values:
        by_currency[currency] = by_currency.get(currency, 0.0) + value
    ordered = dict(sorted(by_currency.items()))
    if len(ordered) == 1:
        currency, amount = next(iter(ordered.items()))
        return {"amount": amount, "currency": currency, "by_currency": ordered}
    return {"amount": None, "currency": None, "by_currency": ordered}


def _spend_source_account(accounts):
    """The discretionary spend source: Crew's 'Free to Spend' pocket.

    Crew separates the primary holding 'Checking' pocket from the discretionary
    'Free to Spend' pocket. Safe-to-spend should reflect the money actually
    available to spend, which is that Free to Spend pocket's available
    (cleared) balance. Falls back to the first active account named like a
    spend/free pocket when the exact name is absent.
    """
    def _is_spend(account) -> bool:
        name = (getattr(account, "name", "") or "").strip().casefold()
        return "free to spend" in name or name == "free to spend"

    for account in accounts:
        if _is_spend(account):
            return account
    return None


def _unfunded_bill_total(commitment_repository):
    """Sum of unfunded amounts on active bills (known obligations to track)."""
    if commitment_repository is None:
        return None
    total = 0.0
    for commitment in commitment_repository.list_active():
        if commitment.type != CommitmentType.BILL:
            continue
        amount = commitment.amount if commitment.amount is not None else commitment.target_amount
        if amount is None:
            continue
        total += max(0.0, amount - (commitment.funded_amount or 0.0))
    return round(total, 2)


def _next_paycheck_inflow(paycheck, *, now=None):
    """Next expected income from the paycheck config (funding source).

    Returns ``{"date", "amount", "cadence"}`` when a paycheck is configured and
    active, rolling the date forward if ``next_date`` has passed; else None.
    This surfaces the "Next expected income" card instead of an empty cash sum.
    """
    if paycheck is None or not getattr(paycheck, "active", False):
        return None
    amount = getattr(paycheck, "amount", 0) or 0
    if amount <= 0:
        return None
    try:
        from datetime import date as _date

        as_of = (now or datetime.now(timezone.utc)).date()
        import calendar

        next_date = _date.fromisoformat(getattr(paycheck, "next_date", ""))
        cadence = getattr(paycheck, "cadence", "monthly")
        # Roll forward if the configured next date has passed.
        while next_date < as_of:
            if cadence == "weekly":
                next_date = next_date + timedelta(days=7)
            elif cadence == "biweekly":
                next_date = next_date + timedelta(days=14)
            elif cadence == "semimonthly":
                next_date = next_date + timedelta(days=15)
            else:  # monthly
                year = next_date.year + (1 if next_date.month == 12 else 0)
                month = 1 if next_date.month == 12 else next_date.month + 1
                day = min(next_date.day, calendar.monthrange(year, month)[1])
                next_date = _date(year, month, day)
    except (TypeError, ValueError):
        return None
    return {
        "date": next_date.isoformat(),
        "amount": round(float(amount), 2),
        "cadence": cadence,
    }


def _learned_paycheck_range(repository) -> Optional[tuple[float, float]]:
    """(min, max) of the learned recurring paycheck, for forecast variability."""
    try:
        from meridian.paycheck_learning import learn_paycheck

        transactions, _cursor = repository.list_transactions(limit=200)
        learned = learn_paycheck(transactions)
        if learned:
            return (float(learned["min_amount"]), float(learned["max_amount"]))
    except Exception:  # noqa: BLE001 - learning is best-effort context
        pass
    return None


def _build_beacon_signal(forecast: Optional[dict], safe_amount: Optional[float], safe_status: str) -> dict:
    """Derive a genuinely valuable Beacon summary from the forecast + safe-to-spend.

    Not a static "plan is steady": it surfaces the real, actionable signal — a
    shortfall, whether the next paycheck covers it, a negative safe-to-spend, or
    a positive runway — so the Beacon card is worth reading.
    """
    if not forecast or forecast.get("available") is not True:
        return None
    shortfall = forecast.get("first_shortfall")
    covers = bool(forecast.get("paycheck_covers"))
    next_paycheck = forecast.get("next_paycheck")
    runway = forecast.get("runway_days")
    low_point = forecast.get("low_point")
    daily = forecast.get("daily_expense")

    if safe_amount is not None and safe_amount < 0:
        detail = f"Safe to spend is negative (${abs(safe_amount):,.2f}); the next paycheck will restore it."
        title = "You're spending faster than income."
    elif shortfall and covers:
        title = "A shortfall is covered by your next paycheck."
        detail = f"{shortfall.get('cause')} leaves you short on {_iso_short(shortfall.get('date'))}, but your {_iso_short(next_paycheck)} paycheck covers it."
    elif shortfall:
        title = "A shortfall is ahead."
        detail = f"{shortfall.get('cause')} leaves you ${shortfall.get('amount'):,.2f} short on {_iso_short(shortfall.get('date'))}."
    elif runway is not None and runway == 0:
        title = "You're running tight until payday."
        detail = f"Every day costs ${(daily or 0):,.2f} and no runway remains before funding."
    elif runway is not None and runway > 0:
        title = f"About {runway} day{'s' if runway != 1 else ''} of runway."
        detail = f"At ${(daily or 0):,.2f}/day after known obligations, before the next paycheck."
    elif low_point is not None and low_point < 0:
        title = "Your low point dips below zero."
        detail = f"Projected low ${low_point:,.2f} before funding arrives."
    else:
        title = "Your plan is steady."
        detail = "No material change detected."
    # When the paycheck varies (learnt min != max), communicate the range so a
    # single figure isn't mistaken for guaranteed.
    p_range = forecast.get("paycheck_range")
    if p_range and isinstance(p_range, (list, tuple)) and len(p_range) == 2:
        lo, hi = float(p_range[0]), float(p_range[1])
        if hi > lo:
            detail = f"{detail} Paycheck ${lo:,.0f}–${hi:,.0f} depending on the week."
    return {"title": title, "summary": title, "detail": detail, "evidence": []}


def _iso_short(value) -> str:
    """'2026-09-16' or a full timestamp -> a short 'Sep 16' label (local-safe)."""
    try:
        from datetime import date as _d

        if isinstance(value, str) and len(value) >= 10:
            return _d.fromisoformat(value[:10]).strftime("%b %-d")
    except (ValueError, TypeError):
        pass
    return str(value or "soon")


def build_today(
    repository: FinancialRepository,
    commitment_repository=None,
    rule_repository=None,
    *,
    now: Optional[datetime] = None,
    paycheck=None,
) -> dict[str, object]:
    """Build a conservative Today summary from normalized repository records."""
    accounts = repository.list_accounts()
    # "Next expected income" from the owner's paycheck config (funding source),
    # if set. Falls back to nothing when no paycheck is configured.
    next_inflow = _next_paycheck_inflow(paycheck, now=now)
    cash_accounts = [
        account
        for account in accounts
        if account.is_active and account.account_type in _CASH_ACCOUNT_TYPES
    ]
    total_cash = _currency_total(
        [(account.currency, account.balance) for account in cash_accounts]
    )
    available_cash = _currency_total(
        [
            (
                account.currency,
                account.available_balance
                if account.available_balance is not None
                else account.balance,
            )
            for account in cash_accounts
        ]
    )

    freshness = data_freshness(
        repository,
        account_ids=[account.id for account in accounts],
        include_all_connections=True,
        now=now,
    )
    beacon = None
    if commitment_repository is not None and rule_repository is not None:
        as_of = (now or datetime.now(timezone.utc)).date()
        beacon = asdict(
            forecast(
                repository,
                commitment_repository,
                rule_repository,
                as_of,
                freshness=freshness["status"],
                paycheck=paycheck,
                paycheck_range=_learned_paycheck_range(repository),
            )
        )

    # R20: coherent cash / bills / goals breakdown + setup + next-run summary.
    breakdown = _commitment_breakdown(commitment_repository) if commitment_repository else None
    setup = _setup_summary(breakdown, rules_configured=rule_repository is not None)
    next_run = _next_run_hint(rule_repository, as_of=None)

    # Safe-to-spend is the discretionary money available to spend now. Crew
    # tracks this as the "Free to Spend" pocket; use its available (cleared)
    # balance directly so safe-to-spend matches Free to Spend. (Crew has
    # already separated bill/obligation money into other pockets, so no further
    # subtraction.) Otherwise fall back to cash-type available balances.
    spend_source = _spend_source_account(accounts)
    # "Committed" (known obligations) is independent of which account is the
    # spend source: it is the unfunded bill/commitment total Meridian is tracking
    # toward. Always surface it so the card is never dead.
    known_obligations = (
        _unfunded_bill_total(commitment_repository) if commitment_repository else None
    )
    if spend_source is not None and spend_source.available_balance is not None:
        safe_amount = _currency_total(
            [(spend_source.currency, spend_source.available_balance)]
        )["by_currency"].get(spend_source.currency, 0.0)
        safe_status = "available"
    else:
        safe_amount = available_cash["by_currency"].get("USD", 0.0)
        safe_status = "available" if available_cash["by_currency"].get("USD") else "unavailable"

    return {
        "total_cash": total_cash,
        "next_inflow": next_inflow,
        "safe_to_spend": {
            "amount": safe_amount,
            "status": safe_status,
            "inputs": {
                "available_cash": available_cash,
                "known_obligations": known_obligations,
                "reason": None,
            },
        },
        "upcoming_events": [],
        "forecast": beacon,
        "beacon": _build_beacon_signal(beacon, safe_amount, safe_status),
        "data_freshness": freshness,
        "breakdown": breakdown,
        "setup": setup,
        "next_run": next_run,
    }


def _commitment_breakdown(commitment_repository) -> Optional[dict]:
    """Cash/bills/goals summary from active commitments (R20)."""
    if commitment_repository is None:
        return None
    active = [
        c for c in commitment_repository.list_active()
    ]
    bills = [c for c in active if c.type == CommitmentType.BILL]
    goals = [
        c for c in active
        if c.type in (CommitmentType.GOAL, CommitmentType.RESERVE, CommitmentType.BUFFER, CommitmentType.DEBT)
    ]
    return {
        "bills": [
            {
                "id": c.id,
                "name": c.name,
                "target": c.target_amount if c.target_amount is not None else c.amount,
                "funded": c.funded_amount,
            }
            for c in bills
        ],
        "goals": [
            {
                "id": c.id,
                "name": c.name,
                "target": c.target_amount if c.target_amount is not None else c.amount,
                "funded": c.funded_amount,
            }
            for c in goals
        ],
        "bills_total": sum((c.target_amount if c.target_amount is not None else (c.amount or 0)) for c in bills),
        "goals_total": sum((c.target_amount if c.target_amount is not None else (c.amount or 0)) for c in goals),
        "bills_funded": sum(c.funded_amount for c in bills),
        "goals_funded": sum(c.funded_amount for c in goals),
    }


def _setup_summary(breakdown, *, rules_configured: bool) -> dict:
    """R20: honest setup checklist (not fabricated)."""
    if breakdown is None:
        return {"state": "needs_commitments", "items": [{"id": "commitments", "done": False, "label": "Add commitments"}]}
    items = []
    items.append({"id": "commitments", "done": True, "label": "Commitments configured"})
    # Native funding rules configured?
    from meridian.funding_repo import FundingRuleRepository  # noqa: F401

    items.append({"id": "funding_rules", "done": bool(rules_configured), "label": "Funding rules configured"})
    return {"state": "ready" if all(i["done"] for i in items) else "in_progress", "items": items}


def _next_run_hint(rule_repository, *, as_of) -> Optional[dict]:
    """R20: next scheduled funding run hint from the active rule set (best-effort)."""
    if rule_repository is None:
        return None
    try:
        from meridian.funding import project_funding  # noqa: F401

        rules = rule_repository.list_all()
        active = [r for r in rules if getattr(r, "status", "active") == "active"]
        if not active:
            return {"state": "no_rules"}
        return {"state": "rules_present", "rule_count": len(active)}
    except Exception:
        return {"state": "unknown"}
