"""Deterministic, idempotent transaction relation discovery."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ReconciliationReport:
    relations_created: int
    ambiguous: int


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def reconcile(snapshot, repository) -> ReconciliationReport:
    with repository._connect() as connection:
        rows = connection.execute(
            """
            SELECT item.id, item.provider, item.external_id,
                   item.account_id, item.amount, item.occurred_at,
                   item.description, account.account_type
            FROM financial_transactions AS item
            JOIN financial_accounts AS account ON account.id = item.account_id
            ORDER BY item.id
            """
        ).fetchall()
    by_external_id = {}
    for row in rows:
        by_external_id.setdefault(row["external_id"], []).append(row)
    current = [
        by_external_id[item.external_id][0]
        for item in snapshot.transactions
        if len(by_external_id.get(item.external_id, ())) == 1
    ]
    created = 0
    ambiguous = 0
    handled_ids = set()
    hints = {}
    for item in snapshot.transactions:
        if item.relation_hint:
            hints.setdefault(item.relation_hint, []).append(item.external_id)
    for hint, external_ids in hints.items():
        if len(external_ids) != 2:
            continue
        left, right = (by_external_id[item][0] for item in external_ids)
        if left["amount"] != -right["amount"]:
            ambiguous += 1
            continue
        created += repository.upsert_transaction_relation(
            provider="meridian",
            external_id=f"hint:{hint}",
            source_transaction_id=min(left["id"], right["id"]),
            related_transaction_id=max(left["id"], right["id"]),
            relation_type="owned_transfer",
            confidence=1.0,
        )
        handled_ids.update((left["id"], right["id"]))
    for transaction in current:
        if transaction["id"] in handled_ids:
            continue
        matches = [
            candidate
            for candidate in rows
            if candidate["id"] != transaction["id"]
            and candidate["amount"] == -transaction["amount"]
            and abs((_timestamp(candidate["occurred_at"]) - _timestamp(transaction["occurred_at"])).total_seconds()) <= 3 * 86400
        ]
        if len(matches) > 1:
            ambiguous += 1
            continue
        if not matches:
            continue
        match = matches[0]
        same_account = transaction["account_id"] == match["account_id"]
        positive = transaction if transaction["amount"] > 0 else match
        if same_account:
            positive_description = positive["description"].casefold()
            if "refund" not in positive_description and "reversal" not in positive_description:
                continue
            relation_type = "refund"
        else:
            descriptions = f"{transaction['description']} {match['description']}".casefold()
            if "credit" in {transaction["account_type"], match["account_type"]}:
                if not any(term in descriptions for term in ("payment", "autopay", "card pay")):
                    ambiguous += 1
                    continue
                relation_type = "credit_payment"
            else:
                if not any(term in descriptions for term in ("transfer", "xfer")):
                    ambiguous += 1
                    continue
                relation_type = "owned_transfer"
        pair = sorted((transaction["id"], match["id"]))
        created += repository.upsert_transaction_relation(
            provider="meridian",
            external_id=f"amount-date:{pair[0]}:{pair[1]}",
            source_transaction_id=pair[0],
            related_transaction_id=pair[1],
            relation_type=relation_type,
            confidence=0.9,
        )
        handled_ids.update(pair)
    return ReconciliationReport(created, ambiguous)
