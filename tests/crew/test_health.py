from crew.client import CrewAPIError, CrewAuthenticationError, CrewTransportError
from crew.health import CredentialHealthService, CrewHealthState


class StubClient:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    def execute(self, *args, **kwargs):
        if self.error:
            raise self.error
        return self.result or {"viewer": {"id": "1"}}


def test_health_is_healthy_for_authenticated_response():
    health = CredentialHealthService(StubClient()).check()
    assert health.state is CrewHealthState.HEALTHY


def test_health_is_unauthorized_for_auth_failure():
    health = CredentialHealthService(StubClient(error=CrewAuthenticationError("bad"))).check()
    assert health.state is CrewHealthState.UNAUTHORIZED


def test_health_is_unreachable_for_transport_failure():
    health = CredentialHealthService(StubClient(error=CrewTransportError("down"))).check()
    assert health.state is CrewHealthState.UNREACHABLE


def test_health_is_api_error_for_graphql_failure():
    health = CredentialHealthService(StubClient(error=CrewAPIError("bad query"))).check()
    assert health.state is CrewHealthState.API_ERROR
