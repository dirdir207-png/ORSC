"""Tests for the Gmail -> evidence intake runner (R28/29 pilot).

Uses a fake transport (no live Gmail) so the pipeline is proven deterministic.
The real Gmail transport is separately covered by connector tests; here we
verify that fetched messages become evidence items via the document intake,
respect dedup, and quarantine empty/oversized bodies.
"""

import pytest

from meridian.connectors.gmail_read import GmailEvidence
from meridian.evidence import EvidenceRepository
from meridian.gmail_intake import ingest_gmail_recent


@pytest.fixture
def evidence_repo(tmp_path):
    return EvidenceRepository(str(tmp_path / "evidence.db"))


class FakeTransport:
    def __init__(self, messages):
        self._messages = messages

    def fetch_recent(self, *, max_results=20):
        return self._messages[:max_results]


def _msg(mid, subject, body, sender="bill@merchant.com", received="2026-09-05T12:00:00Z"):
    return GmailEvidence(
        message_id=mid, subject=subject, sender=sender,
        received_at=received, body_text=body, thread_id=None,
    )


def test_ingest_gmail_stores_messages_as_mail_evidence(evidence_repo):
    transport = FakeTransport([_msg("m1", "Your Eversource bill", "Amount due: $210.00 by Sep 20")])
    summary = ingest_gmail_recent(transport=transport, evidence_repo=evidence_repo, max_messages=5)

    assert summary["fetched"] == 1
    assert summary["stored"] == 1
    # The stored item is retrievable by its content hash (dedup key).
    import hashlib
    body = "Amount due: $210.00 by Sep 20"
    stored_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
    assert evidence_repo.get_by_content_hash(stored_hash) is not None
    assert summary["items"][0]["subject"] == "Your Eversource bill"


def test_ingest_gmail_dedups_on_duplicate(evidence_repo):
    transport = FakeTransport([_msg("m1", "Duplicate", "same body text content")])
    first = ingest_gmail_recent(transport=transport, evidence_repo=evidence_repo)
    second = ingest_gmail_recent(transport=transport, evidence_repo=evidence_repo)

    assert first["stored"] == 1
    assert second["duplicate"] == 1 and second["stored"] == 0


def test_ingest_gmail_quarantines_empty_body(evidence_repo):
    transport = FakeTransport([_msg("m1", "Empty", "   ")])
    summary = ingest_gmail_recent(transport=transport, evidence_repo=evidence_repo)
    assert summary["quarantined"] == 1
    assert summary["stored"] == 0


def test_ingest_gmail_handles_mixed_batch_and_never_leaks_body(evidence_repo):
    transport = FakeTransport(
        [
            _msg("m1", "Bill A", "Amount due $50"),
            _msg("m2", "", ""),  # empty -> quarantine
            _msg("m3", "Bill B", "Statement attached"),
        ]
    )
    summary = ingest_gmail_recent(transport=transport, evidence_repo=evidence_repo)

    assert summary["stored"] == 2
    assert summary["quarantined"] == 1
    # Only sanitized fields are exposed in the summary, never the body.
    assert all("body" not in item and "body_text" not in item for item in summary["items"])
