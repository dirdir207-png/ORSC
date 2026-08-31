"""Stable, authenticated HTTP read models for Meridian."""

from datetime import date
from functools import wraps
from io import BytesIO

from flask import Blueprint, current_app, jsonify, request, send_file
from flask_login import login_required

from meridian.ai.advisor import AdvisorContext
from meridian.commitments import CommitmentRepository
from meridian.connections import ConnectionRepository, ConnectionState
from meridian.evidence import EvidenceRepository
from meridian.funding_repo import FundingRuleRepository
from meridian.models import AccountRecord, TransactionRecord
from meridian.services.accounts import build_accounts
from meridian.services.activity import (
    get_activity,
    get_patterns,
    get_review_queue,
    get_transaction,
)
from meridian.services.connections import build_connections, get_connection_detail
from meridian.services.plan import build_plan
from meridian.services.today import build_today, data_freshness

meridian_api = Blueprint("meridian_api", __name__)


def _repository():
    return current_app.config["MERIDIAN_REPOSITORY_FACTORY"]()


def _evidence_repository(graph=None):
    factory = current_app.config.get("MERIDIAN_EVIDENCE_REPOSITORY_FACTORY")
    if factory:
        return factory()
    graph = graph or _repository()
    return EvidenceRepository(graph.db_path)


def _connection_repository(graph=None):
    factory = current_app.config.get("MERIDIAN_CONNECTIONS_FACTORY")
    if factory:
        return factory()
    graph = graph or _repository()
    return ConnectionRepository(graph.db_path)


def _evidence_payload(repository, link):
    item = repository.get_item(link.evidence_id)
    if item is None:
        return None
    return {
        "id": item.id,
        "title": item.title,
        "source_kind": item.source_kind,
        "mime_type": item.mime_type,
        "size_bytes": item.size_bytes,
        "relation": link.relation,
        "provenance": link.provenance,
        "confidence": None,
        "expires_at": item.expires_at,
        "content_url": f"/api/meridian/evidence/{item.id}/content",
    }


def _plan_repositories():
    graph = _repository()
    commitments = current_app.config.get("MERIDIAN_COMMITMENTS_FACTORY")
    rules = current_app.config.get("MERIDIAN_FUNDING_RULES_FACTORY")
    return (
        graph,
        commitments() if commitments else CommitmentRepository(graph.db_path),
        rules() if rules else FundingRuleRepository(graph.db_path),
    )


def _error(
    code: str,
    message: str,
    recovery_action: str,
    status: int,
    *,
    freshness: dict[str, object] | None = None,
):
    return (
        jsonify(
            {
                "error": {
                    "code": code,
                    "message": message,
                    "recovery_action": recovery_action,
                },
                "data_freshness": freshness
                or {"status": "unavailable", "last_updated_at": None},
            }
        ),
        status,
    )


def _safe_read(view):
    """Keep provider/repository failures out of browser contracts and logs."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        try:
            return view(*args, **kwargs)
        except Exception:
            return _error(
                "financial_data_unavailable",
                "Financial data is temporarily unavailable.",
                "Try again after your provider reconnects.",
                503,
            )

    return wrapped


def _account_payload(account: AccountRecord) -> dict[str, object]:
    return {
        "id": account.id,
        "provider": account.provider,
        "name": account.name,
        "account_type": account.account_type,
        "balance": account.balance,
        "available_balance": account.available_balance,
        "currency": account.currency,
        "is_active": account.is_active,
        "source_updated_at": account.source_updated_at,
        "synced_at": account.synced_at,
    }


def _transaction_payload(transaction: TransactionRecord) -> dict[str, object]:
    return {
        "id": transaction.id,
        "account_id": transaction.account_id,
        "provider": transaction.provider,
        "amount": transaction.amount,
        "currency": transaction.currency,
        "occurred_at": transaction.occurred_at,
        "posted_at": transaction.posted_at,
        "description": transaction.description,
        "merchant": transaction.merchant,
        "status": transaction.status,
        "source_updated_at": transaction.source_updated_at,
        "classification": {
            "category": transaction.classification_category,
            "kind": transaction.classification_kind,
            "confidence": transaction.classification_confidence,
            "rule_id": transaction.classification_rule_id,
            "evidence": transaction.classification_evidence,
            "method": transaction.classification_method,
            "provider": transaction.classification_provider,
            "model": transaction.classification_model,
        },
        "synced_at": transaction.synced_at,
    }


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise ValueError
    return parsed


@meridian_api.get("/plan")
@login_required
@_safe_read
def plan():
    graph, commitments, rules = _plan_repositories()
    as_of_value = request.args.get("as_of")
    try:
        as_of = date.fromisoformat(as_of_value) if as_of_value else date.today()
    except ValueError:
        return _error(
            "invalid_request",
            "as_of must be an ISO date (YYYY-MM-DD).",
            "Use today's date or omit as_of.",
            400,
        )
    return jsonify(build_plan(graph, commitments, rules, as_of=as_of))


@meridian_api.get("/commitments")
@login_required
@_safe_read
def commitments():
    _graph, commitment_repository, rule_repository = _plan_repositories()
    views = []
    for commitment in commitment_repository.list_active():
        views.append(
            {
                "id": commitment.id,
                "type": commitment.type.value,
                "name": commitment.name,
                "status": commitment.status.value,
                "priority": commitment.priority,
                "target_amount": commitment.target_amount,
                "amount": commitment.amount,
                "funded_amount": commitment.funded_amount,
                "due_date": commitment.due_date,
                "target_date": commitment.target_date,
                "buffer_minimum": commitment.buffer_minimum,
                "minimum_payment": commitment.minimum_payment,
                "backing_account_id": commitment.backing_account_id,
                "rule_ids": [
                    rule.id
                    for rule in rule_repository.list_for_commitment(commitment.id)
                ],
            }
        )
    return jsonify({"commitments": views})


@meridian_api.get("/funding-rules")
@login_required
@_safe_read
def funding_rules():
    _graph, _commitments, rule_repository = _plan_repositories()
    views = []
    for rule in rule_repository.list_all():
        views.append(
            {
                "id": rule.id,
                "commitment_id": rule.commitment_id,
                "kind": rule.kind,
                "amount": float(rule.amount) if rule.amount is not None else None,
                "percent": float(rule.percent) if rule.percent is not None else None,
                "cadence": rule.cadence,
                "day_of_month": rule.day_of_month,
                "start_date": rule.start_date.isoformat(),
                "horizon_end": rule.horizon_end.isoformat()
                if rule.horizon_end
                else None,
                "min_contribution": (
                    float(rule.min_contribution)
                    if rule.min_contribution is not None
                    else None
                ),
                "max_contribution": (
                    float(rule.max_contribution)
                    if rule.max_contribution is not None
                    else None
                ),
                "paused": rule.paused,
                "one_time_override": (
                    float(rule.one_time_override)
                    if rule.one_time_override is not None
                    else None
                ),
                "priority": rule.priority,
            }
        )
    return jsonify({"funding_rules": views})


@meridian_api.get("/today")
@login_required
@_safe_read
def today():
    graph, commitments, rules = _plan_repositories()
    return jsonify(build_today(graph, commitments, rules))


@meridian_api.get("/accounts")
@login_required
@_safe_read
def accounts():
    repository = _repository()
    payload = build_accounts(repository)
    payload["accounts"] = [
        account for group in payload["groups"] for account in group["accounts"]
    ]
    return jsonify(payload)


@meridian_api.get("/settings/connections")
@login_required
@_safe_read
def settings_connections():
    graph = _repository()
    return jsonify(
        build_connections(
            graph,
            _connection_repository(graph),
            selected_id=request.args.get("selected"),
        )
    )


@meridian_api.get("/settings/connections/<public_id>")
@login_required
@_safe_read
def settings_connection_detail(public_id: str):
    detail = get_connection_detail(_connection_repository(), public_id)
    if detail is None:
        return _error(
            "connection_not_found",
            "That connection is not available.",
            "Return to Connections and choose an available source.",
            404,
        )
    return jsonify(detail)


@meridian_api.post("/settings/connections/<kind>/authorize")
@login_required
def settings_connection_authorize(kind: str):
    display_names = {"gmail": "Gmail", "calendar": "Google Calendar"}
    if kind not in display_names:
        return _error(
            "unsupported_connection",
            "That connection type is not supported.",
            "Choose Gmail or Google Calendar.",
            400,
        )
    authorizer = current_app.config.get("MERIDIAN_CONNECTION_AUTHORIZERS", {}).get(
        kind
    )
    if authorizer is None:
        return _error(
            "connection_unavailable",
            "Connection setup is temporarily unavailable.",
            "Try again after the connection provider is configured.",
            503,
        )
    try:
        handoff = authorizer()
        authorization_url = handoff["authorization_url"]
        _connection_repository().upsert(
            kind=kind,
            display_name=display_names[kind],
            state=ConnectionState.PENDING,
            granted_scopes=(),
            last_successful_at=None,
            retention_days=365 if kind == "gmail" else 90,
        )
    except Exception:
        return _error(
            "connection_unavailable",
            "Connection setup could not start.",
            "Try again without changing any existing connection.",
            503,
        )
    return jsonify({"state": "pending", "authorization_url": authorization_url})


@meridian_api.post("/settings/connections/<public_id>/revoke")
@login_required
def settings_connection_revoke(public_id: str):
    repository = _connection_repository()
    record = repository.get(public_id)
    if record is None:
        return _error(
            "connection_not_found",
            "That connection is not available.",
            "Return to Connections and choose an available source.",
            404,
        )
    connector = current_app.config.get("MERIDIAN_CONNECTION_CONNECTORS", {}).get(
        public_id
    )
    if connector is None:
        return _error(
            "connection_unavailable",
            "The connection could not be revoked right now.",
            "Try again after the provider reconnects.",
            503,
        )
    try:
        connector.revoke()
        revoked = repository.revoke(public_id)
    except Exception:
        return _error(
            "connection_unavailable",
            "The connection could not be revoked right now.",
            "No connection state was changed. Try again later.",
            503,
        )
    return jsonify({"public_id": revoked.public_id, "state": revoked.state.value})


@meridian_api.get("/activity")
@login_required
@_safe_read
def activity():
    mode = request.args.get("mode", "timeline")
    if mode not in {"timeline", "review", "patterns"}:
        return _error(
            "invalid_request",
            "mode must be timeline, review, or patterns.",
            "Choose an Activity mode and try again.",
            400,
        )
    if mode == "review":
        repository = _repository()
        return jsonify(
            {
                "transactions": [
                    _transaction_payload(item) for item in get_review_queue(repository)
                ],
                "next_cursor": None,
                "data_freshness": data_freshness(
                    repository, include_all_connections=True
                ),
            }
        )
    if mode == "patterns":
        repository = _repository()
        return jsonify(
            {
                "patterns": get_patterns(repository),
                "data_freshness": data_freshness(
                    repository, include_all_connections=True
                ),
            }
        )
    limit_value = request.args.get("limit", "50")
    try:
        limit = _positive_int(limit_value)
        if limit > 200:
            raise ValueError
    except ValueError:
        return _error(
            "invalid_request",
            "limit must be an integer between 1 and 200.",
            "Use a limit between 1 and 200 and try again.",
            400,
        )
    account_id_value = request.args.get("account_id")
    try:
        account_id = _positive_int(account_id_value) if account_id_value else None
    except ValueError:
        return _error(
            "invalid_request",
            "account_id must be a positive integer.",
            "Use a positive account_id and try again.",
            400,
        )

    try:
        page = get_activity(
            _repository(),
            limit=limit,
            cursor=request.args.get("cursor"),
            account_id=account_id,
        )
    except ValueError:
        return _error(
            "invalid_request",
            "The activity cursor is invalid.",
            "Restart from the first Activity page and try again.",
            400,
        )
    return jsonify(
        {
            "transactions": [
                _transaction_payload(transaction)
                for transaction in page["transactions"]
            ],
            "next_cursor": page["next_cursor"],
            "data_freshness": page["data_freshness"],
        }
    )


@meridian_api.get("/transactions/<transaction_id>")
@login_required
@_safe_read
def transaction_detail(transaction_id: str):
    try:
        repository = _repository()
        transaction = get_transaction(repository, _positive_int(transaction_id))
    except ValueError:
        return _error(
            "invalid_request",
            "transaction_id must be a positive integer.",
            "Choose a transaction from Activity and try again.",
            400,
        )
    if transaction is None:
        return _error(
            "transaction_not_found",
            "The requested transaction is not available.",
            "Return to Activity and choose another transaction.",
            404,
            freshness=data_freshness(repository),
        )
    evidence_repository = _evidence_repository(repository)
    evidence = [
        payload
        for link in evidence_repository.list_links_for_target(
            "transaction", str(transaction.id)
        )
        if (payload := _evidence_payload(evidence_repository, link)) is not None
    ]
    return jsonify(
        {
            "transaction": _transaction_payload(transaction),
            "evidence": evidence,
            "data_freshness": data_freshness(
                repository,
                transaction_ids=[transaction.id],
            ),
        }
    )


@meridian_api.get("/evidence/<evidence_id>/content")
@login_required
@_safe_read
def evidence_content(evidence_id: str):
    repository = _evidence_repository()
    try:
        item = repository.get_item(_positive_int(evidence_id))
    except ValueError:
        return _error(
            "invalid_request",
            "evidence_id must be a positive integer.",
            "Open evidence from a Meridian record.",
            400,
        )
    if item is None:
        return _error(
            "evidence_not_found",
            "The evidence content is unavailable or has expired.",
            "Return to the related Meridian record.",
            404,
        )
    factory = current_app.config.get("MERIDIAN_EVIDENCE_BLOB_STORE_FACTORY")
    if factory is None:
        return _error(
            "evidence_storage_unavailable",
            "Evidence storage is not configured.",
            "Configure the encrypted evidence store.",
            503,
        )
    content = factory().read(item.content_hash)
    return send_file(
        BytesIO(content),
        mimetype=item.mime_type,
        download_name=item.title or f"evidence-{item.id}",
        as_attachment=False,
    )


@meridian_api.get("/memory/<workspace>")
@login_required
@_safe_read
def memory_workspace(workspace: str):
    from meridian.services.memory import WORKSPACES, build_memory

    if workspace not in WORKSPACES:
        return _error(
            "invalid_request",
            f"Unknown memory workspace: {workspace}",
            "Choose today, plan, activity, or accounts.",
            404,
        )
    payload = build_memory(_repository().db_path, workspace)
    return jsonify(payload)


def _proposal_sink():
    factory = current_app.config.get("MERIDIAN_PROPOSAL_SINK_FACTORY")
    if factory is None:
        return None
    return factory()


def _management_payload(action_type: str, params: dict):
    sink = _proposal_sink()
    if sink is None:
        return _error(
            "management_unavailable",
            "Action proposals are not configured.",
            "Start the application with the action pipeline enabled.",
            503,
        )
    try:
        proposal = sink(action_type, params)
    except ValueError as error:
        return _error("invalid_request", str(error), "Review the record and try again.", 400)
    return jsonify({"proposal": {"id": proposal["id"], "state": proposal["state"]}}), 202


@meridian_api.post("/assets")
@login_required
@_safe_read
def create_asset_proposal():
    payload = request.get_json(silent=True) or {}
    if not payload.get("name") or not payload.get("category"):
        return _error("invalid_request", "name and category are required.",
                      "Provide both and try again.", 400)
    return _management_payload("create_asset", payload)


@meridian_api.patch("/assets/<asset_id>")
@login_required
@_safe_read
def update_asset_proposal(asset_id: str):
    payload = request.get_json(silent=True) or {}
    try:
        payload["record_id"] = _positive_int(asset_id)
    except ValueError:
        return _error("invalid_request", "asset_id must be a positive integer.",
                      "Provide a valid asset id and try again.", 400)
    return _management_payload("update_asset", payload)


@meridian_api.delete("/assets/<asset_id>")
@login_required
@_safe_read
def delete_asset_proposal(asset_id: str):
    payload = request.get_json(silent=True) or {}
    try:
        payload["record_id"] = _positive_int(asset_id)
    except ValueError:
        return _error("invalid_request", "asset_id must be a positive integer.",
                      "Provide a valid asset id and try again.", 400)
    return _management_payload("delete_asset", payload)


@meridian_api.post("/contracts")
@login_required
@_safe_read
def create_contract_proposal():
    payload = request.get_json(silent=True) or {}
    if not payload.get("name") or not payload.get("kind"):
        return _error("invalid_request", "name and kind are required.",
                      "Provide both and try again.", 400)
    return _management_payload("create_contract", payload)


@meridian_api.patch("/contracts/<contract_id>")
@login_required
@_safe_read
def update_contract_proposal(contract_id: str):
    payload = request.get_json(silent=True) or {}
    try:
        payload["record_id"] = _positive_int(contract_id)
    except ValueError:
        return _error("invalid_request", "contract_id must be a positive integer.",
                      "Provide a valid contract id and try again.", 400)
    return _management_payload("update_contract", payload)


@meridian_api.delete("/contracts/<contract_id>")
@login_required
@_safe_read
def delete_contract_proposal(contract_id: str):
    payload = request.get_json(silent=True) or {}
    try:
        payload["record_id"] = _positive_int(contract_id)
    except ValueError:
        return _error("invalid_request", "contract_id must be a positive integer.",
                      "Provide a valid contract id and try again.", 400)
    return _management_payload("delete_contract", payload)


@meridian_api.post("/transactions/<transaction_id>/classification")
@login_required
@_safe_read
def correct_transaction_classification(transaction_id: str):
    payload = request.get_json(silent=True) or {}
    try:
        repository = _repository()
        transaction = repository.correct_classification(
            _positive_int(transaction_id),
            category=payload.get("category"),
            kind=payload.get("kind"),
            create_rule=payload.get("create_rule") is True,
        )
    except ValueError as error:
        return _error(
            "invalid_request", str(error), "Review the correction and try again.", 400
        )
    return jsonify(
        {"classification": _transaction_payload(transaction)["classification"]}
    )


@meridian_api.post("/classifications/batch")
@login_required
@_safe_read
def batch_correct_transaction_classifications():
    payload = request.get_json(silent=True) or {}
    transaction_ids = payload.get("transaction_ids")
    if not isinstance(transaction_ids, list) or not transaction_ids:
        return _error(
            "invalid_request",
            "transaction_ids is required.",
            "Select transactions and try again.",
            400,
        )
    repository = _repository()
    corrected = []
    try:
        for transaction_id in transaction_ids:
            corrected.append(
                repository.correct_classification(
                    _positive_int(str(transaction_id)),
                    category=payload.get("category"),
                    kind=payload.get("kind"),
                    create_rule=False,
                ).id
            )
    except ValueError as error:
        return _error(
            "invalid_request", str(error), "Review the batch and try again.", 400
        )
    return jsonify({"corrected_transaction_ids": corrected})


@meridian_api.post("/advisor")
@login_required
@_safe_read
def contextual_advisor():
    payload = request.get_json(silent=True) or {}
    context_payload = payload.get("context") or {}
    question = payload.get("question")
    factory = current_app.config.get("MERIDIAN_ADVISOR_FACTORY")
    if factory is None:
        return _error(
            "advisor_unavailable",
            "The contextual advisor is not configured.",
            "Configure an AI provider and try again.",
            503,
        )
    try:
        if not isinstance(question, str) or not question.strip():
            raise ValueError("question is required")
        evidence_ids = context_payload.get("evidence_ids") or []
        if not isinstance(evidence_ids, list) or not all(
            isinstance(item, str) for item in evidence_ids
        ):
            raise ValueError("evidence_ids must be a list of strings")
        context = AdvisorContext(
            kind=context_payload.get("kind"),
            object_id=context_payload.get("object_id"),
            evidence_ids=tuple(evidence_ids),
        )
        result = factory().ask(context, question.strip())
    except ValueError as error:
        return _error(
            "invalid_request",
            str(error),
            "Choose a supported Meridian object and try again.",
            400,
        )
    return jsonify(result)
