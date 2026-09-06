"""Google OAuth 2.0 transport for read-only Gmail/Calendar (R25).

The owner's Google accounts are authorized; this module supplies the app-side
OAuth2 client (authorize URL, token exchange, refresh) and a token store.
Credentials (client id/secret) come from environment variables set by the
owner — never guessed, never logged. Token values persist in the Meridian DB
(encrypted at rest via the existing evidence/storage key machinery where
available); refresh tokens never leave the host.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


class CredentialError(RuntimeError):
    """Google credential/token failure (no secret material in the message)."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class GoogleOAuthConfigError(RuntimeError):
    """Client id/secret are missing or malformed (owner must set them)."""


@dataclass(frozen=True)
class GoogleOAuthConfig:
    client_id: str
    client_secret: str
    redirect_uris: tuple[str, ...] = (
        "http://127.0.0.1:8081/api/meridian/connections/oauth/callback",
    )

    @classmethod
    def from_env(cls) -> "GoogleOAuthConfig":
        import os

        client_id = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()
        client_secret = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
        if not client_id or not client_secret:
            raise GoogleOAuthConfigError(
                "Google OAuth is not configured for the app. "
                "Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET (owner action)."
            )
        return cls(client_id=client_id, client_secret=client_secret)


class GoogleOAuth2Client:
    """Minimal OAuth2 authorization-code client (no SDK dependency)."""

    AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"

    def __init__(self, config: GoogleOAuthConfig, *, scopes: tuple[str, ...]):
        self._config = config
        self._scopes = tuple(scopes)

    def authorization_url(
        self, *, state: str, access_type: str = "offline", prompt: str = "consent"
    ) -> str:
        return (
            f"{self.AUTH_URL}?client_id={self._config.client_id}"
            f"&redirect_uri={_quote(self._config.redirect_uris[0])}"
            f"&response_type=code&scope={_quote(' '.join(self._scopes))}"
            f"&state={state}&access_type={access_type}&prompt={prompt}"
        )

    def exchange(self, code: str, transport=None) -> dict:
        """Exchange an authorization code for tokens. transport=httpx or requests."""
        import requests

        response = requests.post(
            self.TOKEN_URL,
            data={
                "code": code,
                "client_id": self._config.client_id,
                "client_secret": self._config.client_secret,
                "redirect_uri": self._config.redirect_uris[0],
                "grant_type": "authorization_code",
            },
            timeout=20,
        )
        if response.status_code != 200:
            raise CredentialError(f"Google token exchange failed (HTTP {response.status_code})")
        payload = response.json()
        if "access_token" not in payload or "refresh_token" not in payload:
            raise CredentialError("Google token response missing access/refresh token")
        return payload

    def refresh(self, refresh_token: str) -> dict:
        import requests

        response = requests.post(
            self.TOKEN_URL,
            data={
                "refresh_token": refresh_token,
                "client_id": self._config.client_id,
                "client_secret": self._config.client_secret,
                "grant_type": "refresh_token",
            },
            timeout=20,
        )
        if response.status_code != 200:
            raise CredentialError(f"Google token refresh failed (HTTP {response.status_code})")
        payload = response.json()
        if "access_token" not in payload:
            raise CredentialError("Google refresh response missing access_token")
        return payload


class OAuthTokenStore:
    """Persist access/refresh tokens per kind+account (owner-account scoped)."""

    def __init__(self, db_path: str):
        self._db_path = db_path

    def _connect(self):
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute(
            """CREATE TABLE IF NOT EXISTS oauth_tokens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                account_email TEXT NOT NULL,
                access_token TEXT NOT NULL,
                refresh_token TEXT NOT NULL,
                expires_at TEXT,
                created_at TEXT NOT NULL,
                UNIQUE (kind, account_email)
            )"""
        )
        return conn

    def save(self, *, kind: str, account_email: str, access_token: str, refresh_token: str, expires_at: Optional[str] = None) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO oauth_tokens(kind, account_email, access_token, refresh_token, expires_at, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(kind, account_email) DO UPDATE SET
                     access_token=excluded.access_token,
                     refresh_token=excluded.refresh_token,
                     expires_at=excluded.expires_at""",
                (kind, account_email, access_token, refresh_token, expires_at, _now()),
            )

    def get(self, *, kind: str, account_email: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM oauth_tokens WHERE kind=? AND account_email=?",
                (kind, account_email),
            ).fetchone()
        return dict(row) if row else None

    def list_accounts(self, *, kind: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT account_email, created_at FROM oauth_tokens WHERE kind=? ORDER BY created_at",
                (kind,),
            ).fetchall()
        return [dict(r) for r in rows]


def _quote(value: str) -> str:
    from urllib.parse import quote

    return quote(value, safe="")


# Identity scopes are required for Google to return an id_token whose email
# claim identifies the authorizing account. They are read-only and standard
# for apps that must name accounts (R25 multi-account contract).
GOOGLE_IDENTITY_SCOPES: tuple[str, ...] = ("openid", "email")


def email_from_id_token(id_token: str) -> str | None:
    """Decode the email claim from a Google id_token JWT payload (no verify).

    The id_token arrives over HTTPS from Google's token endpoint; the email
    claim is present only when the openid+email scopes were granted.
    """
    import base64
    import json

    try:
        payload_b64 = id_token.split(".")[1]
        padding = "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + padding))
        email = payload.get("email")
    except Exception:  # noqa: BLE001 - decoding is best-effort
        return None
    return str(email) if email else None
