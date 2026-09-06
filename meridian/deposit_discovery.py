"""R24: deposit discovery over the canonical transaction graph.

Searches normalized transaction records across explicitly connected accounts
for income-deposit patterns and proposes FundingSource matches with
provenance + confidence. Owned-account transfers are funding events, not new
household income. A proposal NEVER auto-creates a source — it is a candidate
for owner confirmation (proposal-only boundary).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class DepositCandidate:
    source_name: str
    account_external_id: str
    amount_cents: float
    occurred_at: date
    transaction_external_id: str
    confidence: float
    reason: str
    kind: str  # "recurring_income" | "transfer" | "unknown"
    evidence_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class DepositDiscovery:
    candidates: tuple[DepositCandidate, ...]
    account_whitelist: tuple[str, ...]
    note: str


_INCOME_DESCRIPTIONS = ("direct deposit", "payroll", "salary", "paycheck", "deposit")
_TRANSFER_DESCRIPTIONS = ("transfer", "internal", "move money")


def _confidence_from_description(description: str) -> float:
    low = description.lower()
    if any(k in low for k in ("direct deposit", "payroll", "salary", "paycheck")):
        return 0.95
    if any(k in low for k in ("deposit", "incoming")):
        return 0.75
    if any(k in low for k in _TRANSFER_DESCRIPTIONS):
        return 0.30  # owned transfer — low income confidence
    return 0.45


def discover_deposits(
    transactions: tuple[dict, ...],
    *,
    connected_account_ids: tuple[str, ...],
    min_amount_cents: float = 0,
) -> DepositDiscovery:
    """Scan normalized transaction records and propose deposit matches.

    ``transactions`` items: {external_id, account_external_id, amount, occurred_at,
    description, merchant, category, evidence_ids?}. Only connected accounts are
    searched; no source is auto-created.
    """
    whitelist = tuple(connected_account_ids)
    candidates: list[DepositCandidate] = []
    for txn in transactions:
        acct = str(txn.get("account_external_id") or "")
        if acct not in whitelist:
            continue
        amount = float(txn.get("amount") or 0)
        if amount <= min_amount_cents:
            continue  # debits / zero are not deposit candidates
        description = str(txn.get("description") or txn.get("merchant") or "")
        conf = _confidence_from_description(description)
        kind = "recurring_income" if conf >= 0.75 else ("transfer" if conf <= 0.30 else "unknown")
        candidates.append(
            DepositCandidate(
                source_name=description[:80] or "Deposit",
                account_external_id=acct,
                amount_cents=amount,
                occurred_at=_parse_date(txn.get("occurred_at")),
                transaction_external_id=str(txn.get("external_id") or ""),
                confidence=conf,
                reason=f"matched description '{description[:40]}'",
                kind=kind,
                evidence_ids=tuple(txn.get("evidence_ids") or ()),
            )
        )
    candidates.sort(key=lambda c: -c.confidence)
    return DepositDiscovery(
        candidates=tuple(candidates),
        account_whitelist=whitelist,
        note="candidates only — owner confirmation required before any FundingSource is created",
    )


def _parse_date(value) -> date:
    from datetime import datetime

    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except Exception:  # noqa: BLE001 - unknown date form
        return date.today()
