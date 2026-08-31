"""Read-only SimpleFin normalization for Meridian."""

from datetime import datetime, timezone

from .base import NormalizedAccount, NormalizedTransaction, ProviderSnapshot


def _milliunits(source: dict, milliunit_key: str, amount_key: str) -> float:
    if source.get(milliunit_key) is not None:
        return round(float(source[milliunit_key]) / 1000, 2)
    return round(float(source.get(amount_key) or 0), 2)


class SimpleFinAdapter:
    provider_name = "simplefin"
    connection_external_id = "simplefin-access"
    connection_name = "SimpleFin"

    def __init__(self, fetch_accounts, *, observed_at: str | None = None):
        self._fetch_accounts = fetch_accounts
        self._observed_at = observed_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def fetch_snapshot(self) -> ProviderSnapshot:
        payload = self._fetch_accounts()
        source_accounts = payload.get("accounts", []) if isinstance(payload, dict) else []
        owned_ids = {item.get("id") for item in source_accounts if isinstance(item.get("id"), str)}
        accounts = []
        transactions = []
        errors = []
        for source_account in source_accounts:
            external_id = source_account.get("id")
            if not isinstance(external_id, str) or not external_id:
                errors.append("account missing stable id")
                continue
            accounts.append(NormalizedAccount(
                external_id=external_id,
                name=str(source_account.get("name") or "SimpleFin account"),
                account_type=str(source_account.get("type") or "other"),
                balance=_milliunits(source_account, "balance_milliunits", "balance"),
                currency=str(source_account.get("currency") or "USD").upper(),
                source_updated_at=str(source_account.get("updated_at") or self._observed_at),
            ))
            for source_transaction in source_account.get("transactions") or []:
                transaction_id = source_transaction.get("id")
                occurred_at = source_transaction.get("posted_at") or source_transaction.get("transacted_at")
                if not isinstance(transaction_id, str) or not transaction_id or not isinstance(occurred_at, str):
                    errors.append("transaction missing stable id or timestamp")
                    continue
                transfer_id = source_transaction.get("transfer_id")
                counterparty_id = source_transaction.get("counterparty_account_id")
                relation_hint = (
                    f"simplefin-transfer:{transfer_id}"
                    if isinstance(transfer_id, str) and transfer_id and counterparty_id in owned_ids
                    else None
                )
                transactions.append(NormalizedTransaction(
                    external_id=transaction_id,
                    account_external_id=external_id,
                    amount=_milliunits(source_transaction, "amount_milliunits", "amount"),
                    occurred_at=occurred_at,
                    posted_at=source_transaction.get("posted_at"),
                    description=str(source_transaction.get("description") or "SimpleFin transaction"),
                    merchant=source_transaction.get("merchant"),
                    status=str(source_transaction.get("status") or ("posted" if source_transaction.get("posted_at") else "pending")),
                    currency=str(source_transaction.get("currency") or source_account.get("currency") or "USD").upper(),
                    raw_description=source_transaction.get("raw_description"),
                    source_updated_at=str(source_transaction.get("updated_at") or self._observed_at),
                    relation_hint=relation_hint,
                ))
        return ProviderSnapshot(
            connection_external_id=self.connection_external_id,
            connection_name=self.connection_name,
            accounts=tuple(accounts),
            transactions=tuple(transactions),
            is_complete=not errors,
            errors=tuple(errors),
        )
