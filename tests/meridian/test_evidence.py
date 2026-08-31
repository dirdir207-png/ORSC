from datetime import datetime, timedelta, timezone

from meridian.evidence import EvidenceRepository
from meridian.repository import FinancialRepository
from meridian.storage import EncryptedBlobStore


class StaticKeyProvider:
    def get_or_create_key(self):
        return b"e" * 32


def _timestamp(offset_days=0):
    return (datetime.now(timezone.utc) + timedelta(days=offset_days)).isoformat()


def test_evidence_links_preserve_provenance_and_source_revocation(tmp_path):
    db_path = str(tmp_path / "meridian.db")
    repository = EvidenceRepository(db_path)
    item = repository.add_item(
        source_kind="email",
        source_id="message-7",
        content_hash="a" * 64,
        mime_type="application/pdf",
        size_bytes=120,
        expires_at=_timestamp(30),
        title="August statement",
    )
    link = repository.add_link(
        evidence_id=item.id,
        target_kind="transaction",
        target_id="42",
        relation="supports",
        provenance="page 2, total row",
    )

    assert repository.get_item(item.id) == item
    assert repository.list_links(item.id) == [link]

    assert repository.revoke_source("email", "message-7") == 1
    assert repository.get_item(item.id) is None
    audit_item = repository.get_item(item.id, include_inaccessible=True)
    assert audit_item is not None
    assert audit_item.revoked_at is not None
    assert repository.list_links(item.id) == [link]


def test_retention_deletes_blob_but_preserves_audit_and_financial_records(tmp_path):
    db_path = str(tmp_path / "meridian.db")
    graph = FinancialRepository(db_path)
    account = graph.upsert_account(
        provider="crew",
        external_id="checking",
        name="Checking",
        account_type="checking",
        balance=500,
    )
    store = EncryptedBlobStore(tmp_path / "blobs", StaticKeyProvider())
    blob = store.put(b"expired statement", mime_type="application/pdf")
    evidence = EvidenceRepository(db_path)
    item = evidence.add_item(
        source_kind="email",
        source_id="expired-message",
        content_hash=blob.content_hash,
        mime_type=blob.mime_type,
        size_bytes=blob.size_bytes,
        expires_at=_timestamp(-1),
    )

    swept = evidence.sweep_expired(store, as_of=_timestamp())

    assert swept == 1
    assert evidence.get_item(item.id) is None
    audit_item = evidence.get_item(item.id, include_inaccessible=True)
    assert audit_item is not None
    assert audit_item.content_deleted_at is not None
    assert graph.list_accounts() == [account]


def test_remove_links_for_target_keeps_items(tmp_path):
    db = str(tmp_path / "e.db")
    repo = EvidenceRepository(db)
    item = repo.add_item(source_kind="manual", source_id="seed-1",
                         content_hash="a" * 64, mime_type="text/plain", size_bytes=3)
    repo.add_link(evidence_id=item.id, target_kind="asset", target_id="7",
                  relation="supports", provenance="owner")
    repo.add_link(evidence_id=item.id, target_kind="asset", target_id="8",
                  relation="supports", provenance="owner")
    removed = repo.remove_links_for_target("asset", "7")
    assert removed == 1
    assert repo.list_links_for_target("asset", "7") == []
    assert len(repo.list_links_for_target("asset", "8")) == 1
    assert repo.get_item(item.id) is not None  # item untouched
