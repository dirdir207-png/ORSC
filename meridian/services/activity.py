"""Read-only Activity access backed exclusively by FinancialRepository."""

from datetime import datetime
from typing import Optional

from meridian.models import TransactionRecord
from meridian.repository import FinancialRepository
from meridian.services.today import data_freshness


def get_activity(
    repository: FinancialRepository,
    *,
    limit: int = 50,
    cursor: Optional[str] = None,
    account_id: Optional[int] = None,
    now: Optional[datetime] = None,
) -> dict[str, object]:
    """Return one stable repository page plus the graph's freshness state."""
    transactions, next_cursor = repository.list_transactions(
        limit=limit,
        cursor=cursor,
        account_id=account_id,
    )
    freshness_kwargs = (
        {"account_ids": [account_id]}
        if account_id is not None
        else {
            "transaction_ids": [transaction.id for transaction in transactions],
            "include_all_connections": True,
            "include_all_transaction_links": True,
        }
    )
    return {
        "transactions": transactions,
        "next_cursor": next_cursor,
        "data_freshness": data_freshness(repository, **freshness_kwargs, now=now),
    }


def get_transaction(
    repository: FinancialRepository, transaction_id: int
) -> Optional[TransactionRecord]:
    """Return one normalized transaction without reaching any provider."""
    return repository.get_transaction(transaction_id)


def get_review_queue(
    repository: FinancialRepository, *, confidence_threshold: float = 0.7
) -> list[TransactionRecord]:
    transactions, _ = repository.list_transactions(limit=200)
    return sorted(
        (
            transaction
            for transaction in transactions
            if transaction.classification_confidence is not None
            and transaction.classification_confidence < confidence_threshold
        ),
        key=lambda transaction: (
            transaction.classification_confidence,
            transaction.occurred_at,
            transaction.id,
        ),
    )


def get_patterns(repository: FinancialRepository) -> list[dict[str, object]]:
    transactions, _ = repository.list_transactions(limit=200)
    by_merchant: dict[str, list[TransactionRecord]] = {}
    for transaction in transactions:
        key = (transaction.merchant or transaction.description).strip().casefold()
        by_merchant.setdefault(key, []).append(transaction)
    patterns = []
    for merchant, items in sorted(by_merchant.items()):
        ordered = sorted(items, key=lambda item: item.occurred_at)
        if len(ordered) >= 3:
            dates = [datetime.fromisoformat(item.occurred_at.replace("Z", "+00:00")) for item in ordered]
            intervals = [(later - earlier).days for earlier, later in zip(dates, dates[1:])]
            if len(intervals) >= 2 and all(25 <= interval <= 35 for interval in intervals[-2:]):
                patterns.append(
                    {
                        "kind": "recurrence",
                        "title": f"Monthly pattern: {ordered[-1].merchant or ordered[-1].description}",
                        "evidence_ids": [item.id for item in ordered[-3:]],
                    }
                )
            categories = {item.classification_category for item in ordered if item.classification_category}
            if len(categories) > 1:
                patterns.append(
                    {
                        "kind": "category_shift",
                        "title": f"Category changed for {merchant}",
                        "evidence_ids": [item.id for item in ordered[-3:]],
                    }
                )
            previous_average = sum(abs(item.amount) for item in ordered[:-1]) / (len(ordered) - 1)
            if previous_average and abs(ordered[-1].amount) > previous_average * 1.2:
                patterns.append(
                    {
                        "kind": "merchant_trend",
                        "title": f"Spending increased at {merchant}",
                        "evidence_ids": [item.id for item in ordered[-3:]],
                    }
                )
    if len(transactions) >= 6:
        ordered = sorted(transactions, key=lambda item: item.occurred_at)
        midpoint = len(ordered) // 2
        older = sum(item.amount for item in ordered[:midpoint])
        newer = sum(item.amount for item in ordered[midpoint:])
        if abs(newer - older) > max(abs(older) * 0.2, 1):
            patterns.append(
                {
                    "kind": "cash_flow_change",
                    "title": "Recent cash flow changed",
                    "evidence_ids": [item.id for item in ordered[-3:]],
                }
            )
    return patterns
