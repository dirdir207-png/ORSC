"""One canonical Plan view model: summary, timeline, allocation, commitments."""

from dataclasses import asdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional, Sequence

from meridian.beacon import forecast
from meridian.funding import project_funding
from meridian.funding_repo import FundingRuleRepository

_HORIZON_DAYS = 30
_ZERO = Decimal("0")


def _money(value) -> Decimal:
    return Decimal(str(value)) if value is not None else _ZERO


def _biller_status(commitment, *, last_paid=None) -> str:
    """Subtle per-bill badge for the Plan card (R33). Lazy import avoids a
    module cycle with meridian.billers (which imports commitments + models)."""
    from meridian.billers import bill_status_for

    return bill_status_for(commitment, last_paid_amount=last_paid)


def _project_commitment(commitment, rules, cash_events, as_of: date):
    projections = []
    for rule in rules:
        if rule.paused:
            continue
        deadline = None
        for candidate in (
            getattr(commitment, "due_date", None),
            getattr(commitment, "target_date", None),
        ):
            if isinstance(candidate, str) and candidate:
                try:
                    deadline = date.fromisoformat(candidate)
                except ValueError:
                    deadline = None
            elif isinstance(candidate, date):
                deadline = candidate
        horizon_end = rule.horizon_end or (as_of + timedelta(days=_HORIZON_DAYS))
        if deadline and deadline < horizon_end:
            horizon_end = deadline
        projection = project_funding(
            rule,
            commitment,
            cash_events,
            as_of=as_of,
        )
        projections.append((rule, projection))
    return projections


def build_plan(
    graph_repository,
    commitment_repository,
    rule_repository: FundingRuleRepository,
    *,
    as_of: date,
    cash_events: Optional[Sequence[tuple[date, Decimal]]] = None,
    last_paid_by_id: Optional[dict[int, Optional[float]]] = None,
    paycheck=None,
) -> dict:
    """Compose the canonical Plan view model from local planning data.

    Cash events default to the graph's current cash balances treated as a
    single event today (plus future paycheck inflows when a paycheck config is
    supplied); callers with richer timelines may pass them.
    """
    if cash_events is None:
        cash_events = _cash_events_from_graph(graph_repository, as_of, paycheck)

    accounts = {account.id: account for account in graph_repository.list_accounts()}
    commitments = commitment_repository.list_active()
    horizon_end = as_of + timedelta(days=_HORIZON_DAYS)

    commitment_views = []
    timeline_events = []
    shortfalls = []
    total_target = _ZERO
    total_funded = _ZERO
    next_due = None

    for commitment in commitments:
        commitment_type = commitment.type.value
        target = _commitment_target(commitment)
        funded = _money(commitment.funded_amount)
        total_target += target if commitment_type != "buffer" else _ZERO
        total_funded += min(funded, target) if commitment_type != "buffer" else _ZERO

        rules = rule_repository.list_for_commitment(commitment.id)
        projections = _project_commitment(commitment, rules, cash_events, as_of)
        projected_total = sum(
            (projection.total for _rule, projection in projections), _ZERO
        )

        due_date = _date_of(getattr(commitment, "due_date", None))
        target_date = _date_of(getattr(commitment, "target_date", None))
        # Recurring bill anchors that have passed are rolled to the next
        # occurrence so the surfaced due date is a real future date.
        due_date = _next_occurrence(due_date, getattr(commitment, "recurrence", "") or "", as_of)
        if due_date and (next_due is None or due_date < next_due):
            next_due = due_date

        for rule, projection in projections:
            for event in projection.events:
                if event.amount <= _ZERO or not (as_of <= event.date <= horizon_end):
                    continue
                timeline_events.append(
                    {
                        "date": event.date.isoformat(),
                        "amount": float(event.amount),
                        "commitment": commitment.name,
                        "commitment_id": commitment.id,
                        "rule_id": rule.id,
                        "source": event.source,
                        "explanation": list(event.explanation),
                    }
                )
            for event in projection.events:
                deficit = event.desired_amount - event.amount
                if deficit > _ZERO:
                    shortfalls.append(
                        {
                            "date": event.date.isoformat(),
                            "amount": float(deficit),
                            "cause": (
                                f"{commitment.name} wanted ${event.desired_amount} but only "
                                f"${event.amount} of cash was available"
                            ),
                            "commitment_id": commitment.id,
                        }
                    )

        backing = None
        backing_id = getattr(commitment, "backing_account_id", None)
        if backing_id is not None and backing_id in accounts:
            backing = {
                "account_id": backing_id,
                "name": accounts[backing_id].name,
            }

        commitment_views.append(
            {
                "id": commitment.id,
                "type": commitment_type,
                "name": commitment.name,
                "status": commitment.status.value,
                "priority": commitment.priority,
                "target": float(target),
                "funded": float(min(funded, target)) if commitment_type != "buffer" else float(funded),
                "unfunded": float(max(_ZERO, target - funded)),
                "due_date": due_date.isoformat() if due_date else None,
                "target_date": target_date.isoformat() if target_date else None,
                "backing": backing,
                "rule_ids": [str(rule.id) for rule in rules],
                "projected_30d": float(projected_total),
                "explanation": _coverage_explanation(target, funded, projected_total),
                # Live Crew bills expose the Crew bill id so the UI can offer a
                # proposal-gated write-back (update_crew_bill). Absent for local
                # planning records.
                "crew_bill_id": (
                    getattr(commitment, "legacy_id", None)
                    if getattr(commitment, "legacy_source", None) == "crew"
                    else None
                ),
                # R33: subtle per-bill badge (underfunded / due_soon / changed)
                # shown on the existing Plan card — no separate "monitor" page.
                # "changed" needs the last-paid charge, passed via last_paid_by_id.
                "biller_status": _biller_status(
                    commitment,
                    last_paid=(last_paid_by_id or {}).get(commitment.id),
                ),
            }
        )

    timeline_events.sort(key=lambda item: (item["date"], item["commitment"]))
    shortfalls.sort(key=lambda item: (item["date"], -item["amount"]))
    first_shortfall = shortfalls[0] if shortfalls else None

    cash_total = sum(
        (
            _money(account.balance)
            for account in accounts.values()
            if account.is_active and account.account_type in ("cash", "checking", "savings")
        ),
        _ZERO,
    )
    committed = sum(
        (
            min(_money(view["funded"]), _money(view["target"]))
            for view in commitment_views
            if view["type"] != "buffer"
        ),
        _ZERO,
    )
    unfunded = max(_ZERO, total_target - total_funded)
    available = max(_ZERO, cash_total - committed - unfunded)

    coverage_ratio = float(min(_money("1"), total_funded / total_target)) if total_target > _ZERO else 0.0
    if commitments:
        headline = (
            f"{len(commitments)} commitments, "
            f"{int(coverage_ratio * 100)}% funded"
        )
    else:
        headline = "No commitments yet — add one to start planning"

    freshness = _graph_freshness(graph_repository)
    beacon = forecast(
        graph_repository,
        commitment_repository,
        rule_repository,
        as_of,
        freshness=freshness["status"],
    )
    return {
        "summary": {
            "headline": headline,
            "commitment_count": len(commitments),
            "total_target": float(total_target),
            "total_funded": float(total_funded),
            "unfunded": float(unfunded),
            "coverage_ratio": coverage_ratio,
            "next_due": next_due.isoformat() if next_due else None,
            "first_shortfall": first_shortfall,
        },
        "commitments": commitment_views,
        "timeline": {
            "start": as_of.isoformat(),
            "end": horizon_end.isoformat(),
            "events": timeline_events,
        },
        "allocation": {
            "cash_total": float(cash_total),
            "segments": [
                {"label": "Committed to commitments", "amount": float(committed)},
                {"label": "Unfunded commitments", "amount": float(unfunded)},
                {"label": "Available", "amount": float(available)},
            ],
        },
        "forecast": asdict(beacon),
        "data_freshness": freshness,
        "next_paycheck": _next_paycheck_event(paycheck, as_of),
    }


def _next_paycheck_event(paycheck, as_of):
    """Next paycheck inflow from the owner's config (date + amount).

    Surfaced directly so the Funding Schedule card is meaningful even when no
    funding rules (and therefore no projected timeline events) exist.
    """
    if paycheck is None or not getattr(paycheck, "active", False):
        return None
    amount = getattr(paycheck, "amount", 0) or 0
    next_date = getattr(paycheck, "next_date", "") or ""
    cadence = getattr(paycheck, "cadence", "monthly")
    if amount <= 0 or not next_date:
        return None
    try:
        import calendar

        anchor = date.fromisoformat(next_date)
        while anchor < as_of:
            if cadence == "weekly":
                anchor = anchor + timedelta(days=7)
            elif cadence == "biweekly":
                anchor = anchor + timedelta(days=14)
            elif cadence == "semimonthly":
                anchor = anchor + timedelta(days=15)
            else:
                year = anchor.year + (1 if anchor.month == 12 else 0)
                month = 1 if anchor.month == 12 else anchor.month + 1
                day = min(anchor.day, calendar.monthrange(year, month)[1])
                anchor = date(year, month, day)
    except (TypeError, ValueError):
        return None
    return {"date": anchor.isoformat(), "amount": round(float(amount), 2), "cadence": cadence}


def _coverage_explanation(target: Decimal, funded: Decimal, projected: Decimal) -> list[str]:
    factors = []
    if funded > _ZERO:
        factors.append(f"${funded} already set aside")
    if projected > _ZERO:
        factors.append(f"${projected} projected from funding rules in the next 30 days")
    remaining = max(_ZERO, target - funded - projected)
    if target > _ZERO and remaining > _ZERO:
        factors.append(f"${remaining} still needs a plan")
    if not factors:
        factors.append("No funding activity yet")
    return factors


def _commitment_target(commitment) -> Decimal:
    commitment_type = commitment.type.value
    if commitment_type == "bill":
        return _money(commitment.amount)
    if commitment_type == "buffer":
        return _money(commitment.buffer_minimum)
    return _money(commitment.target_amount)


def _date_of(value) -> Optional[date]:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def _next_occurrence(anchor: date, recurrence: str, as_of: date) -> date:
    """Roll a recurring bill's anchor date forward to the next occurrence.

    Crew's ``anchorDate`` is the original anchor of a recurring bill (e.g.
    2026-01-16). Storing it verbatim surfaces a past date as the bill's due date.
    For a recurring bill whose anchor has passed, advance it by its cadence until
    it is >= as_of so the "next due" is a real future date. Non-recurring (or
    unknown) bills keep their anchor unchanged.
    """
    rec = (recurrence or "").lower()
    anchor = anchor if isinstance(anchor, date) else _date_of(str(anchor)) if anchor else None
    if anchor is None:
        return None
    if rec not in ("weekly", "biweekly", "monthly", "semimonthly"):
        return anchor
    import calendar

    candidate = anchor
    while candidate < as_of:
        if rec == "weekly":
            candidate = candidate + timedelta(days=7)
        elif rec == "biweekly":
            candidate = candidate + timedelta(days=14)
        elif rec == "semimonthly":
            candidate = candidate + timedelta(days=15)
        else:  # monthly
            year = candidate.year + (1 if candidate.month == 12 else 0)
            month = 1 if candidate.month == 12 else candidate.month + 1
            day = min(candidate.day, calendar.monthrange(year, month)[1])
            candidate = date(year, month, day)
    return candidate


def _cash_events_from_graph(graph_repository, as_of: date, paycheck=None) -> list[tuple[date, Decimal]]:
    from decimal import Decimal

    total = sum(
        (
            _money(account.balance)
            for account in graph_repository.list_accounts()
            if account.is_active and account.account_type in ("cash", "checking", "savings")
        ),
        _ZERO,
    )
    if paycheck is not None:
        from meridian.paycheck import build_cash_events

        events = build_cash_events(float(total), paycheck, as_of=as_of)
        return [(date, Decimal(str(amount))) for date, amount in events]
    return [(as_of, total)] if total > _ZERO else []


def _graph_freshness(graph_repository) -> dict:
    from meridian.services.today import data_freshness

    return data_freshness(graph_repository, include_all_connections=True)
