"""Real read-only Gmail transport for evidence intake (R28/29).

Fetches a small, recent set of emails whose bodies are treated as evidence
blobs for the document-intake pipeline. Uses the owner's Gmail OAuth token
(access/refresh) already persisted by `OAuthTokenStore` — never guesses or
reads credentials. Read-only scope (gmail.readonly): never mutates Gmail.

Safety: only fetches a bounded number of recent messages, only reads the
message body as text (no attachment download in this pilot), and logs
sanitized summaries. A refresh_token is used only to obtain a fresh access
token when the stored one is stale.
"""

from __future__ import annotations

import base64
from collections.abc import Callable
from dataclasses import dataclass
from typing import Optional

_MSG_LIST_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
_MSG_GET_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/{id}"


class GmailReadError(RuntimeError):
    """A Gmail read failed; callers decide whether to quarantine or skip."""


@dataclass(frozen=True)
class GmailEvidence:
    message_id: str
    subject: str
    sender: str
    received_at: str
    body_text: str
    thread_id: Optional[str] = None


def _decode_body(payload: dict) -> str:
    """Best-effort decode of the message body part's base64 text."""
    if not isinstance(payload, dict):
        return ""

    def _recurse(node: Optional[dict]) -> str:
        if not isinstance(node, dict):
            return ""
        body_parts = node.get("parts") or []
        if body_parts:
            return "\n".join(_recurse(part) for part in body_parts if isinstance(part, dict))
        body = node.get("body") or {}
        data = body.get("data") or ""
        if not data:
            return ""
        try:
            decoded = base64.urlsafe_b64decode(data + "==="[: -len(data) % 4])
        except Exception:  # noqa: BLE001 - malformed body is best-effort
            return ""
        try:
            return decoded.decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            return ""

    return _recurse(payload.get("payload") or {})


def _headers(payload: dict) -> dict[str, str]:
    result: dict[str, str] = {}
    for header in (payload.get("headers") or []):
        name = str(header.get("name") or "").lower()
        value = str(header.get("value") or "")
        if name in ("subject", "from", "date"):
            result[name] = value
    return result


class GmailTransport:
    """Read-only Gmail fetch using the owner's persisted OAuth token."""

    def __init__(
        self,
        *,
        access_token: str,
        refresh: Optional[Callable[[], dict]] = None,
        timeout_seconds: int = 20,
    ):
        import requests

        self._requests = requests
        self._access_token = access_token
        self._refresh = refresh
        self._timeout = timeout_seconds

    def _get(self, url: str, **params) -> dict:
        """GET with automatic one-shot access-token refresh on 401."""
        for attempt in (0, 1):
            response = self._requests.get(
                url,
                headers={"Authorization": f"Bearer {self._access_token}"},
                params={k: v for k, v in params.items() if v},
                timeout=self._timeout,
            )
            if response.status_code == 401 and attempt == 0 and self._refresh is not None:
                new = self._refresh()
                self._access_token = str(new.get("access_token") or self._access_token)
                continue
            if response.status_code != 200:
                raise GmailReadError(f"Gmail API returned HTTP {response.status_code}")
            return response.json()
        raise GmailReadError("Gmail API kept rejecting the token after refresh")

    def list_message_ids(self, *, max_results: int = 20, since: Optional[str] = None) -> list[dict]:
        # Gmail search `after:` is a YYYY/MM/DD (or epoch) filter; uses the API's
        # `q` param. A 30-day backfill requests only messages newer than the
        # cutoff so we do not over-fetch, while still capping at max_results.
        query = f"after:{since.replace('-', '/')}" if since else ""
        payload = self._get(_MSG_LIST_URL, maxResults=max_results, q=query)
        return payload.get("messages") or []

    def fetch_message(self, message_id: str) -> GmailEvidence:
        payload = self._get(_MSG_GET_URL.format(id=message_id))
        inner = payload.get("payload") or {}
        headers = _headers(inner)
        body_text = _decode_body(payload)
        return GmailEvidence(
            message_id=message_id,
            subject=headers.get("subject", ""),
            sender=headers.get("from", ""),
            received_at=headers.get("date", "") or payload.get("internalDate", ""),
            body_text=body_text,
            thread_id=payload.get("threadId"),
        )

    def fetch_recent(self, *, max_results: int = 20, since: Optional[str] = None) -> list[GmailEvidence]:
        """Fetch a bounded number of recent messages, optionally since a date.

        A single message fetch failing (e.g. a transient 403/rate-limit) must not
        abort the whole batch — it is skipped so a busy backfill keeps progressing.
        """
        results = []
        for meta in self.list_message_ids(max_results=max_results, since=since):
            message_id = str(meta.get("id") or "")
            if not message_id:
                continue
            try:
                results.append(self.fetch_message(message_id))
            except Exception:  # noqa: BLE001 - one bad message must not stop the batch
                continue
        return results
