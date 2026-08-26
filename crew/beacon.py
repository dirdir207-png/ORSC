"""Beacon: forward-looking budget projection from balance history.

V1 is deliberately simple and explainable: average daily burn over a recent
lookback window, projected across a horizon. No black boxes — every number in
the output can be derived by hand from the inputs.
"""

from typing import Any, Dict, List


def build_forecast(
    values: List[Any],
    horizon_days: int = 30,
    lookback_days: int = 14,
) -> Dict[str, Any]:
    points = [float(v) for v in (values or []) if isinstance(v, (int, float))]
    if len(points) < 3:
        return {
            "available": False,
            "reason": "Not enough balance history yet",
            "points": len(points),
        }

    recent = points[-int(lookback_days):]
    deltas = [recent[i + 1] - recent[i] for i in range(len(recent) - 1)]
    daily_burn = sum(deltas) / len(deltas)

    current_balance = round(points[-1], 2)
    projected_end = current_balance + daily_burn * horizon_days
    trajectory = [current_balance + daily_burn * d for d in range(horizon_days + 1)]

    runway_days = None
    if daily_burn < 0:
        runway_days = max(0, int(current_balance / -daily_burn)) if current_balance > 0 else 0

    low_amount = min(trajectory)
    return {
        "available": True,
        "current_balance": current_balance,
        "daily_burn": round(daily_burn, 2),
        "horizon_days": horizon_days,
        "projected_end": round(projected_end, 2),
        "runway_days": runway_days,
        "low_point": {
            "amount": round(low_amount, 2),
            "day": trajectory.index(low_amount),
        },
    }
