"""Read-only iCloud Mail transport for evidence intake.

Fetches recent iCloud Mail messages over IMAP using the owner's app-specific
password. iCloud Mail does not use OAuth (unlike Gmail), so this uses the
standard IMAP path the owner enables via Apple's app-specific-password flow
(Apple ID -> Sign-In & Security -> App-Specific Passwords).

READ-ONLY: only SELECTs the inbox, fetches headers + body text, and closes
without logout-mutation. Never sends, deletes, moves, or flags a message.

Credential: ICLOUD_MAIL_USERNAME (the iCloud mailbox, e.g. emilyparker — NOT the
full @icloud.com address) + ICLOUD_MAIL_APP_PASSWORD (the xxxx-xxxx-xxxx-xxxx
app-specific password). Never logged or returned.
"""

from __future__ import annotations

import email
import os
from dataclasses import dataclass
from email.header import decode_header, make_header
from typing import Optional

IMAP_HOST = "imap.mail.me.com"
IMAP_PORT = 993

DEFAULT_USERNAME = ""  # owner-set via env; never guessed
DEFAULT_APP_PASSWORD = ""


class IcloudMailReadError(RuntimeError):
    """An iCloud Mail read failed; callers decide whether to quarantine or skip."""


@dataclass(frozen=True)
class IcloudMailMessage:
    message_id: str
    subject: str
    sender: str
    received_at: str
    body_text: str
    thread_id: Optional[str] = None


def _decode_header_value(raw: str) -> str:
    """Decode RFC 2047 encoded header text (e.g. '=?UTF-8?Q?...?=')."""
    if not raw:
        return ""
    try:
        return str(make_header(decode_header(raw)))
    except Exception:  # noqa: BLE001 - header decoding is best-effort
        return raw


def _decode_body(payload: bytes, content_type: str = "text/plain") -> str:
    """Decode a message body (best-effort) to UTF-8 text."""
    try:
        charset = "utf-8"
        # Prefer a charset hint if present.
        return payload.decode(charset, errors="replace")
    except Exception:  # noqa: BLE001
        return payload.decode("utf-8", errors="replace")


class IcloudMailTransport:
    """Minimal read-only iCloud Mail transport (IMAP, app-specific password)."""

    def __init__(
        self,
        *,
        username: Optional[str] = None,
        app_password: Optional[str] = None,
        host: str = IMAP_HOST,
        port: int = IMAP_PORT,
    ):
        import imaplib

        self._imaplib = imaplib
        self._username = username or os.environ.get("ICLOUD_MAIL_USERNAME", DEFAULT_USERNAME)
        self._app_password = app_password or os.environ.get(
            "ICLOUD_MAIL_APP_PASSWORD", DEFAULT_APP_PASSWORD
        )
        self._host = host
        self._port = port
        if not self._username or not self._app_password:
            raise IcloudMailReadError(
                "iCloud Mail is not configured (set ICLOUD_MAIL_USERNAME and ICLOUD_MAIL_APP_PASSWORD)."
            )

    def _connect(self):
        try:
            connection = self._imaplib.IMAP4_SSL(self._host, self._port)
            connection.login(self._username, self._app_password)
            return connection
        except Exception as exc:  # noqa: BLE001 - login failures are read-blocking
            raise IcloudMailReadError(f"iCloud Mail login failed: {type(exc).__name__}") from exc

    def fetch_recent(self, *, max_results: int = 20) -> list[IcloudMailMessage]:
        """Fetch a bounded number of recent inbox messages (read-only).

        Uses the app-specific password; always selects the INBOX read-only and
        closes without any mutation.
        """
        connection = self._connect()
        results: list[IcloudMailMessage] = []
        try:
            # SELECT the inbox in read-only (EXAMINE) to guarantee no mutation.
            status, _data = connection.select("INBOX", readonly=True)
            if status != "OK":
                raise IcloudMailReadError("iCloud Mail could not open the inbox")

            status, data = connection.search(None, "ALL")
            if status != "OK":
                raise IcloudMailReadError("iCloud Mail could not search the inbox")
            message_nums = data[0].split() if data and data[0] else []
            # Keep only the most recent max_results.
            recent_nums = message_nums[-max_results:]

            for num in reversed(recent_nums):
                try:
                    status, msg_data = connection.fetch(num, "(RFC822)")
                except Exception as exc:  # noqa: BLE001 - skip unreadable message
                    raise IcloudMailReadError(f"iCloud Mail fetch failed: {type(exc).__name__}") from exc
                if status != "OK" or not msg_data:
                    continue
                for part in msg_data:
                    if not isinstance(part, tuple):
                        continue
                    raw = part[1]
                    message = email.message_from_bytes(raw)
                    subject = _decode_header_value(str(message.get("Subject", "")))
                    sender = _decode_header_value(str(message.get("From", "")))
                    received = str(message.get("Date", ""))
                    body = self._extract_body(message)
                    results.append(
                        IcloudMailMessage(
                            message_id=str(message.get("Message-ID", "")),
                            subject=subject,
                            sender=sender,
                            received_at=received,
                            body_text=body,
                            thread_id=str(message.get("Message-ID", "")),
                        )
                    )
        finally:
            try:
                connection.close()
            except Exception:  # noqa: BLE001 - close is best-effort
                pass
            try:
                connection.logout()
            except Exception:  # noqa: BLE001 - logout is best-effort (no mutation)
                pass
        return results

    @staticmethod
    def _extract_body(message) -> str:
        """Best-effort plain-text body extraction from an email.message."""
        if message.is_multipart():
            chunks = []
            for part in message.walk():
                if part.get_content_type() == "text/plain":
                    payload = part.get_payload(decode=True) or b""
                    chunks.append(_decode_body(payload))
            return "\n".join(chunks) if chunks else ""
        payload = message.get_payload(decode=True) or b""
        return _decode_body(payload)
