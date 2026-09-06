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


def test_ingest_all_gmail_accounts_iterates_each_token(tmp_path, monkeypatch):
    from meridian.evidence import EvidenceRepository
    from meridian.gmail_intake import ingest_all_gmail_accounts

    db = str(tmp_path / "multi.db")
    # Store two fake gmail tokens.
    import sqlite3
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE IF NOT EXISTS oauth_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL,
        account_email TEXT NOT NULL, access_token TEXT NOT NULL,
        refresh_token TEXT NOT NULL, expires_at TEXT, created_at TEXT NOT NULL,
        UNIQUE (kind, account_email))""")
    conn.execute("INSERT INTO oauth_tokens(kind,account_email,access_token,refresh_token,created_at) VALUES('gmail','a@gmail.com','at-a','rt-a','2026-01-01')")
    conn.execute("INSERT INTO oauth_tokens(kind,account_email,access_token,refresh_token,created_at) VALUES('gmail','b@gmail.com','at-b','rt-b','2026-01-01')")
    conn.commit(); conn.close()

    class FakeClient:
        def refresh(self, rt):
            return {"access_token": "fresh-" + rt}

    # Monkeypatch GmailTransport.fetch_recent to avoid live network.
    from meridian import gmail_intake as gi
    from meridian.connectors.gmail_read import GmailEvidence
    calls = []
    def fake_fetch(self, *, max_results=20):
        calls.append(self._access_token)
        return [GmailEvidence(message_id=f"m-{self._access_token}", subject=f"Subject {self._access_token}", sender="x@y.z", received_at="2026-09-05T00:00:00Z", body_text=f"Bill amount due $50 for {self._access_token}")]
    monkeypatch.setattr(gi.GmailTransport, "fetch_recent", fake_fetch)

    repo = EvidenceRepository(str(tmp_path / "evidence.db"))
    summary = ingest_all_gmail_accounts(db_path=db, evidence_repo=repo, token_client=FakeClient(), max_messages_per_account=5)

    assert summary["total_stored"] == 2
    assert len(summary["accounts"]) == 2
    assert calls == ["at-a", "at-b"]  # stored token used; refresh fires only on 401
