from typing import Callable, Optional, Protocol


class CredentialProvider(Protocol):
    def get_bearer_token(self) -> Optional[str]: ...
    def describe(self) -> str: ...


class StoredBearerTokenProvider:
    def __init__(self, token_loader: Callable[[], Optional[str]]):
        self._token_loader = token_loader

    def get_bearer_token(self) -> Optional[str]:
        return self._token_loader()

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
