"""Tests for R26 resumable cursor store + incremental reads."""

from meridian.connection_jobs import IngestionCursorStore, ResumableIncremental


def _store(tmp_path):
    return IngestionCursorStore(str(tmp_path / "c.db"))


class FakeTransport:
    def __init__(self, batches):
        self._batches = batches
        self.calls = []

    def list(self, *, cursor, **kwargs):
        self.calls.append(cursor)
        return self._batches.pop(0)


def test_cursor_resumes_without_duplicates(tmp_path):
    store = _store(tmp_path)
    t = FakeTransport([
        {"items": [{"id": "m1"}, {"id": "m2"}], "cursor": "c1"},
        {"items": [{"id": "m2"}, {"id": "m3"}], "cursor": "c2"},
    ])
    inc = ResumableIncremental(store, kind="gmail", account_email="a@example.com")
    first = inc.run(t)
    second = inc.run(t)
    assert first["new"] == 2
    assert second["new"] == 1  # m2 deduped
    assert second["resumed_cursor"] == "c2"
    assert t.calls == [None, "c1"]  # resumed from cursor


def test_identical_ids_in_different_mailboxes_stay_separate(tmp_path):
    store = _store(tmp_path)
    t = FakeTransport([{"items": [{"id": "X"}], "cursor": "c"}])
    a = ResumableIncremental(store, kind="gmail", account_email="a@x.com")
    b = ResumableIncremental(store, kind="gmail", account_email="b@x.com")
    assert a.run(t)["new"] == 1
    t2 = FakeTransport([{"items": [{"id": "X"}], "cursor": "c"}])
    assert b.run(t2)["new"] == 1  # same id, different account — no dedup collision


def test_revocation_stops_capture(tmp_path):
    store = _store(tmp_path)
    inc = ResumableIncremental(store, kind="calendar", account_email="a@x.com")
    store.save_cursor(kind="calendar", account_email="a@x.com", cursor_value="c0")
    store.revoke(kind="calendar", account_email="a@x.com")
    t = FakeTransport([{"items": [{"id": "e1"}], "cursor": "c1"}])
    result = inc.run(t)
    assert result["revoked"] is True
    assert result["new"] == 0
    assert t.calls == []  # transport not even called


def test_deleted_event_is_not_blocked_by_seen(tmp_path):
    # seen-id is advisory: a deletion (absent from batch) simply advances cursor;
    # a re-created id with same external_id is not re-ingested (idempotence).
    store = _store(tmp_path)
    t = FakeTransport([{"items": [{"id": "e1"}], "cursor": "c1"}])
    inc = ResumableIncremental(store, kind="calendar", account_email="a@x.com")
    first = inc.run(t)
    assert first["new"] == 1
    # Deletion: batch empty, cursor advances — no error, no dup
    t2 = FakeTransport([{"items": [], "cursor": "c2"}])
    second = inc.run(t2)
    assert second["resumed_cursor"] == "c2"
    assert second["new"] == 0


def test_build_connections_includes_oauth_accounts(tmp_path):
    import json
    from meridian.connection_jobs import IngestionCursorStore
    from meridian.connectors.google_auth import OAuthTokenStore
    from meridian.services.connections import build_connections

    db = str(tmp_path / "c.db")
    OAuthTokenStore(db).save(kind="gmail", account_email="a@x.com", access_token="t", refresh_token="r")
    OAuthTokenStore(db).save(kind="calendar", account_email="c@x.com", access_token="t", refresh_token="r")

    class FakeGraph:
        db_path = db

        def list_connection_freshness(self):
            return []

    class FakeAuth:
        def list_all(self):
            return []

    result = build_connections(FakeGraph(), FakeAuth(), db_path=db)
    groups = {g["kind"]: g for g in result["groups"]}
    assert [a["account_email"] for a in groups["evidence"]["oauth_accounts"]] == ["a@x.com"]
    assert [a["account_email"] for a in groups["time"]["oauth_accounts"]] == ["c@x.com"]
    assert groups["money"]["oauth_accounts"] == []
