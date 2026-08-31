from meridian.connectors.email import ReadOnlyMailConnector


class FakeMailTransport:
    def __init__(self):
        self.scopes = None
        self.calls = []

    def configure(self, *, scopes):
        self.scopes = tuple(scopes)

    def list_messages(self, *, cursor):
        self.calls.append(cursor)
        return {
            "messages": [
                {
                    "id": "m-1",
                    "thread_id": "t-1",
                    "received_at": "2026-08-29T10:00:00Z",
                    "subject": "Statement ready",
                    "from": "bank@example.com",
                    "attachments": [{"id": "a-1", "filename": "statement.pdf"}],
                    "labels": ["INBOX"],
                    "oauth_token": "must-not-leak",
                }
            ],
            "next_cursor": "cursor-2",
        }


def test_mail_connector_is_read_only_allowlisted_and_cursor_idempotent():
    transport = FakeMailTransport()
    connector = ReadOnlyMailConnector(transport)

    first = connector.poll(None)
    second = connector.poll(first.cursor)

    assert transport.scopes == ("https://www.googleapis.com/auth/gmail.readonly",)
    assert [message.id for message in first.messages] == ["m-1"]
    assert second.messages == ()
    assert first.messages[0].source_link == "gmail://message/m-1"
    assert "oauth_token" not in repr(first)
    assert transport.calls == [None, "cursor-2"]
    assert not hasattr(connector, "send")
    assert not hasattr(connector, "delete")
    assert not hasattr(connector, "modify")


def test_mail_connector_revocation_stops_access():
    connector = ReadOnlyMailConnector(FakeMailTransport())
    connector.revoke()

    batch = connector.poll(None)

    assert batch.revoked is True
    assert batch.messages == ()
