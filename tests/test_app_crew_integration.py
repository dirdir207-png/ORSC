import os
import tempfile

import pytest

_TEST_DIR = tempfile.mkdtemp(prefix="simplecrew_test_")
os.environ["DB_FILE"] = os.path.join(_TEST_DIR, "savings_data.db")

import app as simplecrew  # noqa: E402
from crew.client import CrewUncertainWriteError  # noqa: E402
from crew.health import CrewHealth, CrewHealthState  # noqa: E402


@pytest.fixture(scope="module")
def authenticated_client():
    simplecrew.init_db()
    simplecrew._background_thread_started = True

    client = simplecrew.app.test_client()
    response = client.post(
        "/api/auth/register",
        json={
            "username": "testuser",
            "email": "testuser@example.com",
            "password": "test-password-123",
        },
    )
    assert response.status_code == 200, response.get_json()
    assert response.get_json()["success"] is True
    return client


def test_crew_health_endpoint_never_exposes_token(monkeypatch, authenticated_client):
    class StubHealth:
        def check(self):
            return CrewHealth(CrewHealthState.HEALTHY, "Crew connection is healthy")

    monkeypatch.setenv("BEARER_TOKEN", "super-secret-sentinel-value")
    monkeypatch.setattr(simplecrew, "crew_health_service", StubHealth())
    response = authenticated_client.get("/api/account/crew-health")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["state"] == "healthy"
    body = str(payload)
    assert "super-secret-sentinel-value" not in body
    assert "authorization:" not in body.lower()


def test_move_money_delegates_exactly_once_to_crew_client(monkeypatch):
    calls = []

    class StubCrewClient:
        def execute(self, operation_name, query, variables=None, *, is_mutation=False):
            calls.append((operation_name, variables, is_mutation))
            return {"initiateTransfer": {"result": {"id": "tx-1"}}}

    monkeypatch.setattr(simplecrew, "crew_client", StubCrewClient())
    result = simplecrew.move_money("from-1", "to-2", 12.34, "Rent")

    assert calls == [(
        "InitiateTransferScottie",
        {"input": {
            "amount": 1234,
            "accountFromId": "from-1",
            "accountToId": "to-2",
            "note": "Rent",
        }},
        True,
    )]
    assert result["success"] is True


def test_move_money_does_not_retry_uncertain_write(monkeypatch):
    calls = 0

    class StubCrewClient:
        def execute(self, *args, **kwargs):
            nonlocal calls
            calls += 1
            raise CrewUncertainWriteError("verify state")

    monkeypatch.setattr(simplecrew, "crew_client", StubCrewClient())
    result = simplecrew.move_money("from-1", "to-2", 12.34, "Rent")
    assert calls == 1
    assert result["error_code"] == "uncertain_write"
    assert result["verify_state"] is True
