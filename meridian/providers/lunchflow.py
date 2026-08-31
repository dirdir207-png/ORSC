"""Read-only LunchFlow normalization for Meridian."""

from datetime import datetime, timezone

from .base import NormalizedAccount, NormalizedTransaction, ProviderSnapshot


class LunchFlowAdapter:
    provider_name = "lunchflow"
    connection_external_id = "lunchflow-user"
    connection_name = "LunchFlow"

    def __init__(self, fetch_accounts, fetch_transactions, *, observed_at: str | None = None):
        self._fetch_accounts = fetch_accounts
        self._fetch_transactions = fetch_transactions
        self._observed_at = observed_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def fetch_snapshot(self) -> ProviderSnapshot:
        payload = self._fetch_accounts()
        source_accounts = payload.get("accounts", []) if isinstance(payload, dict) else []
        accounts = []
        transactions = []
        errors = []
        for source_account in source_accounts:
            external_id = source_account.get("id")
            if not isinstance(external_id, str) or not external_id:
                errors.append("account missing stable id")
                continue
            balance = source_account.get("balance") or {}
            if not isinstance(balance, dict):
                balance = {"amount": balance}
            accounts.append(NormalizedAccount(
                external_id=external_id,
                name=str(source_account.get("name") or "LunchFlow account"),
                account_type=str(source_account.get("type") or "credit"),
                balance=round(float(balance.get("amount") or 0), 2),
                currency=str(balance.get("currency") or source_account.get("currency") or "USD").upper(),
                source_updated_at=str(source_account.get("updatedAt") or self._observed_at),
            ))
            try:
                source_transactions = self._fetch_transactions(external_id).get("transactions", [])
            except Exception:
                errors.append(f"transactions unavailable for {external_id}")
                continue
            for source_transaction in source_transactions:
                transaction_id = source_transaction.get("id")
                occurred_at = source_transaction.get("date") or source_transaction.get("occurredAt")
                if not isinstance(transaction_id, str) or not transaction_id or not isinstance(occurred_at, str):
                    errors.append("transaction missing stable id or timestamp")
                    continue
                shared_id = source_transaction.get("shared_expense_id")
                transactions.append(NormalizedTransaction(
                    external_id=transaction_id,
                    account_external_id=external_id,
                    amount=round(float(source_transaction.get("amount") or 0), 2),
                    occurred_at=occurred_at,
                    description=str(source_transaction.get("description") or source_transaction.get("merchant") or "LunchFlow transaction"),
                    status="pending" if source_transaction.get("isPending") else "posted",
                    currency=str(source_transaction.get("currency") or "USD").upper(),
                    merchant=source_transaction.get("merchant"),
                    source_updated_at=str(source_transaction.get("updatedAt") or self._observed_at),
                    relation_hint=f"lunchflow-shared:{shared_id}" if shared_id else None,
                ))
        return ProviderSnapshot(
            connection_external_id=self.connection_external_id,
            connection_name=self.connection_name,
            accounts=tuple(accounts),
            transactions=tuple(transactions),
            is_complete=not errors,
            errors=tuple(errors),
        )
