from meridian.repository import FinancialRepository
from meridian.services.accounts import build_accounts


def test_accounts_group_by_financial_role_not_provider(tmp_path):
    repository = FinancialRepository(str(tmp_path / "accounts.db"))
    repository.upsert_account(
        provider="crew",
        external_id="checking",
        name="Checking",
        account_type="checking",
        balance=500,
    )
    repository.upsert_account(
        provider="simplefin",
        external_id="card",
        name="Rewards Card",
        account_type="credit",
        balance=-120,
    )
    repository.upsert_account(
        provider="crew",
        external_id="savings",
        name="Savings",
        account_type="savings",
        balance=1000,
    )

    result = build_accounts(repository)

    assert [group["role"] for group in result["groups"]] == [
        "cash",
        "savings",
        "liabilities",
    ]
    assert result["groups"][0]["accounts"][0]["name"] == "Checking"
    assert result["groups"][2]["accounts"][0]["name"] == "Rewards Card"
    assert all(
        "external_id" not in account
        for group in result["groups"]
        for account in group["accounts"]
    )


def test_accounts_include_reimbursements_and_sanitized_connections(tmp_path):
    repository = FinancialRepository(str(tmp_path / "accounts.db"))
    run = repository.begin_sync_run(
        provider="splitwise",
        connection_external_id="private-user-id",
        connection_name="Splitwise",
    )
    repository.upsert_account(
        provider="splitwise",
        external_id="user:99",
        name="Splitwise reimbursements",
        account_type="reimbursement",
        balance=42.5,
        connection_id=run.connection_id,
        source_updated_at="2026-08-29T12:00:00Z",
    )
    repository.upsert_reimbursement(
        provider="splitwise",
        external_id="friend:7",
        name="Splitwise — Avery",
        amount=42.5,
        currency="USD",
        source_updated_at="2026-08-29T12:00:00Z",
    )
    repository.finish_sync_run(
        run.id, status="complete", accounts_synced=1, transactions_synced=0, errors=0
    )

    result = build_accounts(repository)

    assert result["reimbursements"][0]["name"] == "Splitwise — Avery"
    assert result["connections"][0]["provider"] == "splitwise"
    assert result["connections"][0]["status"] == "healthy"
    assert "private-user-id" not in str(result)
