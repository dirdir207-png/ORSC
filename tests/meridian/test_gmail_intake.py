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


def test_link_mail_evidence_matches_transaction_by_amount(tmp_path):
    import sqlite3

    from meridian.evidence import EvidenceRepository
    from meridian.gmail_intake import link_mail_evidence_to_transactions

    db = str(tmp_path / "link.db")
    # A transaction with amount -92.75.
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE financial_transactions (
        id INTEGER PRIMARY KEY, amount REAL, merchant TEXT, description TEXT,
        account_id INTEGER, provider TEXT, external_id TEXT, currency TEXT,
        occurred_at TEXT, posted_at TEXT, status TEXT, raw_description TEXT,
        source_updated_at TEXT, classification_category TEXT, classification_kind TEXT,
        classification_confidence REAL, classification_rule_id TEXT, classification_evidence TEXT,
        classification_method TEXT, classification_provider TEXT, classification_model TEXT,
        classification_version INTEGER, synced_at TEXT, created_at TEXT, updated_at TEXT,
        occurred_at_valid INTEGER DEFAULT 1)""")
    conn.execute("INSERT INTO financial_transactions(id, amount) VALUES (40, -92.75)")
    conn.commit(); conn.close()

    class Tx:
        def __init__(self, id, amount): self.id = id; self.amount = amount

    repo = EvidenceRepository(str(tmp_path / "ev.db"))
    repo.add_item(source_kind="mail", source_id="m1", content_hash="a"*64, mime_type="text/plain", size_bytes=10, title="Urgent: $92.75 charged")

    created = link_mail_evidence_to_transactions(
        evidence_repo=repo, transactions=[Tx(40, -92.75)], evidence_id=1,
        subject="Urgent: $92.75 charged but no order confirmation",
    )

    assert created == 1
    assert len(repo.list_links_for_target("transaction", "40")) == 1


def test_link_mail_evidence_no_match_returns_zero(tmp_path):
    from meridian.evidence import EvidenceRepository
    from meridian.gmail_intake import link_mail_evidence_to_transactions

    class Tx:
        def __init__(self, id, amount): self.id = id; self.amount = amount

    repo = EvidenceRepository(str(tmp_path / "ev.db"))
    repo.add_item(source_kind="mail", source_id="m1", content_hash="b"*64, mime_type="text/plain", size_bytes=10, title="Welcome")

    created = link_mail_evidence_to_transactions(
        evidence_repo=repo, transactions=[Tx(40, -92.75)], evidence_id=1,
        subject="Welcome to Waypoint Budget",
    )
    assert created == 0


def test_ingest_icloud_recent_stores_mail_evidence(tmp_path):
    from meridian.connectors.icloud_mail import IcloudMailMessage
    from meridian.evidence import EvidenceRepository
    from meridian.gmail_intake import ingest_icloud_recent

    class FakeTransport:
        def fetch_recent(self, *, max_results=20):
            return [
                IcloudMailMessage(
                    message_id="<ic1@icloud.com>", subject="Your iCloud bill",
                    sender="billing@x.com", received_at="Fri, 05 Sep 2026 12:00:00 +0000",
                    body_text="Amount due $75.00", thread_id="<ic1@icloud.com>",
                )
            ]

    repo = EvidenceRepository(str(tmp_path / "evidence.db"))
    summary = ingest_icloud_recent(transport=FakeTransport(), evidence_repo=repo, max_messages=5)

    assert summary["stored"] == 1
    assert summary["items"][0]["subject"] == "Your iCloud bill"
    assert repo.get_by_content_hash(__import__("hashlib").sha256(b"Amount due $75.00").hexdigest()) is not None


def test_ingest_icloud_links_use_icloud_provenance(tmp_path):
    """iCloud amount-links must be labeled icloud:amount-match (not gmail)."""
    from meridian.connectors.icloud_mail import IcloudMailMessage
    from meridian.evidence import EvidenceRepository
    from meridian.gmail_intake import ingest_icloud_recent

    class FakeTransport:
        def fetch_recent(self, *, max_results=20):
            return [
                IcloudMailMessage(
                    message_id="<ic2@icloud.com>", subject="Your charge",
                    sender="billing@x.com", received_at="Fri, 05 Sep 2026 12:00:00 +0000",
                    body_text="Amount $92.75", thread_id="<ic2@icloud.com>",
                )
            ]

    class Tx:
        def __init__(self, txid, amount):
            self.id = txid
            self.amount = amount

    repo = EvidenceRepository(str(tmp_path / "evidence.db"))
    summary = ingest_icloud_recent(
        transport=FakeTransport(), evidence_repo=repo, max_messages=5,
        transactions=[Tx(40, -92.75)],
    )

    assert summary["linked"] == 1
    links = repo.list_links(int(summary["items"][0]["id"]))
    assert links, "expected at least one linked evidence link"
    assert all(link.provenance == "icloud:amount-match" for link in links)
