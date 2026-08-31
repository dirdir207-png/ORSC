from meridian.providers.lunchflow import LunchFlowAdapter
from meridian.providers.simplefin import SimpleFinAdapter
from meridian.providers.splitwise import SplitwiseAdapter

OBSERVED_AT = "2026-08-29T12:00:00Z"


def test_simplefin_normalizes_milliunits_and_owned_transfer_hints():
    adapter = SimpleFinAdapter(
        lambda: {
            "accounts": [
                {
                    "id": "checking",
                    "name": "Checking",
                    "type": "checking",
                    "balance_milliunits": 125050,
                    "transactions": [
                        {
                            "id": "out",
                            "amount_milliunits": -25000,
                            "posted_at": "2026-08-28T10:00:00Z",
                            "description": "Transfer to Card",
                            "transfer_id": "owned-1",
                            "counterparty_account_id": "card",
                        }
                    ],
                },
                {
                    "id": "card",
                    "name": "Card",
                    "type": "credit",
                    "balance_milliunits": -50000,
                    "transactions": [
                        {
                            "id": "in",
                            "amount_milliunits": 25000,
                            "posted_at": "2026-08-28T10:00:00Z",
                            "description": "Payment",
                            "transfer_id": "owned-1",
                            "counterparty_account_id": "checking",
                        }
                    ],
                },
            ]
        },
        observed_at=OBSERVED_AT,
    )

    snapshot = adapter.fetch_snapshot()

    assert [account.balance for account in snapshot.accounts] == [125.05, -50.0]
    assert [transaction.amount for transaction in snapshot.transactions] == [-25.0, 25.0]
    assert {transaction.relation_hint for transaction in snapshot.transactions} == {
        "simplefin-transfer:owned-1"
    }
    assert all(transaction.source_updated_at == OBSERVED_AT for transaction in snapshot.transactions)


def test_lunchflow_normalizes_accounts_and_shared_expenses():
    adapter = LunchFlowAdapter(
        lambda: {
            "accounts": [
                {
                    "id": "family-card",
                    "name": "Family Card",
                    "type": "credit_card",
                    "balance": {"amount": "83.42", "currency": "USD"},
                }
            ]
        },
        lambda account_id: {
            "transactions": [
                {
                    "id": "lunch-1",
                    "amount": "-18.75",
                    "date": "2026-08-27T18:00:00Z",
                    "merchant": "Cafe",
                    "description": "Shared lunch",
                    "shared_expense_id": "meal-7",
                    "isPending": False,
                }
            ]
        },
        observed_at=OBSERVED_AT,
    )

    snapshot = adapter.fetch_snapshot()

    assert snapshot.accounts[0].balance == 83.42
    assert snapshot.transactions[0].account_external_id == "family-card"
    assert snapshot.transactions[0].relation_hint == "lunchflow-shared:meal-7"
    assert snapshot.transactions[0].merchant == "Cafe"


def test_splitwise_balances_become_inflows_or_commitment_candidates():
    adapter = SplitwiseAdapter(
        lambda: {
            "friends": [
                {"id": 7, "first_name": "Avery", "balance": [{"currency_code": "USD", "amount": "42.50"}]},
                {"id": 8, "first_name": "Blake", "balance": [{"currency_code": "USD", "amount": "-19.25"}]},
            ]
        },
        lambda: {"expenses": []},
        current_user_id=99,
        observed_at=OBSERVED_AT,
    )

    snapshot = adapter.fetch_snapshot()

    assert snapshot.accounts[0].account_type == "reimbursement"
    assert [(item.external_id, item.amount) for item in snapshot.expected_inflows] == [
        ("friend:7", 42.5)
    ]
    assert [(item.external_id, item.amount) for item in snapshot.commitment_candidates] == [
        ("friend:8", 19.25)
    ]
    assert snapshot.commitment_candidates[0].name == "Splitwise — Blake"

