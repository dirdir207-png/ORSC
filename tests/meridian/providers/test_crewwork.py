"""Creates a read-only Meridian provider adapter from a CrewWorkAssistant
(crew-readonly MCP) snapshot. Balances and amounts are cents; the adapter
normalizes them to dollars like CrewReadAdapter."""

from meridian.providers.crewwork import CrewWorkSnapshotAdapter


def _snapshot():
    """A realistic CrewWorkAssistant snapshot payload (as produced by
    `crew-readonly snapshot` with its normalize_* helpers)."""
    return {
        "mode": "read-only",
        "source": "crew",
        "captured_at": "2026-09-01T14:00:00Z",
        "complete": True,
        "mutations_enabled": False,
        "data": {
            "accounts": {
                "data": {
                    "currentUser": {
                        "accounts": [
                            {
                                "id": "QWNjb3VudDox",
                                "displayName": "Checking",
                            }
                        ]
                    }
                }
            },
            "pockets": {
                "data": {
                    "currentUser": {
                        "accounts": [
                            {
                                "id": "QWNjb3VudDox",
                                "displayName": "Checking",
                                "subaccounts": [
                                    {
                                        "id": "U3ViYWNjb3VudDox",
                                        "displayName": "Checking",
                                        "overallBalance": 12345,
                                        "clearedBalance": 12000,
                                        "isPrimary": True,
                                        "status": "ACTIVATED",
                                    }
                                ],
                            }
                        ]
                    }
                }
            },
            "transactions": {
                "data": {
                    "account": {
                        "id": "QWNjb3VudDox",
                        "cashTransactions": {
                            "edges": [
                                {
                                    "node": {
                                        "id": "Q2FzaFRyYW5zYWN0aW9uOjE=",
                                        "amount": -459,
                                        "currencyCode": "USD",
                                        "description": "Coffee shop",
                                        "title": "Coffee shop",
                                        "occurredAt": "2026-09-01T09:00:00Z",
                                        "type": "DEBIT",
                                        "status": "CLEARED",
                                        "subaccount": {"id": "U3ViYWNjb3VudDox"},
                                        "matchingName": "Blue Bottle",
                                        "memo": "latte",
                                    }
                                }
                            ],
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                        },
                    }
                }
            },
        },
    }


def test_adapter_normalizes_snapshot_to_dollars():
    adapter = CrewWorkSnapshotAdapter(_snapshot())
    assert adapter.provider_name == "crew"
    snapshot = adapter.fetch_snapshot()

    assert snapshot.is_complete is True
    assert snapshot.errors == ()

    # One pocket account + one synthetic parent account (for account-level txns)
    assert len(snapshot.accounts) == 2
    account = snapshot.accounts[0]
    assert account.external_id == "U3ViYWNjb3VudDox"
    assert account.name == "Checking"
    assert account.account_type == "checking"
    assert account.balance == 123.45
    assert account.currency == "USD"

    # One transaction: cents -> dollars, status mapped
    assert len(snapshot.transactions) == 1
    txn = snapshot.transactions[0]
    assert txn.external_id == "Q2FzaFRyYW5zYWN0aW9uOjE="
    assert txn.amount == -4.59
    assert txn.occurred_at == "2026-09-01T09:00:00Z"
    assert txn.description == "Coffee shop"
    assert txn.merchant == "Blue Bottle"
    assert txn.status in ("posted", "pending", "cleared")


def test_adapter_keeps_parent_account_transactions():
    """Transactions without a subaccount must still be retained via the
    synthetic parent account (never silently dropped by the sync engine)."""
    snap = _snapshot()
    snap["data"]["transactions"]["data"]["account"]["cashTransactions"]["edges"].append(
        {
            "node": {
                "id": "Q2FzaFRyYW5zYWN0aW9uOjI=",
                "amount": -1000,
                "currencyCode": "USD",
                "description": "Account-level transfer",
                "title": "Transfer",
                "occurredAt": "2026-09-01T10:00:00Z",
                "type": "TRANSFER",
                "status": "CLEARED",
                "subaccount": None,
                "matchingName": None,
                "memo": None,
            }
        }
    )
    snapshot = CrewWorkSnapshotAdapter(snap).fetch_snapshot()
    # The parent account id is present so the transfer transaction maps to it.
    transfer = [t for t in snapshot.transactions if t.external_id == "Q2FzaFRyYW5zYWN0aW9uOjI="]
    assert len(transfer) == 1
    assert transfer[0].account_external_id == "QWNjb3VudDox"
    # The synthetic parent account exists in the normalized accounts.
    parent_ids = {a.external_id for a in snapshot.accounts}
    assert "QWNjb3VudDox" in parent_ids


def test_adapter_marks_incomplete_when_snapshot_incomplete():
    snapshot = dict(_snapshot())
    snapshot["complete"] = False
    result = CrewWorkSnapshotAdapter(snapshot).fetch_snapshot()
    assert result.is_complete is False


def test_adapter_rejects_unsafe_source():
    # A snapshot that claims mutation authority must be rejected.
    bad = dict(_snapshot())
    bad["mutations_enabled"] = True
    try:
        CrewWorkSnapshotAdapter(bad).fetch_snapshot()
    except ValueError:
        return
    raise AssertionError("mutation-capable snapshot must be rejected")
