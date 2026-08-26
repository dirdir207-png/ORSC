import pytest

from crew.beacon import build_forecast


def test_declining_balances_project_negative_trajectory():
    values = [1000, 990, 975, 960, 950]  # ≈ -12.5/day over last 4 deltas
    forecast = build_forecast(values)
    assert forecast["available"] is True
    assert forecast["daily_burn"] < 0
    assert forecast["projected_end"] < forecast["current_balance"]
    assert 70 <= forecast["runway_days"] <= 85


def test_growing_balances_have_no_runway_limit():
    values = [500, 520, 540, 560]
    forecast = build_forecast(values)
    assert forecast["available"] is True
    assert forecast["daily_burn"] > 0
    assert forecast["runway_days"] is None
    assert forecast["projected_end"] > forecast["current_balance"]


@pytest.mark.parametrize("values", [[], [500], [500, 495]])
def test_insufficient_history_is_unavailable(values):
    forecast = build_forecast(values)
    assert forecast["available"] is False
    assert "reason" in forecast


def test_lookback_limits_extreme_old_data():
    values = [10_000] + [1000 - i for i in range(20)]  # ancient spike must not skew burn
    forecast = build_forecast(values, lookback_days=14)
    assert abs(forecast["daily_burn"]) < 100


def test_low_point_identified_within_horizon():
    values = [300, 290, 280, 270]
    forecast = build_forecast(values, horizon_days=30)
    assert forecast["low_point"]["day"] == 30
    assert forecast["low_point"]["amount"] == forecast["low_point"]["amount"]


def test_non_numeric_entries_are_ignored():
    forecast = build_forecast([1000, None, 980, "oops", 960])
    assert forecast["available"] is True
