from dataclasses import dataclass
from enum import Enum

from .client import CrewAPIError, CrewAuthenticationError, CrewTransportError


class BrokerUnavailableError(CrewTransportError):
    """The Docker application could not reach the local Crew broker."""


class CredentialLockedError(CrewAuthenticationError):
    """The broker could not unlock the encrypted Crew session."""


class CrewHealthState(str, Enum):
    HEALTHY = "healthy"
    UNAUTHORIZED = "unauthorized"
    UNREACHABLE = "unreachable"
    API_ERROR = "api_error"
    BROKER_UNAVAILABLE = "broker_unavailable"
    CREDENTIAL_LOCKED = "credential_locked"


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
        except CredentialLockedError:
            return CrewHealth(CrewHealthState.CREDENTIAL_LOCKED, "Crew credential storage needs attention")
        except BrokerUnavailableError:
            return CrewHealth(CrewHealthState.BROKER_UNAVAILABLE, "The Crew session broker is unavailable")
        except CrewAuthenticationError:
            return CrewHealth(CrewHealthState.UNAUTHORIZED, "Crew authentication needs attention")
        except CrewTransportError:
            return CrewHealth(CrewHealthState.UNREACHABLE, "Crew cannot be reached from this Mac")
        except CrewAPIError:
            return CrewHealth(CrewHealthState.API_ERROR, "Crew responded with an unexpected API error")
