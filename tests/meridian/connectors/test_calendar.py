from meridian.connectors.calendar import ReadOnlyCalendarConnector


class FakeCalendarTransport:
    def __init__(self):
        self.scopes = None

    def configure(self, *, scopes):
        self.scopes = tuple(scopes)

    def list_events(self, *, cursor, time_min, time_max):
        return {
            "events": [
                {
                    "id": "event-1",
                    "start": "2026-09-10T09:00:00Z",
                    "end": "2026-09-10T10:00:00Z",
                    "summary": "Travel",
                    "description": "Private itinerary and confirmation code",
                    "attendees": ["private@example.com"],
                }
            ],
            "next_cursor": "next",
        }


def test_calendar_connector_uses_readonly_scope_and_minimum_fields():
    transport = FakeCalendarTransport()
    connector = ReadOnlyCalendarConnector(transport, max_history_days=30)

    batch = connector.poll(None, as_of="2026-09-01")

    assert transport.scopes == (
        "https://www.googleapis.com/auth/calendar.events.readonly",
    )
    assert batch.events[0].summary == "Travel"
    assert "Private itinerary" not in repr(batch)
    assert "private@example.com" not in repr(batch)
    assert not hasattr(connector, "create")
    assert not hasattr(connector, "update")
    assert not hasattr(connector, "delete")


def test_calendar_source_is_independently_revocable():
    connector = ReadOnlyCalendarConnector(FakeCalendarTransport())
    connector.revoke()

    assert connector.poll(None, as_of="2026-09-01").revoked is True
