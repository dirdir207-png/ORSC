"""Tests for R28/R29: document intake pipeline + evidence-linked memory."""

import pytest

from meridian.connectors.google_auth import OAuthTokenStore  # noqa: F401  (importable)
from meridian.evidence import EvidenceRepository
from meridian.ingest import IntakeRecord, QuarantineError, ingest_record


def _repo(tmp_path):
    return EvidenceRepository(str(tmp_path / "e.db"))


def test_duplicate_receipt_not_double_counted(tmp_path):
    repo = _repo(tmp_path)
    blob = b"Bank statement total: $123.45"
    r1 = ingest_record(IntakeRecord("mail", "m1", blob, "text/plain", "statement"), evidence_repo=repo)
    r2 = ingest_record(IntakeRecord("mail", "m1", blob, "text/plain", "statement"), evidence_repo=repo)
    assert r1.duplicate is False
    assert r2.duplicate is True
    assert r2.item_id == r1.item_id


def test_quarantine_oversized_and_elemental_cases(tmp_path):
    repo = _repo(tmp_path)
    with pytest.raises(QuarantineError):
        ingest_record(IntakeRecord("upload", "u1", b"x" * (9 * 1024 * 1024), "text/plain"), evidence_repo=repo, extraction_limit_bytes=8 * 1024 * 1024)
    with pytest.raises(QuarantineError):
        ingest_record(IntakeRecord("upload", "u2", b"", "text/plain"), evidence_repo=repo)
    with pytest.raises(QuarantineError):
        ingest_record(IntakeRecord("upload", "u3", b"%PDF-1.7 encrypted", "application/pdf"), evidence_repo=repo)


def test_extraction_produces_provenance_facts(tmp_path):
    repo = _repo(tmp_path)
    blob = b"Amount due: $42.00\nStatement total: $42.00"
    result = ingest_record(IntakeRecord("mail", "m1", blob, "text/plain", "bil statement"), evidence_repo=repo)
    assert result.document_type
    facts = result.extracted["facts"]
    assert facts  # at least one labeled amount captured
    assert all("confidence" in f and "provenance" in f for f in facts)


def test_removing_evidence_does_not_touch_source_history(tmp_path):
    from meridian.db import run_migrations

    db = str(tmp_path / "full.db")
    run_migrations(db)
    repo = EvidenceRepository(db)
    blob = b"Renewal amount: $12.00"
    result = ingest_record(IntakeRecord("mail", "m", blob, "text/plain", "renewal"), evidence_repo=repo)
    # Revoke the evidence (owner removes it) — evidence gone, source untouched.
    with repo._connect() as conn:
        conn.execute("UPDATE evidence_items SET revoked_at=? WHERE id=?", ("2026-09-05T00:00:00Z", result.item_id))
        conn.commit()
    assert repo.get_by_content_hash(result.content_hash) is None
    assert repo.get_item(result.item_id, include_inaccessible=True) is not None  # history preserved
