"""Write-through reconciliation helpers for confirmed Crew mutations."""

from __future__ import annotations

from collections.abc import Callable


def reconcile_crew_mutation(
    result: dict[str, object], refresh: Callable[[], object]
) -> dict[str, object]:
    """Attach one read-back status to a confirmed Crew mutation.

    The mutation itself is never retried. A successful Crew write whose
    subsequent normalized read fails remains successful but explicitly needs
    verification before Meridian presents current financial state.
    """
    if not result.get("success"):
        return result
    transfer = result.get("result")
    transfer_id = transfer.get("id") if isinstance(transfer, dict) else None
    if not isinstance(transfer_id, str) or not transfer_id.strip():
        return result
    try:
        report = refresh()
    except Exception:
        result["reconciliation"] = {
            "state": "pending_reconciliation",
            "transfer_id": transfer_id,
            "verify_state": True,
        }
        return result
    status = getattr(report, "status", None)
    if status is None and isinstance(report, dict):
        status = report.get("status")
    if status != "complete":
        result["reconciliation"] = {
            "state": "pending_reconciliation",
            "transfer_id": transfer_id,
            "verify_state": True,
        }
        return result
    accounts_synced = getattr(report, "accounts_synced", None)
    transactions_synced = getattr(report, "transactions_synced", None)
    if isinstance(report, dict):
        accounts_synced = report.get("accounts_synced")
        transactions_synced = report.get("transactions_synced")
    result["reconciliation"] = {
        "state": "reconciled",
        "transfer_id": transfer_id,
        "accounts_synced": accounts_synced,
        "transactions_synced": transactions_synced,
    }
    return result
