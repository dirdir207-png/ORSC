"""Tests for the read-only Gmail transport (no live Gmail).

Mocks HTTP responses so body decoding, header extraction, and 401->refresh
retry are proven without hitting the Gmail API.
"""

import base64

import pytest

from meridian.connectors.gmail_read import GmailReadError, GmailTransport


def _b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode("utf-8")).decode("ascii").rstrip("=")


class FakeResponse:
    def __init__(self, status_code, json_body=None, text_body=""):
        self.status_code = status_code
        self._json = json_body or {}
        self.text = text_body

    def json(self):
        return self._json


class FakeRequests:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def get(self, url, headers=None, params=None, timeout=None):
        self.calls.append((url, params))
        return self._responses.pop(0)


def _message_rows(payload):
    """A minimal Gmail message-get payload with subject/from/date + body."""
    return {
        "id": "m1",
        "threadId": "t1",
        "internalDate": "1757000000000",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Your Eversource bill"},
                {"name": "From", "value": "billing@eversource.com"},
                {"name": "Date", "value": "Fri, 05 Sep 2026 12:00:00 +0000"},
            ],
            "parts": [
                {"body": {"data": _b64("Amount due: $210.00 by Sep 20")}},
            ],
        },
    }


def test_gmail_transport_decodes_body_and_headers():
    req = FakeRequests([FakeResponse(200, _message_rows(None))])
    t = GmailTransport(access_token="abc", refresh=None, timeout_seconds=2)
    t._requests = req

    msg = t.fetch_message("m1")

    assert msg.subject == "Your Eversource bill"
    assert msg.sender == "billing@eversource.com"
    assert "Amount due: $210.00" in msg.body_text
    assert req.calls[0][0].endswith("/messages/m1")


def test_gmail_transport_refreshes_once_on_401():
    refreshed = {"access_token": "new-token"}
    refresh_calls = []

    def refresh():
        refresh_calls.append(1)
        return refreshed

    req = FakeRequests([FakeResponse(401), FakeResponse(200, _message_rows(None))])
    t = GmailTransport(access_token="stale", refresh=refresh, timeout_seconds=2)
    t._requests = req

    msg = t.fetch_message("m1")

    assert msg.subject == "Your Eversource bill"
    assert len(refresh_calls) == 1
    # Retried with the refreshed token.
    assert req.calls[1][0].endswith("/messages/m1")


def test_gmail_transport_raises_on_non_401_error():
    req = FakeRequests([FakeResponse(403, {"error": {"message": "insufficient scopes"}})])
    t = GmailTransport(access_token="abc", refresh=None, timeout_seconds=2)
    t._requests = req

    with pytest.raises(GmailReadError):
        t.fetch_message("m1")


def test_gmail_transport_list_message_ids():
    req = FakeRequests([FakeResponse(200, {"messages": [{"id": "m1"}, {"id": "m2"}]})])
    t = GmailTransport(access_token="abc", timeout_seconds=2)
    t._requests = req

    ids = t.list_message_ids(max_results=5)

    assert [i["id"] for i in ids] == ["m1", "m2"]
    assert req.calls[0][0].endswith("/messages")
    assert req.calls[0][1] == {"maxResults": 5}
