import pytest
import requests

from crew.client import (
    CrewAPIError,
    CrewAuthenticationError,
    CrewTransportError,
    CrewUncertainWriteError,
)
from crew.health import BrokerUnavailableError, CredentialLockedError
from crew.session_credentials import SessionCredential
from crew.transports import BrokerCrewTransport, SessionCookieTransport


class Response:
    status_code = 200
    def __init__(self, payload): self.payload = payload
    def json(self): return self.payload


class Session:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []
        self.cookies = self
        self.cookie_values = []
    def set(self, **kwargs): self.cookie_values.append(kwargs)
    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error: raise self.error
        return self.response

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error: raise self.error
        return self.response


def credential():
    return SessionCredential(({"name": "crew", "value": "opaque", "domain": ".trycrew.com", "path": "/"},))


def test_session_transport_injects_cookie_without_auth_header():
    session = Session(Response({"data": {"currentUser": {"id": "1"}}}))
    result = SessionCookieTransport(lambda: credential(), session=session).execute("CurrentUser", "query X { x }")
    assert result == {"currentUser": {"id": "1"}}
    assert session.cookie_values[0]["value"] == "opaque"
    assert "authorization" not in session.calls[0][1]["headers"]


def test_session_transport_missing_credential_is_unauthorized():
    with pytest.raises(CrewAuthenticationError):
        SessionCookieTransport(lambda: None, session=Session()).execute("CurrentUser", "query X { x }")


def test_session_mutation_timeout_is_uncertain_and_single_attempt():
    session = Session(error=requests.Timeout("nope"))
    with pytest.raises(CrewUncertainWriteError):
        SessionCookieTransport(lambda: credential(), session=session).execute(
            "Move", "mutation Move { move }", is_mutation=True
        )
    assert len(session.calls) == 1


def test_default_session_cookie_transports_do_not_share_cookie_jars():
    first = SessionCookieTransport(lambda: credential())
    second = SessionCookieTransport(lambda: credential())
    assert first.session is not second.session


@pytest.mark.parametrize("status,payload", [
    (500, {"error": "server"}),
    (429, {"error": "rate_limited"}),
])
def test_session_mutation_http_failure_is_uncertain(status, payload):
    response = Response(payload)
    response.status_code = status
    session = Session(response)
    with pytest.raises(CrewUncertainWriteError):
        SessionCookieTransport(lambda: credential(), session=session).execute(
            "Move", "mutation Move { move }", is_mutation=True
        )
    assert len(session.calls) == 1


def test_broker_transport_sends_narrow_request_with_capability(tmp_path):
    capability_file = tmp_path / "broker-capability"
    capability_file.write_text("synthetic-capability\n")
    session = Session(Response({"data": {"currentUser": {"id": "1"}}}))

    result = BrokerCrewTransport(
        "http://host.docker.internal:8787", capability_file, session=session
    ).execute("CurrentUser", "query CurrentUser { currentUser { id } }", {"page": 2})

    assert result == {"currentUser": {"id": "1"}}
    url, request = session.calls[0]
    assert url == "http://host.docker.internal:8787/graphql"
    assert request["json"] == {
        "operation_name": "CurrentUser",
        "query": "query CurrentUser { currentUser { id } }",
        "variables": {"page": 2},
        "is_mutation": False,
    }
    assert request["headers"] == {"X-SimpleCrew-Capability": "synthetic-capability"}


@pytest.mark.parametrize(
    ("status", "payload", "error_type"),
    [
        (401, {"error": "unauthorized"}, CrewAuthenticationError),
        (503, {"error": "unreachable"}, CrewTransportError),
        (502, {"error": "api_error"}, CrewAPIError),
        (503, {"error": "uncertain_write"}, CrewUncertainWriteError),
    ],
)
def test_broker_transport_maps_sanitized_broker_errors(tmp_path, status, payload, error_type):
    capability_file = tmp_path / "broker-capability"
    capability_file.write_text("do-not-disclose")
    response = Response(payload)
    response.status_code = status

    with pytest.raises(error_type) as caught:
        BrokerCrewTransport("http://broker", capability_file, session=Session(response)).execute(
            "Move", "mutation Move { move }", is_mutation=True
        )

    assert "do-not-disclose" not in str(caught.value)


def test_broker_transport_timeout_is_broker_unavailable_for_read(tmp_path):
    capability_file = tmp_path / "broker-capability"
    capability_file.write_text("synthetic-capability")
    session = Session(error=requests.Timeout("contains-network-detail"))

    with pytest.raises(BrokerUnavailableError) as caught:
        BrokerCrewTransport("http://broker", capability_file, session=session).execute(
            "CurrentUser", "query CurrentUser { currentUser { id } }"
        )

    assert "contains-network-detail" not in str(caught.value)
    assert len(session.calls) == 1


def test_broker_health_maps_locked_credential_without_disclosing_capability(tmp_path):
    capability_file = tmp_path / "broker-capability"
    capability_file.write_text("do-not-disclose")
    session = Session(Response({"state": "credential_locked", "message": "safe"}))

    with pytest.raises(CredentialLockedError) as caught:
        BrokerCrewTransport("http://broker", capability_file, session=session).execute(
            "CrewConnectionHealth", "query CrewConnectionHealth { currentUser { id } }"
        )

    assert session.calls[0][0] == "http://broker/health"
    assert "do-not-disclose" not in str(caught.value)


def test_broker_transport_proxies_sanitized_renewal(tmp_path):
    capability_file = tmp_path / "broker-capability"
    capability_file.write_text("synthetic-capability")
    session = Session(Response({"session_id": "renew-1"}))
    transport = BrokerCrewTransport("http://broker", capability_file, session=session)

    assert transport.start_renewal() == ({"session_id": "renew-1"}, 200)
    assert session.calls[0][0] == "http://broker/renew/start"
    session.response = Response({"status": "healthy", "message": "Crew connection is healthy"})
    assert transport.renewal_status("renew-1") == (
        {"status": "healthy", "message": "Crew connection is healthy"}, 200
    )
    assert session.calls[1][0] == "http://broker/renew/status/renew-1"
