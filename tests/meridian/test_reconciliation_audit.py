from meridian.classify import ClassificationInput, classify_deterministic
from meridian.providers.base import (
    ExpectedInflow,
    NormalizedAccount,
    NormalizedTransaction,
    ProviderSnapshot,
)
from meridian.repository import FinancialRepository
from meridian.sync import sync_provider, sync_providers


class Adapter:
    def __init__(self, provider, snapshot):
        self.provider_name = provider
        self.connection_external_id = snapshot.connection_external_id
        self.connection_name = snapshot.connection_name
        self.snapshot = snapshot

    def fetch_snapshot(self):
        return self.snapshot


def _snapshot(provider, account_id, account_type, transactions):
    return ProviderSnapshot(
        connection_external_id=f"{provider}:{account_id}",
        connection_name=provider.title(),
        accounts=(NormalizedAccount(account_id, account_id, account_type, 0),),
        transactions=tuple(transactions),
    )


def test_fixture_audit_assigns_transfers_refunds_and_reimbursements_once(tmp_path):
    repository = FinancialRepository(str(tmp_path / "audit.db"))
    crew = _snapshot(
        "crew",
        "checking",
        "checking",
        (
            NormalizedTransaction(
                "card-payment-out",
                "checking",
                -75,
                "2026-08-28T10:00:00Z",
                "Card payment",
                "posted",
            ),
        ),
    )
    card = _snapshot(
        "simplefin",
        "card",
        "credit",
        (
            NormalizedTransaction(
                "card-payment-in",
                "card",
                75,
                "2026-08-28T10:05:00Z",
                "Payment received",
                "posted",
            ),
            NormalizedTransaction(
                "purchase",
                "card",
                -20,
                "2026-08-20T10:00:00Z",
                "Book shop",
                "posted",
            ),
            NormalizedTransaction(
                "refund",
                "card",
                20,
                "2026-08-21T10:00:00Z",
                "Refund from Book shop",
                "posted",
            ),
        ),
    )
    splitwise = _snapshot(
        "splitwise",
        "user:99",
        "reimbursement",
        (
            NormalizedTransaction(
                "expense:7",
                "user:99",
                18,
                "2026-08-22T10:00:00Z",
                "Shared dinner reimbursement",
                "posted",
                relation_hint="splitwise-expense:7",
            ),
        ),
    )

    sync_providers(
        (Adapter("crew", crew), Adapter("simplefin", card), Adapter("splitwise", splitwise)),
        repository,
    )

    transactions, _ = repository.list_transactions(limit=20)
    assignments = {item.external_id: item.classification_kind for item in transactions}
    assert assignments == {
        "card-payment-out": "transfer",
        "card-payment-in": "transfer",
        "purchase": "spend",
        "refund": "refund",
        "expense:7": "reimbursement",
    }
    relations = repository.list_transaction_relations()
    assert [(item.relation_type, item.source_transaction_id, item.related_transaction_id) for item in relations] == [
        ("credit_payment", 1, 2),
        ("refund", 3, 4),
    ]


def test_owner_rule_applies_to_later_synced_transactions(tmp_path):
    repository = FinancialRepository(str(tmp_path / "rules.db"))
    initial = _snapshot(
        "crew",
        "checking",
        "checking",
        (
            NormalizedTransaction(
                "coffee-1",
                "checking",
                -5,
                "2026-08-28T10:00:00Z",
                "Coffee",
                "posted",
                merchant="Corner Coffee",
            ),
        ),
    )
    sync_provider(Adapter("crew", initial), repository)
    first = repository.list_transactions()[0][0]
    repository.correct_classification(
        first.id, category="Dining", kind="spend", create_rule=True
    )
    later = _snapshot(
        "crew",
        "checking",
        "checking",
        (
            NormalizedTransaction(
                "coffee-2",
                "checking",
                -6,
                "2026-08-29T10:00:00Z",
                "Coffee",
                "posted",
                merchant="Corner Coffee",
            ),
        ),
    )

    sync_provider(Adapter("crew", later), repository)

    second = next(item for item in repository.list_transactions()[0] if item.external_id == "coffee-2")
    assert second.classification_category == "Dining"
    assert second.classification_method == "user_rule"


def test_create_rule_always_corrects_selected_high_confidence_transaction(tmp_path):
    repository = FinancialRepository(str(tmp_path / "correction.db"))
    account = repository.upsert_account(
        provider="crew", external_id="checking", name="Checking", account_type="checking", balance=0
    )
    transaction = repository.upsert_transaction(
        provider="crew",
        external_id="groceries",
        account_id=account.id,
        amount=-40,
        occurred_at="2026-08-29T10:00:00Z",
        description="Whole Foods",
        merchant="Whole Foods",
        status="posted",
    )
    repository.record_classification(
        transaction.id,
        classify_deterministic(
            ClassificationInput(transaction.id, -40, "Whole Foods", "Whole Foods", "checking", "2026-08-29T10:00:00Z")
        ),
    )

    repository.correct_classification(
        transaction.id, category="Household", kind="spend", create_rule=True
    )

    assert repository.get_transaction(transaction.id).classification_category == "Household"


def test_equal_amounts_without_transfer_evidence_remain_unlinked(tmp_path):
    repository = FinancialRepository(str(tmp_path / "ambiguous.db"))
    checking = _snapshot(
        "crew",
        "checking",
        "checking",
        (
            NormalizedTransaction(
                "payroll",
                "checking",
                50,
                "2026-08-29T10:00:00Z",
                "Payroll adjustment",
                "posted",
            ),
        ),
    )
    card = _snapshot(
        "simplefin",
        "card",
        "credit",
        (
            NormalizedTransaction(
                "purchase",
                "card",
                -50,
                "2026-08-29T11:00:00Z",
                "Grocery store",
                "posted",
            ),
        ),
    )

    sync_providers((Adapter("crew", checking), Adapter("simplefin", card)), repository)

    assert repository.list_transaction_relations() == []
    assignments = {
        item.external_id: item.classification_kind
        for item in repository.list_transactions()[0]
    }
    assert assignments == {"payroll": "income", "purchase": "spend"}


def test_multi_provider_fetch_failure_is_attempted_once_and_recorded_failed(tmp_path):
    repository = FinancialRepository(str(tmp_path / "failure.db"))

    class FailingAdapter:
        provider_name = "simplefin"
        connection_external_id = "simplefin-access"
        connection_name = "SimpleFin"

        def __init__(self):
            self.calls = 0

        def fetch_snapshot(self):
            self.calls += 1
            raise OSError("offline")

    adapter = FailingAdapter()

    reports = sync_providers((adapter,), repository)

    assert adapter.calls == 1
    assert reports[0].status == "failed"


def test_expected_reimbursements_are_idempotent_and_keep_provider_freshness(tmp_path):
    repository = FinancialRepository(str(tmp_path / "reimbursements.db"))
    snapshot = ProviderSnapshot(
        connection_external_id="user:99",
        connection_name="Splitwise",
        accounts=(
            NormalizedAccount("user:99", "Splitwise reimbursements", "reimbursement", 42.5),
        ),
        transactions=(),
        expected_inflows=(
            ExpectedInflow(
                "friend:7",
                "Splitwise — Avery",
                42.5,
                "USD",
                "2026-08-29T12:00:00Z",
            ),
        ),
    )
    adapter = Adapter("splitwise", snapshot)

    sync_providers((adapter,), repository)
    sync_providers((adapter,), repository)

    reimbursements = repository.list_reimbursements()
    assert len(reimbursements) == 1
    assert reimbursements[0].provider == "splitwise"
    assert reimbursements[0].external_id == "friend:7"
    assert reimbursements[0].amount == 42.5
    assert reimbursements[0].source_updated_at == "2026-08-29T12:00:00Z"
