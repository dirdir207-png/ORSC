import base64
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from urllib.parse import quote

import pytest

if "app" not in sys.modules:
    os.environ["DB_FILE"] = os.path.join(
        tempfile.mkdtemp(prefix="meridian_api_test_"), "savings_data.db"
    )

import app as simplecrew
from meridian.classify import ClassificationInput, classify_deterministic
from meridian.connections import ConnectionRepository, ConnectionState
from meridian.connectors.email import READ_ONLY_GMAIL_SCOPE
from meridian.repository import FinancialRepository


@pytest.fixture(autouse=True)
def disable_background_polling(monkeypatch):
    monkeypatch.setattr(simplecrew, "_background_thread_started", True)


@pytest.fixture
def api_client(monkeypatch, tmp_path):
    repository = FinancialRepository(str(tmp_path / "financial.db"))
    user_id = "meridian-api-user"
    monkeypatch.setattr(
        simplecrew.login_manager,
        "_user_callback",
        lambda value: simplecrew.User(
            value, "meridian-api-user", "meridian-api@example.com"
        ),
    )

    monkeypatch.setitem(
        simplecrew.app.config,
        "MERIDIAN_REPOSITORY_FACTORY",
        lambda: repository,
    )
    client = simplecrew.app.test_client()
    with client.session_transaction() as session:
        session["_user_id"] = str(user_id)
        session["_fresh"] = True
    return client, repository


def _complete_connection(repository, *, provider="crew", include_transaction=True):
    now = datetime.now(timezone.utc).isoformat()
    run = repository.begin_sync_run(
        provider=provider,
        connection_external_id=f"{provider}-household",
        connection_name=provider.title(),
    )
    account = repository.upsert_account(
        provider=provider,
        external_id=f"{provider}-checking",
        name=f"{provider.title()} checking",
        account_type="checking",
        balance=100.0,
        connection_id=run.connection_id,
        source_updated_at=now,
    )
    if include_transaction:
        repository.upsert_transaction(
            provider=provider,
            external_id=f"{provider}-coffee",
            account_id=account.id,
            amount=-3.0,
            occurred_at=now,
            description="Coffee",
            status="posted",
            source_updated_at=now,
        )
    repository.finish_sync_run(
        run.id,
        status="complete",
        accounts_synced=1,
        transactions_synced=int(include_transaction),
        errors=0,
    )
    return account


def _partial_connection_without_records(repository, *, provider="simplefin"):
    run = repository.begin_sync_run(
        provider=provider,
        connection_external_id=f"{provider}-household",
        connection_name=provider.title(),
    )
    repository.finish_sync_run(
        run.id,
        status="partial",
        accounts_synced=0,
        transactions_synced=0,
        errors=1,
    )


@pytest.mark.parametrize(
    "path",
    [
        "/api/meridian/today",
        "/api/meridian/activity",
        "/api/meridian/transactions/1",
        "/api/meridian/accounts",
        "/api/meridian/evidence/1/content",
        "/api/meridian/settings/connections",
    ],
)
def test_meridian_read_apis_require_login(path):
    response = simplecrew.app.test_client().get(path)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login?next=" + quote(path, safe=""))


def test_evidence_content_rejects_invalid_identifier(api_client):
    client, _repository = api_client

    response = client.get("/api/meridian/evidence/not-an-id/content")

    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "invalid_request"


def test_connection_api_requires_login_and_never_serializes_secrets(
    api_client, monkeypatch
):
    client, graph = api_client
    authorizations = ConnectionRepository(graph.db_path)
    authorizations.upsert(
        kind="gmail",
        display_name="Gmail",
        state=ConnectionState.CONNECTED,
        granted_scopes=(READ_ONLY_GMAIL_SCOPE,),
        last_successful_at="2026-08-31T07:47:00Z",
        retention_days=365,
    )
    monkeypatch.setitem(
        simplecrew.app.config,
        "MERIDIAN_CONNECTIONS_FACTORY",
        lambda: authorizations,
    )
    monkeypatch.setenv("GMAIL_ACCESS_TOKEN", "secret-sentinel")

    response = client.get("/api/meridian/settings/connections")

    assert response.status_code == 200
    assert response.get_json()["groups"][1]["connections"][0]["kind"] == "gmail"
    assert "secret-sentinel" not in response.get_data(as_text=True)
    assert (
        simplecrew.app.test_client()
        .get("/api/meridian/settings/connections")
        .status_code
        == 302
    )


def test_connection_authorize_returns_only_provider_handoff_state(
    api_client, monkeypatch
):
    client, graph = api_client
    authorizations = ConnectionRepository(graph.db_path)
    monkeypatch.setitem(
        simplecrew.app.config,
        "MERIDIAN_CONNECTIONS_FACTORY",
        lambda: authorizations,
    )
    monkeypatch.setitem(
        simplecrew.app.config,
        "MERIDIAN_CONNECTION_AUTHORIZERS",
        {"gmail": lambda: {"authorization_url": "https://accounts.google.test/oauth"}},
    )

    response = client.post("/api/meridian/settings/connections/gmail/authorize")

    assert response.status_code == 200
    assert response.get_json() == {
        "state": "pending",
        "authorization_url": "https://accounts.google.test/oauth",
    }
    saved = authorizations.list_all()[0]
    assert saved.state is ConnectionState.PENDING
    assert saved.granted_scopes == ()


def test_connection_revoke_marks_only_selected_source(api_client, monkeypatch):
    client, graph = api_client
    authorizations = ConnectionRepository(graph.db_path)
    gmail = authorizations.upsert(
        kind="gmail",
        display_name="Gmail",
        state=ConnectionState.CONNECTED,
        granted_scopes=(READ_ONLY_GMAIL_SCOPE,),
        last_successful_at="2026-08-31T07:47:00Z",
        retention_days=365,
    )
    calendar = authorizations.upsert(
        kind="calendar",
        display_name="Google Calendar",
        state=ConnectionState.CONNECTED,
        granted_scopes=("calendar.readonly",),
        last_successful_at="2026-08-31T07:52:00Z",
        retention_days=90,
    )

    class Connector:
        revoked = False

        def revoke(self):
            self.revoked = True

    connector = Connector()
    monkeypatch.setitem(
        simplecrew.app.config,
        "MERIDIAN_CONNECTIONS_FACTORY",
        lambda: authorizations,
    )
    monkeypatch.setitem(
        simplecrew.app.config,
        "MERIDIAN_CONNECTION_CONNECTORS",
        {gmail.public_id: connector},
    )

    response = client.post(
        f"/api/meridian/settings/connections/{gmail.public_id}/revoke"
    )

    assert response.status_code == 200
    assert response.get_json()["state"] == "revoked"
    assert connector.revoked is True
    assert authorizations.get(calendar.public_id).state is ConnectionState.CONNECTED


def test_meridian_read_apis_serialize_safe_data_and_stable_errors(
    api_client, monkeypatch
):
    client, repository = api_client
    account = repository.upsert_account(
        provider="crew",
        external_id="account-number-123456789",
        name="Checking",
        account_type="checking",
        balance=125.0,
        available_balance=100.0,
        synced_at="2026-08-27T12:00:00Z",
    )
    first = repository.upsert_transaction(
        provider="crew",
        external_id="transaction-secret-111",
        account_id=account.id,
        amount=-12.5,
        occurred_at="2026-08-27T11:00:00Z",
        description="Coffee",
        raw_description="Bearer should-never-appear",
        status="posted",
        synced_at="2026-08-27T12:00:00Z",
    )
    repository.upsert_transaction(
        provider="crew",
        external_id="transaction-secret-222",
        account_id=account.id,
        amount=-20.0,
        occurred_at="2026-08-26T11:00:00Z",
        description="Lunch",
        status="posted",
        synced_at="2026-08-27T12:00:00Z",
    )
    monkeypatch.setenv("BEARER_TOKEN", "super-secret-sentinel-value")

    today = client.get("/api/meridian/today")
    accounts = client.get("/api/meridian/accounts")
    activity = client.get("/api/meridian/activity?limit=1")
    transaction = client.get(f"/api/meridian/transactions/{first.id}")
    missing = client.get("/api/meridian/transactions/99999")

    assert today.status_code == accounts.status_code == activity.status_code == 200
    assert transaction.status_code == 200
    assert activity.get_json()["next_cursor"]
    assert activity.get_json()["transactions"][0]["id"] == first.id
    for response in (today, accounts, activity, transaction):
        payload = response.get_json()
        assert "data_freshness" in payload
        body = response.get_data(as_text=True)
        assert "account-number-123456789" not in body
        assert "transaction-secret-111" not in body
        assert "should-never-appear" not in body
        assert "super-secret-sentinel-value" not in body

    assert missing.status_code == 404
    assert missing.get_json()["error"] == {
        "code": "transaction_not_found",
        "message": "The requested transaction is not available.",
        "recovery_action": "Return to Activity and choose another transaction.",
    }


def test_meridian_activity_rejects_invalid_pagination_with_a_stable_error(api_client):
    client, _ = api_client

    response = client.get("/api/meridian/activity?limit=not-a-number")

    assert response.status_code == 400
    assert response.get_json()["error"] == {
        "code": "invalid_request",
        "message": "limit must be an integer between 1 and 200.",
        "recovery_action": "Use a limit between 1 and 200 and try again.",
    }


def test_classification_correction_is_atomic_audited_and_can_create_rule(api_client):
    client, repository = api_client
    account = repository.upsert_account(
        provider="crew",
        external_id="checking",
        name="Checking",
        account_type="checking",
        balance=100,
    )
    transactions = []
    for external_id in ("coffee-1", "coffee-2"):
        transaction = repository.upsert_transaction(
            provider="crew",
            external_id=external_id,
            account_id=account.id,
            amount=-5,
            occurred_at="2026-08-29T10:00:00Z",
            description="Coffee",
            merchant="Corner Coffee",
            status="posted",
        )
        repository.record_classification(
            transaction.id,
            classify_deterministic(
                ClassificationInput(
                    transaction.id,
                    -5,
                    "Coffee",
                    "Corner Coffee",
                    "checking",
                    "2026-08-29T10:00:00Z",
                )
            ),
        )
        transactions.append(transaction)

    response = client.post(
        f"/api/meridian/transactions/{transactions[0].id}/classification",
        json={"category": "Dining", "kind": "spend", "create_rule": True},
    )

    assert response.status_code == 200
    assert response.get_json()["classification"]["category"] == "Dining"
    assert (
        repository.get_transaction(transactions[1].id).classification_category
        == "Dining"
    )
    assert repository.list_assignment_rules()[0].category == "Dining"
    assert repository.list_classification_history(transactions[0].id)


def test_review_and_patterns_activity_modes(api_client):
    client, repository = api_client
    account = repository.upsert_account(
        provider="crew",
        external_id="checking",
        name="Checking",
        account_type="checking",
        balance=100,
    )
    for index, occurred_at in enumerate(
        ("2026-06-29T10:00:00Z", "2026-07-29T10:00:00Z", "2026-08-29T10:00:00Z")
    ):
        transaction = repository.upsert_transaction(
            provider="crew",
            external_id=f"subscription-{index}",
            account_id=account.id,
            amount=-12,
            occurred_at=occurred_at,
            description="Monthly service",
            merchant="Example Service",
            status="posted",
        )
        repository.record_classification(
            transaction.id,
            classify_deterministic(
                ClassificationInput(
                    transaction.id,
                    -12,
                    "Monthly service",
                    "Example Service",
                    "checking",
                    occurred_at,
                )
            ),
        )

    review = client.get("/api/meridian/activity?mode=review")
    patterns = client.get("/api/meridian/activity?mode=patterns")

    assert review.status_code == 200
    assert len(review.get_json()["transactions"]) == 3
    assert patterns.status_code == 200
    assert patterns.get_json()["patterns"][0]["kind"] == "recurrence"
    assert patterns.get_json()["patterns"][0]["evidence_ids"]


def test_contextual_advisor_endpoint_passes_workspace_context(api_client, monkeypatch):
    client, repository = api_client
    account = repository.upsert_account(
        provider="crew",
        external_id="checking",
        name="Checking",
        account_type="checking",
        balance=100,
    )
    transaction = repository.upsert_transaction(
        provider="crew",
        external_id="coffee",
        account_id=account.id,
        amount=-5,
        occurred_at="2026-08-29T10:00:00Z",
        description="Coffee",
        status="posted",
    )
    calls = []

    class Advisor:
        def ask(self, context, question):
            calls.append((context, question))
            return {
                "answer": "It was $5.",
                "evidence": [f"transaction:{transaction.id}"],
                "proposals": [],
                "provider": "test",
                "model": "test-model",
                "usage": {},
            }

    monkeypatch.setitem(
        simplecrew.app.config, "MERIDIAN_ADVISOR_FACTORY", lambda: Advisor()
    )

    response = client.post(
        "/api/meridian/advisor",
        json={
            "question": "What happened?",
            "context": {
                "kind": "transaction",
                "object_id": transaction.id,
                "evidence_ids": [f"transaction:{transaction.id}"],
            },
        },
    )

    assert response.status_code == 200
    assert response.get_json()["answer"] == "It was $5."
    assert calls[0][0].kind == "transaction"


@pytest.mark.parametrize(
    "path",
    [
        "/api/meridian/today",
        "/api/meridian/accounts",
        "/api/meridian/activity",
    ],
)
def test_unfiltered_reads_include_partial_providers_without_records(api_client, path):
    client, repository = api_client
    _complete_connection(repository)
    _partial_connection_without_records(repository)

    response = client.get(path)

    assert response.status_code == 200
    assert response.get_json()["data_freshness"]["status"] == "stale"


@pytest.mark.parametrize(
    "path",
    [
        "/api/meridian/today",
        "/api/meridian/accounts",
        "/api/meridian/activity",
    ],
)
def test_unfiltered_reads_treat_unlinked_returned_records_as_stale(api_client, path):
    client, repository = api_client
    account = repository.upsert_account(
        provider="crew",
        external_id="unlinked-checking",
        name="Unlinked checking",
        account_type="checking",
        balance=100.0,
        source_updated_at=datetime.now(timezone.utc).isoformat(),
    )
    repository.upsert_transaction(
        provider="crew",
        external_id="unlinked-coffee",
        account_id=account.id,
        amount=-3.0,
        occurred_at=datetime.now(timezone.utc).isoformat(),
        description="Coffee",
        status="posted",
    )

    response = client.get(path)

    assert response.status_code == 200
    assert response.get_json()["data_freshness"]["status"] == "stale"


def test_unfiltered_activity_scans_unlinked_transactions_beyond_first_page(api_client):
    client, repository = api_client
    linked_account = _complete_connection(repository)
    unlinked_account = repository.upsert_account(
        provider="crew",
        external_id="unlinked-later-checking",
        name="Unlinked later checking",
        account_type="checking",
        balance=100.0,
        source_updated_at="2026-08-26T08:00:00Z",
    )
    repository.upsert_transaction(
        provider="crew",
        external_id="unlinked-later-coffee",
        account_id=unlinked_account.id,
        amount=-3.0,
        occurred_at="2026-08-26T08:00:00Z",
        description="Later page coffee",
        status="posted",
    )

    response = client.get("/api/meridian/activity", query_string={"limit": 1})

    assert response.status_code == 200
    assert response.get_json()["transactions"][0]["account_id"] == linked_account.id
    assert response.get_json()["data_freshness"]["status"] == "stale"


def test_filtered_empty_activity_uses_the_requested_account_provider_freshness(
    api_client,
):
    client, repository = api_client
    account = _complete_connection(repository, include_transaction=False)

    response = client.get(
        "/api/meridian/activity", query_string={"account_id": account.id}
    )

    assert response.status_code == 200
    assert response.get_json()["transactions"] == []
    assert response.get_json()["data_freshness"]["status"] == "fresh"


def test_filtered_empty_activity_reports_partial_requested_account_as_stale(api_client):
    client, repository = api_client
    run = repository.begin_sync_run(
        provider="simplefin",
        connection_external_id="simplefin-household",
        connection_name="SimpleFin",
    )
    account = repository.upsert_account(
        provider="simplefin",
        external_id="simplefin-checking",
        name="SimpleFin checking",
        account_type="checking",
        balance=100.0,
        connection_id=run.connection_id,
        source_updated_at=datetime.now(timezone.utc).isoformat(),
    )
    repository.finish_sync_run(
        run.id,
        status="partial",
        accounts_synced=1,
        transactions_synced=0,
        errors=1,
    )

    response = client.get(
        "/api/meridian/activity", query_string={"account_id": account.id}
    )

    assert response.status_code == 200
    assert response.get_json()["transactions"] == []
    assert response.get_json()["data_freshness"]["status"] == "stale"


def _cursor(payload):
    return base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ).decode("ascii")


@pytest.mark.parametrize(
    "cursor",
    [
        "not-base64",
        _cursor(["not-a-timestamp", 1]),
        _cursor([1, 1]),
        _cursor(["2026-08-27T08:00:00", 1]),
        _cursor(["2026-08-27T08:00:00Z", True]),
        _cursor(["2026-08-27T08:00:00Z", 0]),
        _cursor(["2026-08-27T08:00:00Z", 1, "extra"]),
        _cursor(["2026-08-27 08:00:00+00:00", 1]),
        _cursor(["20260827T080000+00:00", 1]),
        _cursor(["2026-08-27T08:00:00+00:00", 1]),
        base64.urlsafe_b64encode(b'["2026-08-27T08:00:00Z", 1]').decode("ascii"),
    ],
)
def test_meridian_activity_rejects_malformed_or_noncanonical_cursors(
    api_client, cursor
):
    client, _ = api_client

    response = client.get("/api/meridian/activity", query_string={"cursor": cursor})

    assert response.status_code == 400
    assert response.get_json()["error"] == {
        "code": "invalid_request",
        "message": "The activity cursor is invalid.",
        "recovery_action": "Restart from the first Activity page and try again.",
    }


@pytest.mark.parametrize("account_id", ["not-a-number", "0", "-1"])
def test_meridian_activity_names_an_invalid_account_filter(api_client, account_id):
    client, _ = api_client

    response = client.get(
        "/api/meridian/activity", query_string={"account_id": account_id}
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == {
        "code": "invalid_request",
        "message": "account_id must be a positive integer.",
        "recovery_action": "Use a positive account_id and try again.",
    }


def test_meridian_missing_transaction_keeps_last_known_good_freshness(api_client):
    client, repository = api_client
    now = datetime.now(timezone.utc).isoformat()
    run = repository.begin_sync_run(
        provider="crew",
        connection_external_id="crew-household",
        connection_name="Crew",
    )
    repository.upsert_account(
        provider="crew",
        external_id="checking",
        name="Checking",
        account_type="checking",
        balance=100.0,
        connection_id=run.connection_id,
        source_updated_at=now,
    )
    repository.finish_sync_run(
        run.id,
        status="complete",
        accounts_synced=1,
        transactions_synced=0,
        errors=0,
    )

    response = client.get("/api/meridian/transactions/99999")

    assert response.status_code == 404
    assert response.get_json()["data_freshness"]["status"] == "fresh"


def test_meridian_api_hides_repository_failures_behind_a_stable_error(
    api_client, monkeypatch
):
    client, _ = api_client

    class UnavailableRepository:
        @staticmethod
        def list_accounts():
            raise RuntimeError("Bearer should-never-appear")

    monkeypatch.setitem(
        simplecrew.app.config,
        "MERIDIAN_REPOSITORY_FACTORY",
        UnavailableRepository,
    )

    response = client.get("/api/meridian/accounts")

    assert response.status_code == 503
    assert response.get_json()["error"] == {
        "code": "financial_data_unavailable",
        "message": "Financial data is temporarily unavailable.",
        "recovery_action": "Try again after your provider reconnects.",
    }
    assert "should-never-appear" not in response.get_data(as_text=True)
