import os
import tempfile

import pytest

_TEST_DIR = tempfile.mkdtemp(prefix="simplecrew_test_")
os.environ["DB_FILE"] = os.path.join(_TEST_DIR, "savings_data.db")

import app as simplecrew  # noqa: E402
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
