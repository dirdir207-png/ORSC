"""Pure comparisons over an existing deterministic Meridian forecast."""

from dataclasses import dataclass, replace
from datetime import timedelta
from math import floor


@dataclass(frozen=True)
class ScenarioResult:
    base: object
    scenario: object
    comparison: dict[str, float | int | None]
    assumptions: tuple[str, ...]


def run_scenario(base, changes) -> ScenarioResult:
    income = float(changes.get("income", 0) or 0)
    reserve = float(changes.get("reserve", 0) or 0)
    contribution = float(changes.get("contribution", 0) or 0)
    expense_change = float(changes.get("expense_change", 0) or 0)
    due_date_days = int(changes.get("due_date_days", 0) or 0)
    starting_cash = base.starting_cash + income - reserve - contribution
    daily_expense = max(0, base.daily_expense + expense_change)
    runway_days = floor(starting_cash / daily_expense) if daily_expense > 0 else None
    low_point_date = (
        base.low_point_date + timedelta(days=due_date_days)
        if base.low_point_date is not None
        else None
    )
    scenario = replace(
        base,
        starting_cash=round(starting_cash, 2),
        daily_expense=round(daily_expense, 2),
        runway_days=runway_days,
        low_point=(
            round(
                base.low_point + income - reserve - contribution - expense_change * 30,
                2,
            )
            if base.low_point is not None
            else None
        ),
        low_point_date=low_point_date,
    )
    assumptions = []
    if income:
        assumptions.append(f"income changes by ${income:.2f}")
    if expense_change:
        assumptions.append(f"daily expenses change by ${expense_change:.2f}")
    if reserve:
        assumptions.append(f"${reserve:.2f} held as reserve")
    if contribution:
        assumptions.append(f"${contribution:.2f} contribution")
    if due_date_days:
        assumptions.append(f"due date shifted by {due_date_days} days")
    for context in changes.get("context_assumptions", ()) or ():
        if context.range_min is not None and context.range_max is not None:
            range_label = f" (${context.range_min:.2f}–${context.range_max:.2f})"
        else:
            range_label = ""
        assumptions.append(f"assumption: {context.explanation}{range_label}")
    return ScenarioResult(
        base=base,
        scenario=scenario,
        comparison={
            "starting_cash": round(scenario.starting_cash - base.starting_cash, 2),
            "daily_expense": round(scenario.daily_expense - base.daily_expense, 2),
            "runway_days": (
                scenario.runway_days - base.runway_days
                if scenario.runway_days is not None and base.runway_days is not None
                else None
            ),
            "low_point": (
                round(scenario.low_point - base.low_point, 2)
                if scenario.low_point is not None and base.low_point is not None
                else None
            ),
        },
        assumptions=tuple(assumptions),
    )
