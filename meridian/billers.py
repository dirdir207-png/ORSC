"""Read-only Biller Monitor (R33).

A biller monitor that computes bill state from what Meridian can actually
read — its own bill commitments + transaction charge history — and surfaces
changes into review. It does NOT invent provider data.

Honest boundaries (R33/R34):
- NO payment-method switching (infeasible on Crew; R34 gates it behind a
  vetted partner + bank-action authority).
- NO autopay / statement / biller-health fields: Crew exposes none of these,
  so we omit them rather than fake them.
- NO second bill identity: every row reuses the existing commitment id.

Every field is tagged with ``provenance`` so the UI never implies a value
came from a live provider when it was computed locally.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from .commitments import Commitment, CommitmentType
from .models import TransactionRecord

_FIELD_RECURRENCE = ("monthly", "weekly", "biweekly", "annually", "yearly")

# Amount-change threshold (dollars) — a bill whose latest charge or current
# amount moved by more than this is flagged as changed for review.
DEFAULT_CHANGE_THRESHOLD = 5.0


@dataclass(frozen=True)
class MonitorBill:
    commitment_id: int
    name: str
    currency: str
    amount: Optional[float]
    recurrence: Optional[str]
    next_due: Optional[str]
    due_date: Optional[str]
    funded_amount: float
    last_paid_date: Optional[str]
    last_paid_amount: Optional[float]
    amount_change: Optional[float]
    status: str  # on_track | changed | due_soon | unfunded
    provenance: dict[str, str]  # field -> "crew_bill" | "owner_set" | "computed"
    source: Optional[str]


def _date_of(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _next_due(commitment: Commitment, today: date) -> Optional[str]:
    """Project the next due date from due_date or its recurrence.

    If ``due_date`` has not yet passed, it is the next due. If it is already
    past, roll forward by the recurrence interval (calendar month/week/etc.)
    until it is >= today, so the monitor reports the next real occurrence.
    """
    base = _date_of(commitment.due_date)
    if base is None:
        return None
    seed = base
    guard = 0
    while seed < today and guard < 400:
        added = _advance(seed, commitment.recurrence)
        if added is None or added <= seed:
            break
        seed = added
        guard += 1
    return seed.isoformat()


def _advance(anchor: date, recurrence: Optional[str]) -> Optional[date]:
    """Advance ``anchor`` by one recurrence period without stretching a month."""
    rec = (recurrence or "").strip().lower()
    if rec in ("monthly", "month"):
        year = anchor.year + (anchor.month // 12)
        month = anchor.month % 12 + 1
        # Clamp the day to the last day of the target month.
        import calendar
        day = min(anchor.day, calendar.monthrange(year, month)[1])
        return date(year, month, day)
    if rec in ("weekly", "week"):
        return anchor + timedelta(days=7)
    if rec in ("biweekly", "bi-weekly", "fortnight"):
        return anchor + timedelta(days=14)
    if rec in ("annually", "yearly", "annual", "year"):
        try:
            return date(anchor.year + 1, anchor.month, anchor.day)
        except ValueError:
            return date(anchor.year + 1, 2, 28)
    return None


def _merchant_match(bill_name: str, merchant: Optional[str]) -> bool:
    """Conservative merchant->bill match: bill-name token appears in the
    merchant string (or vice versa). Case-folding and punctuation-insensitive."""
    if not merchant:
        return False
    def tokens(text: str) -> list[str]:
        return [t for t in "".join(c.lower() if c.isalnum() else " " for c in text).split() if t]
    bill_toks = tokens(bill_name)
    mer_toks = tokens(merchant)
    if not bill_toks or not mer_toks:
        return False
    return any(tok in mer_toks for tok in bill_toks)


def _last_paid(
    bill_name: str, transactions: list[TransactionRecord]
) -> tuple[Optional[str], Optional[float]]:
    """Most recent charge transaction ~matching this bill (largest amount)."""
    matches = []
    for tx in transactions:
        if not tx.occurred_at or tx.amount >= 0:
            continue
        if _merchant_match(bill_name, tx.merchant):
            matches.append(tx)
    if not matches:
        return None, None
    latest = max(matches, key=lambda tx: tx.occurred_at)
    latest_date = _date_of(latest.occurred_at)
    return latest_date.isoformat() if latest_date else None, abs(latest.amount)


def _funded_status(funded: float, amount: Optional[float]) -> str:
    if amount is None or amount <= 0:
        return "on_track"
    return "on_track" if funded >= amount else "unfunded"


def _days_until(next_due: Optional[str], today: date) -> Optional[int]:
    d = _date_of(next_due)
    return (d - today).days if d else None


def build_biller_monitor(
    commitments: list[Commitment],
    transactions: list[TransactionRecord],
    *,
    today: Optional[date] = None,
    change_threshold: float = DEFAULT_CHANGE_THRESHOLD,
) -> list[MonitorBill]:
    """Compute the read-only bill monitor from bill commitments + history.

    ``commitments`` are bill-typed (caller filters); ``transactions`` is the
    full available charge history used to derive last-paid. Pure function — no
    provider/network, no mutation, deterministic.

    Status precedence (a bill has one status; attention wins):
      on_track  -> funded enough and not flagged
      unfunded  -> reserved amount < amount due
      due_soon  -> due within 7 days AND not fully funded (it needs attention)
      changed   -> amount moved by >= change_threshold vs last paid (independent)
    """
    today = today or datetime.now(timezone.utc).date()
    bills = [c for c in commitments if c.type == CommitmentType.BILL and c.status.value != "archived"]
    monitor: list[MonitorBill] = []
    for bill in bills:
        amount = bill.amount or bill.target_amount
        due_date = _date_of(bill.due_date)
        next_due = _next_due(bill, today)
        last_paid_date, last_paid_amount = _last_paid(bill.name, transactions)

        amount_change = None
        if amount is not None and last_paid_amount is not None:
            amount_change = round(amount - last_paid_amount, 2)

        status = _funded_status(bill.funded_amount, amount)
        fully_funded = status == "on_track"
        days = _days_until(next_due, today)
        if days is not None and days <= 7 and not fully_funded:
            status = "due_soon"
        if amount_change is not None and abs(amount_change) >= change_threshold:
            status = "changed"

        provenance = {
            "amount": "crew_bill" if bill.legacy_source == "crew" else ("owner_set" if bill.amount is not None else "owner_set"),
            "due_date": "owner_set" if bill.due_date else "computed",
            "next_due": "computed",
            "recurrence": "owner_set",
            "funded_amount": "computed",
            "last_paid": "computed",
        }

        monitor.append(
            MonitorBill(
                commitment_id=bill.id,
                name=bill.name,
                currency=bill.currency,
                amount=amount,
                recurrence=bill.recurrence,
                next_due=next_due,
                due_date=due_date.isoformat() if due_date else None,
                funded_amount=bill.funded_amount,
                last_paid_date=last_paid_date,
                last_paid_amount=last_paid_amount,
                amount_change=amount_change,
                status=status,
                provenance=provenance,
                source=bill.legacy_source,
            )
        )
    return sorted(monitor, key=lambda b: b.next_due or "9999-12-31")


def bill_status_for(
    commitment: Commitment,
    *,
    today: Optional[date] = None,
) -> str:
    """Compute the Plan-card badge status for a single bill commitment.

    Lightweight (no transaction history): reflects funding coverage and how
    soon the bill is due. Returns one of ``on_track | unfunded | due_soon``.
    (``changed`` needs last-paid history and is reported by the monitor, not
    here, so a Plan badge never claims a drift it did not measure.)

    Precedence: unfunded wins, then due_soon (unfunded + due soon is shown as
    ``due_soon`` so the urgent case is not hidden behind a generic underfund
    badge); fully-funded bills are ``on_track`` regardless of due date.
    """
    if commitment.type != CommitmentType.BILL:
        return "on_track"
    today = today or datetime.now(timezone.utc).date()
    amount = commitment.amount or commitment.target_amount
    funded = commitment.funded_amount or 0.0
    next_due = _next_due(commitment, today)

    if amount is None or amount <= 0:
        return "on_track"
    funded_ok = funded >= amount
    if not funded_ok:
        days = _days_until(next_due, today)
        if days is not None and days <= 7:
            return "due_soon"
        return "unfunded"
    return "on_track"
