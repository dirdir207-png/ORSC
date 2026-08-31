import pytest

from meridian.providers.base import (
    NormalizedAccount,
    NormalizedTransaction,
    ProviderSnapshot,
)
from meridian.reconcile import reconcile
from meridian.repository import FinancialRepository
from meridian.sync import sync_provider, sync_providers


class SnapshotAdapter:
    def __init__(self, provider_name, snapshot):
        self.provider_name = provider_name
        self.connection_external_id = snapshot.connection_external_id
        self.connection_name = snapshot.connection_name
        self.snapshot = snapshot

    def fetch_snapshot(self):
        return self.snapshot


@pytest.fixture
def repository(tmp_path):
    return FinancialRepository(str(tmp_path / "financial.db"))


def _snapshot(provider, account_id, transactions):
    return ProviderSnapshot(
        connection_external_id=f"{provider}-connection",
        connection_name=provider.title(),
        accounts=(
            NormalizedAccount(
                external_id=account_id,
                name=account_id,
                account_type="checking" if account_id == "checking" else "credit",
                balance=0,
                source_updated_at="2026-08-29T12:00:00Z",
            ),
        ),
        transactions=tuple(transactions),
    )


def test_reconcile_links_explicit_owned_transfer_pair(repository):
    snapshot = _snapshot(
        "simplefin",
        "checking",
        (
            NormalizedTransaction(
                external_id="out",
                account_external_id="checking",
                amount=-50,
                occurred_at="2026-08-28T10:00:00Z",
                description="Transfer",
                status="posted",
                relation_hint="owned:1",
            ),
            NormalizedTransaction(
                external_id="in",
                account_external_id="checking",
                amount=50,
                occurred_at="2026-08-28T10:00:30Z",
                description="Transfer",
                status="posted",
                relation_hint="owned:1",
            ),
        ),
    )
    sync_provider(SnapshotAdapter("simplefin", snapshot), repository)

    report = reconcile(snapshot, repository)

    assert report.relations_created == 1
    assert report.ambiguous == 0
    assert repository.list_transaction_relations()[0].relation_type == "owned_transfer"


def test_reconcile_detects_cross_provider_credit_payment_without_double_counting(repository):
    checking = _snapshot(
        "crew",
        "checking",
        (
            NormalizedTransaction(
                external_id="crew-payment",
                account_external_id="checking",
                amount=-75,
                occurred_at="2026-08-28T10:00:00Z",
                description="Card payment",
                status="posted",
            ),
        ),
    )
    card = _snapshot(
        "simplefin",
        "card",
        (
            NormalizedTransaction(
                external_id="card-payment",
                account_external_id="card",
                amount=75,
                occurred_at="2026-08-28T10:10:00Z",
                description="Payment received",
                status="posted",
            ),
        ),
    )
    sync_provider(SnapshotAdapter("crew", checking), repository)
    sync_provider(SnapshotAdapter("simplefin", card), repository)

    report = reconcile(card, repository)

    assert report.relations_created == 1
    assert repository.list_transaction_relations()[0].relation_type == "credit_payment"


def test_reconcile_is_idempotent_and_leaves_ambiguous_matches_unlinked(repository):
    card = _snapshot(
        "simplefin",
        "card",
        (
            NormalizedTransaction(
                external_id="refund",
                account_external_id="card",
                amount=20,
                occurred_at="2026-08-28T10:00:00Z",
                description="Refund",
                status="posted",
            ),
        ),
    )
    for external_id in ("purchase-a", "purchase-b"):
        purchase = _snapshot(
            "crew",
            "checking",
            (
                NormalizedTransaction(
                    external_id=external_id,
                    account_external_id="checking",
                    amount=-20,
                    occurred_at="2026-08-28T09:00:00Z",
                    description="Purchase",
                    status="posted",
                ),
            ),
        )
        sync_provider(SnapshotAdapter("crew", purchase), repository)
    sync_provider(SnapshotAdapter("simplefin", card), repository)

    first = reconcile(card, repository)
    second = reconcile(card, repository)

    assert first.ambiguous == 1
    assert second.ambiguous == 1
    assert repository.list_transaction_relations() == []


def test_multi_provider_sync_upserts_splitwise_commitment_candidates(repository):
    from meridian.providers.base import CommitmentCandidate

    snapshot = ProviderSnapshot(
        connection_external_id="user:99",
        connection_name="Splitwise",
        accounts=(
            NormalizedAccount(
                external_id="user:99",
                name="Splitwise reimbursements",
                account_type="reimbursement",
                balance=-19.25,
                source_updated_at="2026-08-29T12:00:00Z",
            ),
        ),
        transactions=(),
        commitment_candidates=(
            CommitmentCandidate("friend:8", "Splitwise — Blake", 19.25),
        ),
    )
    adapter = SnapshotAdapter("splitwise", snapshot)

    sync_providers((adapter,), repository)
    sync_providers((adapter,), repository)

    with repository._connect() as connection:
        rows = connection.execute(
            "SELECT name, amount, legacy_source, legacy_id FROM commitments"
        ).fetchall()
    assert [tuple(row) for row in rows] == [
        ("Splitwise — Blake", 19.25, "splitwise", "friend:8")
    ]
