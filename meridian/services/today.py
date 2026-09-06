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


def build_today(
    repository: FinancialRepository,
    commitment_repository=None,
    rule_repository=None,
    *,
    now: Optional[datetime] = None,
) -> dict[str, object]:
    """Build a conservative Today summary from normalized repository records."""
    accounts = repository.list_accounts()
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
            )
        )

    # R20: coherent cash / bills / goals breakdown + setup + next-run summary.
    breakdown = _commitment_breakdown(commitment_repository) if commitment_repository else None
    setup = _setup_summary(breakdown, rules_configured=rule_repository is not None)
    next_run = _next_run_hint(rule_repository, as_of=None)
    return {
        "total_cash": total_cash,
        "safe_to_spend": {
            "amount": None,
            "status": "unavailable",
            "inputs": {
                "available_cash": available_cash,
                "known_obligations": None,
                "reason": "Commitments are not yet available in the normalized graph.",
            },
        },
        "upcoming_events": [],
        "forecast": beacon,
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
