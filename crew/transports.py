from typing import Any

import requests

from .client import (
    CrewAPIError,
    CrewAuthenticationError,
    CrewTransportError,
    CrewUncertainWriteError,
    _looks_like_auth_error,
)
from .health import BrokerUnavailableError, CredentialLockedError


class BrokerCrewTransport:
    def __init__(self, base_url, capability_file, timeout_seconds=15, session=requests):
        self.base_url = str(base_url).rstrip("/")
        self.capability_file = capability_file
        self.timeout_seconds = timeout_seconds
        self.session = session

    def _headers(self):
        try:
            capability = self.capability_file.read_text().strip()
        except (OSError, AttributeError) as exc:
            raise BrokerUnavailableError("The Crew session broker is unavailable") from exc
        if not capability:
            raise BrokerUnavailableError("The Crew session broker is unavailable")
        return {"X-SimpleCrew-Capability": capability}

    def execute(self, operation_name: str, query: str, variables: dict[str, Any] | None = None, *, is_mutation: bool = False):
        try:
            if operation_name == "CrewConnectionHealth":
                response = self.session.get(
                    f"{self.base_url}/health", headers=self._headers(), timeout=self.timeout_seconds
                )
                return self._health_result(response)
            response = self.session.post(
                f"{self.base_url}/graphql",
                headers=self._headers(),
                json={
                    "operation_name": operation_name,
                    "query": query,
                    "variables": variables or {},
                    "is_mutation": is_mutation,
                },
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            if is_mutation:
                raise CrewUncertainWriteError("Crew write outcome is uncertain; verify state before retrying") from exc
            raise BrokerUnavailableError("The Crew session broker is unavailable") from exc
        return self._graphql_result(response)

    def start_renewal(self):
        return self._renewal_request("post", "/renew/start")

    def renewal_status(self, session_id: str):
        if not session_id or any(not (c.isalnum() or c in "-_") for c in session_id):
            return {"error": "Unknown renewal session"}, 404
        return self._renewal_request("get", f"/renew/status/{session_id}")

    def _renewal_request(self, method: str, path: str):
        try:
            response = getattr(self.session, method)(
                f"{self.base_url}{path}", headers=self._headers(), timeout=self.timeout_seconds
            )
            body = self._json(response)
        except (requests.RequestException, CrewAPIError) as exc:
            raise BrokerUnavailableError("The Crew session broker is unavailable") from exc
        allowed = {key: body[key] for key in ("session_id", "status", "message", "error") if key in body}
        return allowed, response.status_code

    @staticmethod
    def _json(response):
        try:
            body = response.json()
        except ValueError as exc:
            raise CrewAPIError("Crew broker returned an invalid response") from exc
        if not isinstance(body, dict):
            raise CrewAPIError("Crew broker returned an invalid response")
        return body

    def _health_result(self, response):
        body = self._json(response)
        state = body.get("state")
        if state == "healthy":
            return body
        self._raise_error(state)

    def _graphql_result(self, response):
        body = self._json(response)
        if response.status_code < 400 and "data" in body:
            return body["data"]
        self._raise_error(body.get("error"))

    @staticmethod
    def _raise_error(error):
        if error == "credential_locked":
            raise CredentialLockedError("Crew credential storage needs attention")
        if error == "unauthorized":
            raise CrewAuthenticationError("Crew authentication needs attention")
        if error == "unreachable":
            raise CrewTransportError("Crew cannot be reached from this Mac")
        if error == "uncertain_write":
            raise CrewUncertainWriteError("Crew write outcome is uncertain; verify state before retrying")
        if error == "api_error":
            raise CrewAPIError("Crew responded with an unexpected API error")
        raise CrewAPIError("Crew broker returned an unexpected response")


class SessionCookieTransport:
    def __init__(self, credential_loader, endpoint="https://api.trycrew.com/willow/graphql", timeout_seconds=15, session=None):
        self._credential_loader = credential_loader
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()

    def execute(self, operation_name: str, query: str, variables: dict[str, Any] | None = None, *, is_mutation: bool = False):
        credential = self._credential_loader()
        if credential is None:
            raise CrewAuthenticationError("Crew session credential is missing")
        return self.execute_with_credential(
            credential, operation_name, query, variables, is_mutation=is_mutation
        )

    def execute_with_credential(self, credential, operation_name: str, query: str, variables: dict[str, Any] | None = None, *, is_mutation: bool = False):
        for cookie in credential.cookies:
            self.session.cookies.set(
                name=str(cookie["name"]), value=str(cookie["value"]),
                domain=str(cookie.get("domain") or ".trycrew.com"), path=str(cookie.get("path") or "/"),
            )
        try:
            response = self.session.post(
                self.endpoint,
                headers={"accept": "*/*", "content-type": "application/json"},
                json={"operationName": operation_name, "variables": variables or {}, "query": query},
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            if is_mutation:
                raise CrewUncertainWriteError("Crew write outcome is uncertain; verify state before retrying") from exc
            raise CrewTransportError("Crew is unreachable") from exc
        if is_mutation and response.status_code >= 400:
            raise CrewUncertainWriteError("Crew write outcome is uncertain; verify state before retrying")
        if response.status_code in (401, 403):
            raise CrewAuthenticationError("Crew rejected the current session")
        try:
            body = response.json()
        except ValueError as exc:
            raise CrewAPIError("Crew returned an invalid response") from exc
        errors = body.get("errors") or []
        if errors:
            if _looks_like_auth_error(errors):
                raise CrewAuthenticationError("Crew rejected the current session")
            raise CrewAPIError(str(errors[0].get("message") or "Crew GraphQL request failed"))
        return body.get("data") or {}
