import pytest

from meridian.classify import (
    AssignmentRule,
    ClassificationInput,
    classify_deterministic,
)
from meridian.providers.base import (
    NormalizedAccount,
    NormalizedTransaction,
    ProviderSnapshot,
)
from meridian.repository import FinancialRepository
from meridian.sync import sync_provider


@pytest.fixture
def repository(tmp_path):
    return FinancialRepository(str(tmp_path / "financial.db"))


def _transaction(**overrides):
    values = {
        "id": 1,
        "amount": -12.5,
        "description": "Coffee shop",
        "merchant": "Corner Coffee",
        "account_type": "checking",
        "occurred_at": "2026-08-29T10:00:00Z",
    }
    values.update(overrides)
    return ClassificationInput(**values)


def test_user_rule_outranks_transfer_and_merchant_rules():
    user_rule = AssignmentRule(
        id="user:coffee",
        category="Shared household",
        kind="reimbursement",
        merchant_pattern="corner coffee",
    )

    result = classify_deterministic(
        _transaction(relation_type="owned_transfer"),
        user_rules=(user_rule,),
    )

    assert result.rule_id == "user:coffee"
    assert result.method == "user_rule"
    assert result.kind == "reimbursement"


def test_owned_transfer_and_credit_payment_are_not_spending():
    owned_transfer = classify_deterministic(
        _transaction(relation_type="owned_transfer")
    )
    credit_payment = classify_deterministic(
        _transaction(
            description="Payment to credit card",
            account_type="checking",
            relation_type="credit_payment",
        )
    )

    assert owned_transfer.kind == "transfer"
    assert credit_payment.kind == "transfer"
    assert owned_transfer.category == "Transfers"
    assert owned_transfer.confidence == 1.0


def test_refunds_and_known_merchants_have_explainable_assignments():
    refund = classify_deterministic(
        _transaction(amount=12.5, description="Refund from Corner Coffee")
    )
    groceries = classify_deterministic(
        _transaction(merchant="Whole Foods Market", description="WHOLE FOODS 102")
    )

    assert refund.kind == "refund"
    assert "positive amount" in refund.evidence
    assert groceries.category == "Groceries"
    assert groceries.rule_id == "merchant:whole-foods"


def test_recurrence_detects_stable_merchant_interval():
    history = (
        _transaction(id=2, occurred_at="2026-06-29T10:00:00Z"),
        _transaction(id=3, occurred_at="2026-07-29T10:00:00Z"),
    )

    result = classify_deterministic(_transaction(), history=history)

    assert result.rule_id == "recurrence:merchant-monthly"
    assert result.evidence == "same merchant observed on a stable 25–35 day interval"


def test_fallback_assigns_every_transaction_without_mutating_input():
    transaction = _transaction(merchant=None, description="Unknown debit")

    result = classify_deterministic(transaction)

    assert result.kind == "spend"
    assert result.category == "Uncategorized"
    assert result.method == "fallback"
    assert transaction.merchant is None


def test_record_classification_preserves_prior_assignment(repository):
    account = repository.upsert_account(
        provider="crew",
        external_id="checking",
        name="Checking",
        account_type="checking",
        balance=100,
    )
    transaction = repository.upsert_transaction(
        provider="crew",
        external_id="coffee",
        account_id=account.id,
        amount=-12.5,
        occurred_at="2026-08-29T10:00:00Z",
        description="Coffee",
        status="posted",
    )
    first = classify_deterministic(_transaction())
    corrected = classify_deterministic(
        _transaction(),
        user_rules=(
            AssignmentRule(
                id="user:coffee",
                category="Dining",
                kind="spend",
                merchant_pattern="corner coffee",
            ),
        ),
    )

    repository.record_classification(transaction.id, first)
    repository.record_classification(transaction.id, corrected)

    updated = repository.get_transaction(transaction.id)
    assert updated.classification_category == "Dining"
    assert updated.classification_rule_id == "user:coffee"
    assert repository.list_classification_history(transaction.id)[0]["category"] == first.category


def test_sync_assigns_deterministic_classification(repository):
    snapshot = ProviderSnapshot(
        connection_external_id="crew-household",
        connection_name="Crew",
        accounts=(NormalizedAccount("checking", "Checking", "checking", 100),),
        transactions=(
            NormalizedTransaction(
                external_id="groceries",
                account_external_id="checking",
                amount=-42,
                occurred_at="2026-08-29T10:00:00Z",
                description="WHOLE FOODS 102",
                merchant="Whole Foods Market",
                status="posted",
            ),
        ),
    )

    class Adapter:
        provider_name = "crew"
        connection_external_id = "crew-household"
        connection_name = "Crew"

        @staticmethod
        def fetch_snapshot():
            return snapshot

    sync_provider(Adapter(), repository)

    transactions, _ = repository.list_transactions()
    assert transactions[0].classification_category == "Groceries"
    assert transactions[0].classification_method == "deterministic"
