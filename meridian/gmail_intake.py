"""Gmail -> evidence intake runner (R28/29 pilot).

Fetches a bounded set of recent Gmail messages via the owner's OAuth token and
stores each as an evidence item (source_kind='mail') through the document-intake
pipeline. Read-only: never mutates Gmail; only stores the message body text as
evidence with sane size limits.

This is a pilot: it reads a small, recent slice and records how Gmail data
populates the evidence layer. It is intentionally conservative (no attachment
download, bounded count, quarantine on oversized/empty).
"""

from __future__ import annotations

from .connectors.gmail_read import GmailEvidence, GmailTransport
from .evidence import EvidenceRepository
from .ingest import IntakeRecord, QuarantineError, ingest_record


def ingest_gmail_recent(
    *,
    transport: GmailTransport,
    evidence_repo: EvidenceRepository,
    max_messages: int = 20,
) -> dict[str, object]:
    """Fetch recent Gmail messages and store each as evidence.

    Returns a sanitized summary: counts stored/duplicate/quarantined/error,
    plus the subject + source_id of each stored item (never the body).
    """
    stored: list[dict[str, str]] = []
    duplicate = 0
    quarantined = 0
    errors = 0

    messages: list[GmailEvidence] = transport.fetch_recent(max_results=max_messages)
    for msg in messages:
        if not msg.body_text.strip():
            quarantined += 1
            continue
        record = IntakeRecord(
            source_kind="mail",
            source_id=msg.message_id,
            blob=msg.body_text.encode("utf-8"),
            mime_type="text/plain",
            title=f"{msg.subject or 'Gmail message'}",
        )
        try:
            result = ingest_record(record, evidence_repo=evidence_repo)
        except QuarantineError:
            quarantined += 1
            continue
        except Exception:  # noqa: BLE001 - a single bad message must not stop the batch
            errors += 1
            continue
        if result.duplicate:
            duplicate += 1
            continue
        stored.append(
            {
                "id": str(result.item_id),
                "subject": msg.subject or "",
                "sender": msg.sender or "",
                "received_at": msg.received_at or "",
            }
        )

    return {
        "fetched": len(messages),
        "stored": len(stored),
        "duplicate": duplicate,
        "quarantined": quarantined,
        "errors": errors,
        "items": stored,
    }
