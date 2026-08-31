"""Minimum-scope, cursor-based read-only mail ingestion."""

from dataclasses import dataclass
from typing import Protocol

READ_ONLY_GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


class MailTransport(Protocol):
    def configure(self, *, scopes: tuple[str, ...]) -> None: ...

    def list_messages(self, *, cursor: str | None) -> dict[str, object]: ...


@dataclass(frozen=True)
class MailAttachment:
    id: str
    filename: str


@dataclass(frozen=True)
class MailMessage:
    id: str
    thread_id: str | None
    received_at: str
    subject: str
    sender: str
    attachments: tuple[MailAttachment, ...]
    source_link: str


@dataclass(frozen=True)
class MailBatch:
    messages: tuple[MailMessage, ...]
    cursor: str | None
    revoked: bool = False


class ReadOnlyMailConnector:
    """Expose polling only; mutation methods deliberately do not exist."""

    def __init__(self, transport: MailTransport):
        self._transport = transport
        self._seen_ids: set[str] = set()
        self._revoked = False
        transport.configure(scopes=(READ_ONLY_GMAIL_SCOPE,))

    def poll(self, cursor: str | None) -> MailBatch:
        if self._revoked:
            return MailBatch((), cursor, revoked=True)
        payload = self._transport.list_messages(cursor=cursor)
        messages = []
        for raw in payload.get("messages", ()):
            message_id = str(raw["id"])
            if message_id in self._seen_ids:
                continue
            self._seen_ids.add(message_id)
            attachments = tuple(
                MailAttachment(
                    str(item["id"]), str(item.get("filename") or "attachment")
                )
                for item in raw.get("attachments", ())
            )
            messages.append(
                MailMessage(
                    id=message_id,
                    thread_id=str(raw["thread_id"]) if raw.get("thread_id") else None,
                    received_at=str(raw["received_at"]),
                    subject=str(raw.get("subject") or ""),
                    sender=str(raw.get("from") or ""),
                    attachments=attachments,
                    source_link=f"gmail://message/{message_id}",
                )
            )
        next_cursor = payload.get("next_cursor")
        return MailBatch(tuple(messages), str(next_cursor) if next_cursor else None)

    def revoke(self) -> None:
        self._revoked = True
        self._seen_ids.clear()
