import threading
import time

from crew.broker import BrokerConfig, create_broker_app
from crew.session_credentials import SessionCredential

CAP = "capability-value"


class Store:
    def __init__(self, value=None): self.value = value
    def load(self): return self.value
    def save(self, value): self.value = value


class Transport:
    def __init__(self): self.calls = []
    def execute(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return {"currentUser": {"id": "1"}}


def app(store=None, transport=None, capturer_factory=None, operation_documents=None):
    return create_broker_app(BrokerConfig(
        capability=CAP,
        credential_store=store or Store(SessionCredential(({"name":"c","value":"v","domain":".trycrew.com","path":"/"},))),
        transport=transport or Transport(),
        allowed_operations=frozenset({"CrewConnectionHealth", "CurrentUser", "Move"}),
        operation_documents=operation_documents,
        capturer_factory=capturer_factory,
    ))


def headers(value=CAP): return {"X-SimpleCrew-Capability": value}


def test_broker_rejects_missing_or_wrong_capability():
    client = app().test_client()
    assert client.get("/health").status_code == 401
    assert client.get("/health", headers=headers("wrong")).get_json() == {"error": "unauthorized"}


def test_health_is_sanitized_and_healthy():
    response = app().test_client().get("/health", headers=headers())
    assert response.get_json() == {"state": "healthy", "message": "Crew connection is healthy"}


def test_graphql_rejects_unknown_operation_and_propagates_mutation_flag():
    transport = Transport()
    client = app(transport=transport).test_client()
    denied = client.post("/graphql", headers=headers(), json={"operation_name":"Anything","query":"query X{x}"})
    assert denied.status_code == 400
    response = client.post("/graphql", headers=headers(), json={
        "operation_name":"Move", "query":"mutation Move { move }", "variables":{"x":1}, "is_mutation":True,
    })
    assert response.get_json()["data"] == {"currentUser":{"id":"1"}}
    assert transport.calls[0][1]["is_mutation"] is True


def test_graphql_rejects_query_mismatch_for_allowlisted_operation():
    client = app().test_client()
    response = client.post("/graphql", headers=headers(), json={
        "operation_name": "CurrentUser",
        "query": "mutation Evil { moveMoney }",
        "variables": {},
        "is_mutation": False,
    })
    assert response.status_code == 400


def test_non_loopback_bind_is_rejected():
    try:
        BrokerConfig.validate_bind_host("0.0.0.0")
    except ValueError as exc:
        assert "loopback" in str(exc).lower()
    else:
        raise AssertionError("non-loopback bind accepted")


def test_graphql_requires_an_exact_registered_document():
    query = "query CurrentUser { currentUser { id } }"
    client = app(operation_documents={"CurrentUser": (query, False)}).test_client()

    accepted = client.post("/graphql", headers=headers(), json={
        "operation_name": "CurrentUser", "query": query, "variables": {}, "is_mutation": False,
    })
    rejected = client.post("/graphql", headers=headers(), json={
        "operation_name": "Move", "query": "mutation Move { move }", "variables": {}, "is_mutation": True,
    })

    assert accepted.status_code == 200
    assert rejected.status_code == 400


def test_renewal_validates_before_save_and_reports_sanitized_status():
    old = SessionCredential(({"name": "old", "value": "old-secret", "domain": ".trycrew.com", "path": "/"},))
    new = SessionCredential(({"name": "new", "value": "new-secret", "domain": ".trycrew.com", "path": "/"},))
    store = Store(old)

    class Capturer:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def capture(self, timeout_seconds): return new

    class ValidatingTransport(Transport):
        def execute_with_credential(self, credential, *args, **kwargs):
            assert credential is new
            return {"currentUser": {"id": "1"}}

    client = app(store=store, transport=ValidatingTransport(), capturer_factory=Capturer).test_client()
    started = client.post("/renew/start", headers=headers()).get_json()
    session_id = started["session_id"]
    for _ in range(100):
        status = client.get(f"/renew/status/{session_id}", headers=headers()).get_json()
        if status["status"] not in {"starting", "waiting_for_user"}:
            break
        time.sleep(0.01)

    assert status == {"status": "healthy", "message": "Crew connection is healthy"}
    assert store.value is new
    assert "secret" not in str(status)


def test_failed_renewal_validation_preserves_existing_credential():
    old = SessionCredential(({"name": "old", "value": "old-secret", "domain": ".trycrew.com", "path": "/"},))
    new = SessionCredential(({"name": "new", "value": "new-secret", "domain": ".trycrew.com", "path": "/"},))
    store = Store(old)

    class Capturer:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def capture(self, timeout_seconds): return new

    class RejectingTransport(Transport):
        def execute_with_credential(self, credential, *args, **kwargs):
            raise RuntimeError("new-secret")

    client = app(store=store, transport=RejectingTransport(), capturer_factory=Capturer).test_client()
    session_id = client.post("/renew/start", headers=headers()).get_json()["session_id"]
    for _ in range(100):
        status = client.get(f"/renew/status/{session_id}", headers=headers()).get_json()
        if status["status"] == "failed": break
        time.sleep(0.01)

    assert status == {"status": "failed", "message": "Crew authentication could not be renewed"}
    assert store.value is old


def test_renewal_is_single_flight_and_unknown_status_is_404():
    gate = threading.Event()

    class Capturer:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def capture(self, timeout_seconds):
            gate.wait(1)

    client = app(capturer_factory=Capturer).test_client()
    first = client.post("/renew/start", headers=headers())
    second = client.post("/renew/start", headers=headers())
    unknown = client.get("/renew/status/not-real", headers=headers())
    gate.set()

    assert first.status_code == 202
    assert second.status_code == 409
    assert set(second.get_json()) == {"error", "session_id"}
    assert unknown.status_code == 404
