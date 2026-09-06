"""R28/R29: document intake pipeline — mail/manual blob → extraction → evidence.

Contract:
- Content-addressed: duplicate receipts never double-count as bills (sha256 id).
- Malformed/oversized/encrypted → quarantine (no unsafe parse fallback).
- Extracted fields carry provenance/confidence; user corrections persist and
  do not get overwritten by re-ingest of identical content.
- Evidence removal invalidates dependent suggestions without touching source
  bank history (memory derived from evidence, never source-merged).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone

from .documents.extract import extract_document


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class QuarantineError(RuntimeError):
    """Malformed/oversized/encrypted intake is quarantined, never parsed unsafely."""


@dataclass(frozen=True)
class IntakeResult:
    item_id: int
    content_hash: str
    document_type: str
    extracted: dict
    duplicate: bool = False
    quarantined: bool = False


@dataclass(frozen=True)
class IntakeRecord:
    source_kind: str          # mail | upload | calendar
    source_id: str
    blob: bytes
    mime_type: str
    title: str | None = None
    sender: str | None = None  # mail sender address (for biller matching)
    max_bytes: int = 8 * 1024 * 1024

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.blob).hexdigest()


def ingest_record(
    record: IntakeRecord,
    *,
    evidence_repo,
    blob_store=None,
    extraction_limit_bytes: int = 8 * 1024 * 1024,
) -> IntakeResult:
    """One intake step: validate → dedup → extract → store evidence.

    When ``blob_store`` is provided, the raw content is also persisted to the
    encrypted blob store so the evidence content can later be retrieved (opening
    an invoice link needs the decrypted blob, not just the metadata row).
    """
    if len(record.blob) > extraction_limit_bytes:
        raise QuarantineError("intake exceeds size limit")
    if not record.blob:
        raise QuarantineError("empty intake")
    if (
        not record.mime_type.startswith("text/")
        and b"%" in record.blob[:16]
        and record.mime_type.endswith("pdf")
    ):
        raise QuarantineError("possible encrypted PDF; no unsafe parse fallback")

    existing = evidence_repo.get_by_content_hash(record.content_hash) if hasattr(evidence_repo, "get_by_content_hash") else None
    if existing is not None:
        # Still persist the blob on a duplicate (a prior run may have created the
        # metadata row before blob storage was wired, leaving the content missing).
        if blob_store is not None:
            try:
                blob_store.put(record.blob, mime_type=record.mime_type)
            except Exception:  # noqa: BLE001 - best-effort
                pass
        return IntakeResult(
            item_id=existing.id, content_hash=record.content_hash,
            document_type="duplicate", extracted={}, duplicate=True,
        )

    try:
        doc = extract_document(record.blob, mime_type=record.mime_type)
    except Exception as exc:  # noqa: BLE001 - quarantine any parse failure
        raise QuarantineError(f"parse failure: {type(exc).__name__}") from exc

    item = evidence_repo.add_item(
        source_kind=record.source_kind,
        source_id=record.source_id,
        content_hash=record.content_hash,
        mime_type=record.mime_type,
        size_bytes=len(record.blob),
        expires_at=None,
        title=record.title or doc.document_type,
        sender=record.sender,
    )
    # Persist the encrypted blob so the evidence content is retrievable.
    if blob_store is not None:
        try:
            blob_store.put(record.blob, mime_type=record.mime_type)
        except Exception:  # noqa: BLE001 - blob persistence is best-effort
            pass
    facts = [
        {
            "field": f.field,
            "value": f.value,
            "confidence": f.confidence,
            "provenance": f"page {f.provenance.page} {f.provenance.region}: {f.provenance.excerpt}",
        }
        for f in doc.facts
    ]
    return IntakeResult(
        item_id=item.id,
        content_hash=record.content_hash,
        document_type=doc.document_type,
        extracted={"facts": facts},
    )
