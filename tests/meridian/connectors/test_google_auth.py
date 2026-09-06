"""Tests for R25 Google OAuth transport + multi-account token store."""

import pytest

from meridian.connectors.google_auth import (
    GoogleOAuth2Client,
    GoogleOAuthConfig,
    GoogleOAuthConfigError,
    OAuthTokenStore,
)


def test_config_requires_owner_set_credentials(monkeypatch):
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_ID", raising=False)
    monkeypatch.delenv("GOOGLE_OAUTH_CLIENT_SECRET", raising=False)
    with pytest.raises(GoogleOAuthConfigError, match="owner action"):
        GoogleOAuthConfig.from_env()


def test_config_from_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "app-123.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "GOCSPX-not-a-real-secret")
    cfg = GoogleOAuthConfig.from_env()
    assert cfg.client_id.endswith("apps.googleusercontent.com")


def test_authorization_url_contains_scopes_and_state():
    cfg = GoogleOAuthConfig(
        client_id="app-123.apps.googleusercontent.com",
        client_secret="secret",
    )
    client = GoogleOAuth2Client(cfg, scopes=("https://www.googleapis.com/auth/gmail.readonly",))
    url = client.authorization_url(state="st-1")
    assert "oauth2/v2/auth" in url
    assert "gmail.readonly" in url
    assert "state=st-1" in url
    assert "access_type=offline" in url


def test_token_store_persists_and_multi_account(tmp_path):
    store = OAuthTokenStore(str(tmp_path / "t.db"))
    store.save(kind="gmail", account_email="a@example.com", access_token="tok-a", refresh_token="ref-a")
    store.save(kind="gmail", account_email="b@example.com", access_token="tok-b", refresh_token="ref-b")
    store.save(kind="gmail", account_email="a@example.com", access_token="tok-a2", refresh_token="ref-a2")
    got = store.get(kind="gmail", account_email="a@example.com")
    assert got["access_token"] == "tok-a2"  # upsert
    accounts = store.list_accounts(kind="gmail")
    assert {a["account_email"] for a in accounts} == {"a@example.com", "b@example.com"}


def test_token_store_scopes_by_kind(tmp_path):
    store = OAuthTokenStore(str(tmp_path / "k.db"))
    store.save(kind="calendar", account_email="c@example.com", access_token="tc", refresh_token="rc")
    assert store.list_accounts(kind="gmail") == []
    assert len(store.list_accounts(kind="calendar")) == 1


def test_token_store_roundtrips_all_fields(tmp_path):
    store = OAuthTokenStore(str(tmp_path / "r.db"))
    store.save(kind="gmail", account_email="x@y.z", access_token="at", refresh_token="rt", expires_at="2026-10-01T00:00:00Z")
    got = store.get(kind="gmail", account_email="x@y.z")
    assert got["expires_at"] == "2026-10-01T00:00:00Z"
    assert got["access_token"] == "at"


def test_authorization_url_state_distinguishes_kinds():
    cfg = GoogleOAuthConfig(client_id="c", client_secret="s")
    g = GoogleOAuth2Client(cfg, scopes=("https://www.googleapis.com/auth/calendar.events.readonly",))
    url = g.authorization_url(state="calendar-connect")
    assert "calendar.events.readonly" in url
    assert "state=calendar-connect" in url


class _FakeAuthResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def test_exchange_returns_token_dict_synchronously(monkeypatch):
    """exchange() must resolve to a dict when called from a sync Flask view."""
    cfg = GoogleOAuthConfig(client_id="c", client_secret="s")
    client = GoogleOAuth2Client(cfg, scopes=("https://www.googleapis.com/auth/gmail.readonly",))
    monkeypatch.setattr(
        "requests.post",
        lambda *args, **kwargs: _FakeAuthResponse(
            {"access_token": "at-1", "refresh_token": "rt-1", "expires_in": 3600}
        ),
    )

    tokens = client.exchange("code-1")

    assert isinstance(tokens, dict)
    assert tokens["access_token"] == "at-1"
    assert tokens["refresh_token"] == "rt-1"


def test_refresh_returns_token_dict_synchronously(monkeypatch):
    cfg = GoogleOAuthConfig(client_id="c", client_secret="s")
    client = GoogleOAuth2Client(cfg, scopes=("https://www.googleapis.com/auth/gmail.readonly",))
    monkeypatch.setattr(
        "requests.post",
        lambda *args, **kwargs: _FakeAuthResponse({"access_token": "at-2"}),
    )

    tokens = client.refresh("rt-1")

    assert isinstance(tokens, dict)
    assert tokens["access_token"] == "at-2"


def test_google_identity_scopes_are_read_only_and_include_email():
    from meridian.connectors.google_auth import GOOGLE_IDENTITY_SCOPES

    assert "openid" in GOOGLE_IDENTITY_SCOPES
    assert "email" in GOOGLE_IDENTITY_SCOPES


def test_email_from_id_token_extracts_claim():
    from meridian.connectors.google_auth import email_from_id_token

    import base64
    import json

    payload = base64.urlsafe_b64encode(
        json.dumps({"email": "baronhod207@gmail.com", "sub": "123"}).encode("utf-8")
    ).decode("ascii").rstrip("=")
    assert email_from_id_token(f"head.{payload}.sig") == "baronhod207@gmail.com"


def test_email_from_id_token_rejects_malformed_input():
    from meridian.connectors.google_auth import email_from_id_token

    assert email_from_id_token("not-a-jwt") is None
    assert email_from_id_token("") is None
    assert email_from_id_token("a.b.c") is None
