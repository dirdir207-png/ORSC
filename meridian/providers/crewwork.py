"""Read-only Meridian provider adapter for a CrewWorkAssistant snapshot.

CrewWorkAssistant (the ``crew-readonly`` MCP server) produces a Credential-free
Crew dashboard snapshot exactly matching the mobile/API auth Crew supports
(JWT + Stytch session token kept in the Mac Keychain). This adapter consumes
that snapshot — it never makes Crew network calls and never touches
credentials — and normalizes it into Meridian ProviderSnapshot records.

Balances and amounts in the snapshot are cents; the adapter converts to the
dollar convention used by CrewReadAdapter (divide by 100).
"""

from datetime import date, datetime
from typing import Any, Dict, Optional

from .base import NormalizedAccount, NormalizedTransaction, ProviderSnapshot

# Map Crew's status / type strings to the Meridian transaction status
# vocabulary used by the sync engine (see meridian/sync and CrewReadAdapter).
_STATUS_MAP = {
    "CLEARED": "posted",
    "POSTED": "posted",
    "PENDING": "pending",
    "DEBIT": "posted",
    "CREDIT": "posted",
    "UNKNOWN": "posted",
}

# Account type: primary pocket -> checking, everything else -> pocket.
_ACCOUNT_TYPE = {"ACTIVATED": "checking"}


def _status(value: Optional[str]) -> str:
    if value is None:
        return "posted"
    return _STATUS_MAP.get(str(value).upper(), "posted")


def _cents_to_dollars(value: Any) -> float:
    try:
        return float(value or 0) / 100
    except (TypeError, ValueError):
        return 0.0


def _as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list:
    return value if isinstance(value, list) else []


class CrewWorkSnapshotAdapter:
    """Translate a CrewWorkAssistant snapshot into Meridian's read-only model."""

    provider_name = "crew"
    connection_external_id = "crew-work-assistant"
    connection_name = "Crew (Work Assistant)"

    def __init__(self, snapshot: Dict[str, Any]):
        if not isinstance(snapshot, dict):
            raise ValueError("CrewWorkAssistant snapshot must be an object")
        if snapshot.get("mode") != "read-only" or snapshot.get("source") != "crew":
            raise ValueError("CrewWorkAssistant snapshot must come from the read-only Crew source")
        if snapshot.get("mutations_enabled", False) is not False:
            raise ValueError("CrewWorkAssistant snapshot cannot claim mutation authority")
        self._snapshot = snapshot

    def fetch_snapshot(self) -> ProviderSnapshot:
        captured_at = self._snapshot.get("captured_at") or ""
        complete = bool(self._snapshot.get("complete"))
        snap_errors = self._snapshot.get("errors") or {}

        accounts = self._collect_accounts(captured_at)
        transactions = self._collect_transactions(accounts)
        errors = tuple(self._snapshot_errors(snap_errors))

        return ProviderSnapshot(
            connection_external_id=self.connection_external_id,
            connection_name=self.connection_name,
            accounts=tuple(accounts),
            transactions=tuple(transactions),
            is_complete=complete and not errors,
            errors=errors,
        )

    def _snapshot_errors(self, snap_errors: Any) -> list[str]:
        if not isinstance(snap_errors, dict):
            return []
        # Error details are human-readable summaries produced by the MCP; keep
        # them as-is but never surface raw source payloads.
        values = []
        for key, message in snap_errors.items():
            values.append(f"{key}: {message}" if isinstance(message, str) else str(key))
        return values

    def _collect_accounts(self, captured_at: str = "") -> list[NormalizedAccount]:
        data = _as_dict(self._snapshot.get("data"))
        # The snapshot keeps account identity in data.accounts (id/name only)
        # and the pocket subaccounts (with balances) in data.pockets. The
        # CrewReadAdapter convention: primary pocket -> checking, else pocket.
        pockets_payload = _as_dict(data.get("pockets"))
        current_user = _as_dict(_as_dict(pockets_payload).get("data")).get("currentUser")
        source_accounts = _as_list(_as_dict(current_user).get("accounts"))
        owned = set()
        result = []
        for source in source_accounts:
            account_id = str(source.get("id") or "")
            if not account_id:
                continue
            for pocket in _as_list(source.get("subaccounts")):
                external_id = str(pocket.get("id") or "")
                if not external_id:
                    continue
                owned.add(external_id)
                name = str(pocket.get("displayName") or pocket.get("name") or "Crew account")
                is_primary = bool(pocket.get("isPrimary"))
                result.append(
                    NormalizedAccount(
                        external_id=external_id,
                        name=name,
                        account_type="checking" if is_primary else "pocket",
                        balance=_cents_to_dollars(pocket.get("overallBalance")),
                        currency="USD",
                        available_balance=_cents_to_dollars(pocket.get("clearedBalance")),
                        is_active=True,
                        source_updated_at=captured_at or None,
                    )
                )
        # Some transactions carry only the parent account (no subaccount) — e.g.
        # account-level transfers. Add a synthetic parent account so those
        # records are never dropped by the sync engine's account mapping.
        accounts_payload = _as_dict(data.get("accounts"))
        account_current_user = _as_dict(_as_dict(accounts_payload).get("data")).get("currentUser")
        for source in _as_list(_as_dict(account_current_user).get("accounts")):
            account_id = str(source.get("id") or "")
            if not account_id or account_id in owned:
                continue
            result.append(
                NormalizedAccount(
                    external_id=account_id,
                    name=str(source.get("displayName") or "Crew account"),
                    account_type="fallback",
                    balance=0.0,
                    currency="USD",
                    is_active=True,
                    source_updated_at=captured_at or None,
                )
            )
        return result

    def _collect_transactions(self, accounts: list[NormalizedAccount]) -> list[NormalizedTransaction]:
        owned = {account.external_id for account in accounts}
        transactions_payload = _as_dict(self._snapshot.get("data", {}).get("transactions"))
        account_node = _as_dict(_as_dict(transactions_payload).get("data")).get("account")
        edges = _as_list(_as_dict(_as_dict(account_node).get("cashTransactions")).get("edges"))
        observed_at = str(self._snapshot.get("captured_at") or "")

        result = []
        for edge in edges:
            node = _as_dict(edge.get("node"))
            external_id = str(node.get("id") or "")
            occurred_at = str(node.get("occurredAt") or "")
            if not external_id or not occurred_at:
                continue
            subaccount = _as_dict(node.get("subaccount"))
            pocket_id = str(subaccount.get("id") or "")
            account_external_id = pocket_id if pocket_id in owned else str(account_node.get("id") or pocket_id)
            result.append(
                NormalizedTransaction(
                    external_id=external_id,
                    account_external_id=account_external_id or (accounts[0].external_id if accounts else ""),
                    amount=_cents_to_dollars(node.get("amount")),
                    occurred_at=occurred_at,
                    description=str(node.get("description") or node.get("title") or "Crew transaction"),
                    status=_status(node.get("status") or node.get("type")),
                    currency=str(node.get("currencyCode") or "USD"),
                    merchant=node.get("matchingName"),
                    raw_description=node.get("memo") or node.get("externalMemo"),
                    source_updated_at=observed_at or occurred_at,
                )
            )
        return result
