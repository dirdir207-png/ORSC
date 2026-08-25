from typing import Callable, Optional, Protocol


class CredentialProvider(Protocol):
    def get_bearer_token(self) -> Optional[str]: ...
    def describe(self) -> str: ...


def _normalize_token(token: Optional[str]) -> Optional[str]:
    """Existing installs may store the full header value ('Bearer xyz').
    CrewClient adds its own prefix, so strip any leading scheme and whitespace."""
    if not token:
        return None
    token = token.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    return token or None


class StoredBearerTokenProvider:
    def __init__(self, token_loader: Callable[[], Optional[str]]):
        self._token_loader = token_loader

    def get_bearer_token(self) -> Optional[str]:
        return _normalize_token(self._token_loader())

    def describe(self) -> str:
        return "stored_bearer_token"

    def __repr__(self) -> str:
        return "StoredBearerTokenProvider()"


class MacCredentialProvider:
    def __init__(self, token_loader: Callable[[], Optional[str]]):
        self._token_loader = token_loader

    def get_bearer_token(self) -> Optional[str]:
        return self._token_loader()

    def describe(self) -> str:
        return "mac_credential_provider"

    def __repr__(self) -> str:
        return "MacCredentialProvider()"
