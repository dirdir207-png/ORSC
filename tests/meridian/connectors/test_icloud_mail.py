"""Tests for the read-only iCloud Mail transport (no live iCloud).

Mocks the IMAP layer so login, read-only SELECT, fetch, body decode, and
close/logout are proven without touching a real mailbox.
"""

import pytest

from meridian.connectors.icloud_mail import IcloudMailReadError, IcloudMailTransport


class _FakeIMAP:
    def __init__(self, fetch_payloads=None):
        self.selected = None
        self.closed = False
        self.logged_out = False
        self._fetch_payloads = fetch_payloads or []

    def select(self, mailbox, readonly=False):
        self.selected = (mailbox, readonly)
        return ("OK", None)

    def search(self, charset, criteria):
        # Simulate exactly 1 message so the test is deterministic.
        return ("OK", [b"1"])

    def fetch(self, num, what):
        # Return a tuple in the RFC822 format imaplib gives back. A single
        # configured payload is returned for every fetch call in the test.
        payload = self._fetch_payloads[0] if self._fetch_payloads else None
        if payload is None:
            raise RuntimeError("no payload for fetch")
        return ("OK", [(b"(RFC822 {size}", payload)])

    def close(self):
        self.closed = True

    def logout(self):
        self.logged_out = True


def _message_bytes(subject, sender, date, body):
    msg = (
        f"From: {sender}\r\nTo: x@y.z\r\nSubject: {subject}\r\nDate: {date}\r\n"
        f"Message-ID: <abc@{sender.split('@')[-1] if '@' in sender else 'y.z'}>\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n\r\n"
        f"{body}"
    )
    return msg.encode("utf-8")


class _Connector(IcloudMailTransport):
    def __init__(self, fetch_payloads=None):
        super().__init__(username="emilyparker", app_password="abcd-efgh-ijkl-mnop")
        self._fetch_payloads = fetch_payloads or []
        self.conn = None

    def _connect(self):
        self.conn = _FakeIMAP(self._fetch_payloads)
        return self.conn


def test_icloud_requires_credentials():
    with pytest.raises(IcloudMailReadError):
        IcloudMailTransport(username="", app_password="")


def test_icloud_fetch_recent_reads_messages_and_decodes_body():
    fetch = [
        _message_bytes("Your iCloud bill", "billing@x.com", "Fri, 05 Sep 2026 12:00:00 +0000", "Amount due $50"),
    ]
    t = _Connector(fetch)
    msgs = t.fetch_recent(max_results=5)
    assert len(msgs) == 1
    assert msgs[0].subject == "Your iCloud bill"
    assert msgs[0].sender == "billing@x.com"
    assert "Amount due $50" in msgs[0].body_text


def test_icloud_selects_inbox_readonly_and_closes():
    t = _Connector([_message_bytes("s", "a@b.c", "Fri, 05 Sep 2026 12:00:00 +0000", "hi")])
    t.fetch_recent(max_results=5)
    # Read-only SELECT (EXAMINE-equivalent via readonly=True) and clean close.
    assert t.conn.selected == ("INBOX", True)
    assert t.conn.closed is True
    assert t.conn.logged_out is True


def test_icloud_fetch_error_raises_read_error():
    t = _Connector([])  # no payloads -> fetch raises
    with pytest.raises(IcloudMailReadError):
        t.fetch_recent(max_results=5)
