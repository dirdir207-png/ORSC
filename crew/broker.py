import hmac
import ipaddress
import threading
import uuid
from dataclasses import dataclass

from flask import Flask, jsonify, request

from .client import (
    CrewAPIError,
    CrewAuthenticationError,
    CrewTransportError,
    CrewUncertainWriteError,
)
from .session_credentials import CredentialDecryptionError


@dataclass
class BrokerConfig:
    capability: str
    credential_store: object
    transport: object
    allowed_operations: frozenset[str]
    operation_documents: dict[str, tuple[str, bool]] | None = None
    capturer_factory: object | None = None
    renewal_timeout_seconds: float = 300

    @staticmethod
    def validate_bind_host(host: str) -> None:
        try:
            address = ipaddress.ip_address(host)
        except ValueError as exc:
            raise ValueError("Crew broker must bind to a loopback address") from exc
        if not address.is_loopback:
            raise ValueError("Crew broker must bind to a loopback address")


def create_broker_app(config: BrokerConfig) -> Flask:
    app = Flask("simplecrew-crew-broker")
    app.config["MAX_CONTENT_LENGTH"] = 1_000_000
    renewal_lock = threading.Lock()
    renewal_statuses: dict[str, dict[str, str]] = {}
    active_renewal: list[str | None] = [None]

    @app.before_request
    def require_capability():
        supplied = request.headers.get("X-SimpleCrew-Capability", "")
        if not hmac.compare_digest(supplied, config.capability):
            return jsonify({"error": "unauthorized"}), 401
        return None

    @app.get("/health")
    def health():
        try:
            if config.credential_store.load() is None:
                return jsonify({"state": "unauthorized", "message": "Crew authentication needs attention"})
            config.transport.execute("CrewConnectionHealth", "query CrewConnectionHealth { currentUser { id } }")
            return jsonify({"state": "healthy", "message": "Crew connection is healthy"})
        except CredentialDecryptionError:
            return jsonify({"state": "credential_locked", "message": "Crew credential storage needs attention"})
        except CrewAuthenticationError:
            return jsonify({"state": "unauthorized", "message": "Crew authentication needs attention"})
        except CrewTransportError:
            return jsonify({"state": "unreachable", "message": "Crew cannot be reached from this Mac"})
        except CrewAPIError:
            return jsonify({"state": "api_error", "message": "Crew responded with an unexpected API error"})

    @app.post("/graphql")
    def graphql():
        payload = request.get_json(silent=True) or {}
        allowed = {"operation_name", "query", "variables", "is_mutation"}
        operation_name = payload.get("operation_name")
        if set(payload) - allowed or operation_name not in config.allowed_operations:
            return jsonify({"error": "invalid_request"}), 400
        if not isinstance(payload.get("query"), str) or not isinstance(payload.get("variables", {}), dict):
            return jsonify({"error": "invalid_request"}), 400
        if not isinstance(payload.get("is_mutation", False), bool):
            return jsonify({"error": "invalid_request"}), 400
        documents = config.operation_documents
        if documents is not None:
            document = documents.get(operation_name)
            if document is None:
                return jsonify({"error": "invalid_request"}), 400
            expected_query, expected_mutation = document
            if payload["query"] != expected_query or payload.get("is_mutation", False) is not expected_mutation:
                return jsonify({"error": "invalid_request"}), 400
        else:
            query_kind = payload["query"].lstrip().split(None, 1)[0].lower()
            expected_mutation = operation_name in {"Move", "InitiateTransferScottie"}
            if query_kind not in {"query", "mutation"} or (query_kind == "mutation") is not expected_mutation:
                return jsonify({"error": "invalid_request"}), 400
        try:
            data = config.transport.execute(
                payload["operation_name"], payload["query"], payload.get("variables"),
                is_mutation=bool(payload.get("is_mutation", False)),
            )
            return jsonify({"data": data})
        except CrewAuthenticationError:
            return jsonify({"error": "unauthorized"}), 401
        except CrewUncertainWriteError:
            return jsonify({"error": "uncertain_write"}), 503
        except CrewTransportError:
            return jsonify({"error": "unreachable"}), 503
        except CrewAPIError:
            return jsonify({"error": "api_error"}), 502

    def run_renewal(session_id: str) -> None:
        try:
            renewal_statuses[session_id] = {
                "status": "waiting_for_user", "message": "Complete Crew login in the opened window"
            }
            if config.capturer_factory is None:
                raise RuntimeError("renewal unavailable")
            with config.capturer_factory() as capturer:
                credential = capturer.capture(config.renewal_timeout_seconds)
            if credential is None:
                raise RuntimeError("renewal incomplete")
            config.transport.execute_with_credential(
                credential,
                "CrewConnectionHealth",
                "query CrewConnectionHealth { currentUser { id } }",
            )
            config.credential_store.save(credential)
            renewal_statuses[session_id] = {
                "status": "healthy", "message": "Crew connection is healthy"
            }
        except Exception:  # noqa: BLE001 - sanitize; never surface exception detail
            renewal_statuses[session_id] = {
                "status": "failed", "message": "Crew authentication could not be renewed"
            }
        finally:
            with renewal_lock:
                if active_renewal[0] == session_id:
                    active_renewal[0] = None

    @app.post("/renew/start")
    def renew_start():
        with renewal_lock:
            if active_renewal[0] is not None:
                return jsonify({
                    "error": "A renewal session is already running",
                    "session_id": active_renewal[0],
                }), 409
            session_id = uuid.uuid4().hex
            active_renewal[0] = session_id
            renewal_statuses[session_id] = {
                "status": "starting", "message": "Opening Crew login"
            }
        threading.Thread(target=run_renewal, args=(session_id,), daemon=True).start()
        return jsonify({"session_id": session_id}), 202

    @app.get("/renew/status/<session_id>")
    def renew_status(session_id: str):
        status = renewal_statuses.get(session_id)
        if status is None:
            return jsonify({"error": "Unknown renewal session"}), 404
        return jsonify(status)

    return app
