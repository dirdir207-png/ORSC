"""Bounded, minimum-field, read-only calendar ingestion."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol

READ_ONLY_CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.events.readonly"


class CalendarTransport(Protocol):
    def configure(self, *, scopes: tuple[str, ...]) -> None: ...

    def list_events(
        self, *, cursor: str | None, time_min: str, time_max: str
    ) -> dict[str, object]: ...


@dataclass(frozen=True)
class CalendarEvent:
    id: str
    start: str
    end: str
    summary: str
    source_link: str


@dataclass(frozen=True)
class CalendarBatch:
    events: tuple[CalendarEvent, ...]
    cursor: str | None
    revoked: bool = False


class ReadOnlyCalendarConnector:
    def __init__(
        self,
        transport: CalendarTransport,
        *,
        max_history_days: int = 90,
        max_future_days: int = 365,
    ):
        self._transport = transport
        self._max_history_days = max_history_days
        self._max_future_days = max_future_days
        self._revoked = False
        self._seen_ids: set[str] = set()
        transport.configure(scopes=(READ_ONLY_CALENDAR_SCOPE,))

    def poll(self, cursor: str | None, *, as_of: str) -> CalendarBatch:
        if self._revoked:
            return CalendarBatch((), cursor, revoked=True)
        anchor = date.fromisoformat(as_of)
        payload = self._transport.list_events(
            cursor=cursor,
            time_min=(anchor - timedelta(days=self._max_history_days)).isoformat(),
            time_max=(anchor + timedelta(days=self._max_future_days)).isoformat(),
        )
        events = []
        for raw in payload.get("events", ()):
            event_id = str(raw["id"])
            if event_id in self._seen_ids:
                continue
            self._seen_ids.add(event_id)
            events.append(
                CalendarEvent(
                    event_id,
                    str(raw["start"]),
                    str(raw["end"]),
                    str(raw.get("summary") or "Event"),
                    f"calendar://event/{event_id}",
                )
            )
        next_cursor = payload.get("next_cursor")
        return CalendarBatch(tuple(events), str(next_cursor) if next_cursor else None)

    def revoke(self) -> None:
        self._revoked = True
        self._seen_ids.clear()
