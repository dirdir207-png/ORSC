"""Pure deterministic transaction classification with explicit precedence."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ClassificationInput:
    id: int
    amount: float
    description: str
    merchant: str | None
    account_type: str
    occurred_at: str
    relation_type: str | None = None


@dataclass(frozen=True)
class AssignmentRule:
    id: str
    category: str
    kind: str
    merchant_pattern: str | None = None
    description_pattern: str | None = None


@dataclass(frozen=True)
class Classification:
    category: str
    kind: str
    confidence: float
    rule_id: str
    evidence: str
    method: str
    provider: str | None = None
    model: str | None = None


_KNOWN_MERCHANTS = {
    "whole foods": ("Groceries", "merchant:whole-foods"),
}


def _matches(rule: AssignmentRule, transaction: ClassificationInput) -> bool:
    merchant = (transaction.merchant or "").casefold()
    description = transaction.description.casefold()
    return (
        (rule.merchant_pattern is None or rule.merchant_pattern.casefold() in merchant)
        and (rule.description_pattern is None or rule.description_pattern.casefold() in description)
    )


def _date(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _is_monthly(transaction: ClassificationInput, history) -> bool:
    merchant = (transaction.merchant or "").casefold()
    if not merchant:
        return False
    dates = sorted(
        [_date(item.occurred_at) for item in history if (item.merchant or "").casefold() == merchant]
        + [_date(transaction.occurred_at)]
    )
    if len(dates) < 3:
        return False
    intervals = [(later - earlier).days for earlier, later in zip(dates, dates[1:])]
    return all(25 <= interval <= 35 for interval in intervals[-2:])


def classify_deterministic(
    transaction: ClassificationInput,
    *,
    user_rules=(),
    history=(),
) -> Classification:
    for rule in user_rules:
        if _matches(rule, transaction):
            return Classification(
                rule.category,
                rule.kind,
                1.0,
                rule.id,
                "matched an owner-defined assignment rule",
                "user_rule",
            )
    if transaction.relation_type in {"owned_transfer", "credit_payment"}:
        return Classification(
            "Transfers",
            "transfer",
            1.0,
            f"relation:{transaction.relation_type}",
            f"reconciliation identified {transaction.relation_type.replace('_', ' ')}",
            "deterministic",
        )
    if transaction.relation_type == "reimbursement":
        return Classification(
            "Reimbursements",
            "reimbursement",
            0.98,
            "relation:reimbursement",
            "shared-money evidence identified a reimbursement",
            "deterministic",
        )
    if transaction.relation_type == "refund" and transaction.amount > 0:
        return Classification(
            "Refunds",
            "refund",
            0.98,
            "relation:refund",
            "matched to an earlier purchase on the same account",
            "deterministic",
        )
    description = transaction.description.casefold()
    if transaction.amount > 0 and ("refund" in description or "reversal" in description):
        return Classification(
            "Refunds",
            "refund",
            0.98,
            "transaction:refund",
            "positive amount and refund language",
            "deterministic",
        )
    merchant = (transaction.merchant or "").casefold()
    for pattern, (category, rule_id) in _KNOWN_MERCHANTS.items():
        if pattern in merchant or pattern in description:
            return Classification(
                category,
                "spend",
                0.95,
                rule_id,
                f"normalized merchant matched {pattern}",
                "deterministic",
            )
    if _is_monthly(transaction, history):
        return Classification(
            "Recurring",
            "spend" if transaction.amount < 0 else "income",
            0.85,
            "recurrence:merchant-monthly",
            "same merchant observed on a stable 25–35 day interval",
            "deterministic",
        )
    return Classification(
        "Uncategorized",
        "spend" if transaction.amount < 0 else "income",
        0.2,
        "fallback:amount-sign",
        "amount sign only; review needed",
        "fallback",
    )
