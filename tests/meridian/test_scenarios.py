from datetime import date

from meridian.beacon import Forecast
from meridian.context import Assumption
from meridian.scenarios import run_scenario


def _base():
    return Forecast(
        available=True,
        reason=None,
        as_of=date(2026, 9, 1),
        starting_cash=1000,
        daily_expense=20,
        daily_expense_range=(15, 25),
        runway_days=50,
        low_point=400,
        low_point_date=date(2026, 10, 1),
        first_shortfall=None,
        coverage_horizons={"30d": 400},
        factors=(),
        confidence=0.8,
        freshness="fresh",
    )


def test_scenario_is_pure_and_compares_income_expense_reserve_changes():
    base = _base()

    result = run_scenario(
        base,
        {"income": 200, "expense_change": -5, "reserve": 100, "contribution": 50},
    )

    assert result.base is base
    assert result.scenario.starting_cash == 1050
    assert result.scenario.daily_expense == 15
    assert result.scenario.runway_days == 70
    assert result.comparison["runway_days"] == 20
    assert base == _base()


def test_scenario_due_date_change_is_explained_without_persisting():
    base = _base()

    result = run_scenario(base, {"due_date_days": 14})

    assert result.assumptions == ("due date shifted by 14 days",)
    assert result.scenario.low_point_date == date(2026, 10, 15)


def test_confirmed_context_range_is_labeled_as_assumption_not_fact():
    context = Assumption(
        kind="travel_pressure",
        source_ids=("calendar:trip-1",),
        confidence=0.7,
        range_min=100,
        range_max=300,
        confirmation_state="confirmed",
        explanation="Confirmed travel range.",
    )

    result = run_scenario(_base(), {"context_assumptions": [context]})

    assert "assumption: Confirmed travel range. ($100.00–$300.00)" in result.assumptions
    assert result.scenario == _base()
