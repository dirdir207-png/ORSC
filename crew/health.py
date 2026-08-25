from dataclasses import dataclass
from enum import Enum

from .client import CrewAPIError, CrewAuthenticationError, CrewTransportError


class CrewHealthState(str, Enum):
    HEALTHY = "healthy"
    UNAUTHORIZED = "unauthorized"
    UNREACHABLE = "unreachable"
    API_ERROR = "api_error"


@dataclass(frozen=True)
class CrewHealth:
    state: CrewHealthState
    message: str


HEALTH_QUERY = "query CrewConnectionHealth { currentUser { id } }"


class CredentialHealthService:
    def __init__(self, client):
        self.client = client

    def check(self) -> CrewHealth:
        try:
            self.client.execute("CrewConnectionHealth", HEALTH_QUERY)
            return CrewHealth(CrewHealthState.HEALTHY, "Crew connection is healthy")
        except CrewAuthenticationError:
            return CrewHealth(CrewHealthState.UNAUTHORIZED, "Crew authentication needs attention")
        except CrewTransportError:
            return CrewHealth(CrewHealthState.UNREACHABLE, "Crew cannot be reached from this Mac")
        except CrewAPIError:
            return CrewHealth(CrewHealthState.API_ERROR, "Crew responded with an unexpected API error")
