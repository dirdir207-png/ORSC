"""Explainable deterministic cash runway forecasts for Meridian."""

from dataclasses import dataclass
from datetime import date, timedelta
from math import floor


@dataclass(frozen=True)
class ForecastFactor:
    kind: str
    amount: float
    date: date | None
    explanation: str
    evidence_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class ForecastShortfall:
    date: date
    amount: float
    cause: str


@dataclass(frozen=True)
class Forecast:
    available: bool
    reason: str | None
    as_of: date
    starting_cash: float
    daily_expense: float
    daily_expense_range: tuple[float, float]
    runway_days: int | None
    low_point: float | None
    low_point_date: date | None
    first_shortfall: ForecastShortfall | None
    coverage_horizons: dict[str, float]
    factors: tuple[ForecastFactor, ...]
    confidence: float
    freshness: str


def _commitment_amount(commitment) -> float:
    kind = getattr(getattr(commitment, "type", None), "value", getattr(commitment, "type", None))
    if kind == "bill":
        target = getattr(commitment, "amount", 0) or 0
    elif kind == "buffer":
        target = getattr(commitment, "buffer_minimum", 0) or 0
    else:
        target = getattr(commitment, "target_amount", 0) or 0
    return max(0.0, float(target) - float(getattr(commitment, "funded_amount", 0) or 0))


def _date(value) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def forecast(graph, commitments, rules, as_of: date, *, freshness: str = "fresh") -> Forecast:
    del rules
    accounts = graph.list_accounts()
    starting_cash = sum(
        float(account.balance)
        for account in accounts
        if account.is_active and account.account_type in {"cash", "checking", "savings"}
    )
    transactions, _ = graph.list_transactions(limit=200)
    expenses = [
        (abs(float(item.amount)), item)
        for item in transactions
        if item.amount < 0 and getattr(item, "classification_kind", "spend") not in {"transfer", "refund"}
    ]
    if not expenses:
        return Forecast(
            False,
            "transaction history unavailable",
            as_of,
            starting_cash,
            0,
            (0, 0),
            None,
            None,
            None,
            None,
            {},
            (),
            0,
            freshness,
        )
    daily_expense = sum(amount for amount, _item in expenses) / len(expenses)
    due_items = []
    factors = [
        ForecastFactor(
            "historical_expense",
            daily_expense,
            None,
            f"average of {len(expenses)} classified spending transactions",
            tuple(item.id for _amount, item in expenses),
        )
    ]
    for commitment in commitments.list_active():
        due = _date(getattr(commitment, "due_date", None) or getattr(commitment, "target_date", None))
        amount = _commitment_amount(commitment)
        if due and due >= as_of and amount > 0:
            due_items.append((due, amount, commitment.name))
            factors.append(
                ForecastFactor(
                    "commitment",
                    amount,
                    due,
                    f"{commitment.name} is due on {due.isoformat()}",
                    (commitment.id,),
                )
            )
    known_obligations = sum(amount for _due, amount, _name in due_items)
    runway_days = max(0, floor(max(0, starting_cash - known_obligations) / daily_expense))
    balance = starting_cash
    low_point = balance
    low_point_date = as_of
    first_shortfall = None
    due_by_date = {}
    for due, amount, name in due_items:
        due_by_date.setdefault(due, []).append((amount, name))
    coverage = {}
    for offset in range(1, 91):
        current = as_of + timedelta(days=offset)
        balance -= daily_expense
        for amount, name in due_by_date.get(current, ()):
            balance -= amount
            if balance < 0 and first_shortfall is None:
                first_shortfall = ForecastShortfall(current, round(abs(balance), 2), name)
        if balance < low_point:
            low_point = balance
            low_point_date = current
        if offset in {7, 14, 30, 60, 90}:
            coverage[f"{offset}d"] = round(balance, 2)
    if first_shortfall is not None:
        low_point_date = first_shortfall.date
    sample_confidence = min(0.9, 0.35 + len(expenses) * 0.05)
    confidence = sample_confidence * (0.65 if freshness != "fresh" else 1.0)
    amounts = [amount for amount, _item in expenses]
    return Forecast(
        True,
        None,
        as_of,
        round(starting_cash, 2),
        round(daily_expense, 2),
        (round(min(amounts), 2), round(max(amounts), 2)),
        runway_days,
        round(low_point, 2),
        low_point_date,
        first_shortfall,
        coverage,
        tuple(factors),
        round(confidence, 2),
        freshness,
    )
