"""Stable, authenticated HTTP read models for Meridian."""

import os
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


def _evidence_blob_store(graph=None):
    """Build the encrypted evidence blob store (same as app._evidence_store_factory).

    Intake needs this to persist the raw content so invoice/evidence links can
    later decrypt and display it. Uses the app secret key as the derived key.
    """
    from meridian.storage import DerivedKeyProvider, EncryptedBlobStore

    graph = graph or _repository()
    evidence_root = os.path.join(os.path.dirname(os.path.abspath(graph.db_path)), "evidence")
    return EncryptedBlobStore(evidence_root, DerivedKeyProvider(current_app.secret_key.encode()))


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
        "sender": item.sender,
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


def _transaction_payload_with_suggestion(repository, transaction):
    """Transaction payload plus a data-derived category suggestion (the "smart"
    first guess for the Review editor) and ranked category options."""
    payload = _transaction_payload(transaction)
    if payload["classification"].get("category"):
        payload["suggested_category"] = None
        payload["category_options"] = []
    else:
        payload["suggested_category"] = repository.suggest_category(
            merchant=transaction.merchant,
            description=transaction.description,
        )
        payload["category_options"] = repository.category_options(
            merchant=transaction.merchant,
            description=transaction.description,
        )
    return payload


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
    return jsonify(build_plan(graph, commitments, rules, as_of=as_of, last_paid_by_id=_last_paid_by_id(graph, commitments), paycheck=_paycheck_config(graph), evidence_repository=EvidenceRepository(graph.db_path)))


def _paycheck_config(graph):
    """Load the owner's paycheck config (funding source), if set."""
    from meridian.paycheck import PaycheckRepository

    return PaycheckRepository(graph.db_path).get()


@meridian_api.get("/paycheck")
@login_required
@_safe_read
def paycheck_get():
    graph = _repository()
    cfg = _paycheck_config(graph)
    if cfg is None:
        return jsonify({"paycheck": None})
    return jsonify(
        {
            "paycheck": {
                "cadence": cfg.cadence,
                "amount": cfg.amount,
                "next_date": cfg.next_date,
                "active": cfg.active,
            }
        }
    )


@meridian_api.post("/paycheck")
@login_required
@_safe_read
def paycheck_set():
    """Set the owner's paycheck (funding source). Approval-gated planning
    metadata; never moves money. Reuses the proposal pipeline."""
    from meridian.paycheck import PaycheckConfig, PaycheckRepository

    graph = _repository()
    payload = request.get_json(silent=True) or {}
    cadence = str(payload.get("cadence") or "monthly").lower()
    if cadence not in ("weekly", "biweekly", "monthly", "semimonthly"):
        return _error("invalid_request", "cadence must be weekly, biweekly, monthly, or semimonthly.",
                      "Choose a supported cadence and try again.", 400)
    try:
        amount = float(payload.get("amount"))
    except (TypeError, ValueError):
        return _error("invalid_request", "amount must be a number.", "Enter a paycheck amount.", 400)
    if amount <= 0:
        return _error("invalid_request", "amount must be positive.", "Enter a positive paycheck amount.", 400)
    next_date = str(payload.get("next_date") or "")
    if not next_date:
        return _error("invalid_request", "next_date is required.", "Set the next paycheck date.", 400)
    try:
        date.fromisoformat(next_date)
    except ValueError:
        return _error("invalid_request", "next_date must be an ISO date (YYYY-MM-DD).",
                      "Use a valid date and try again.", 400)
    cfg = PaycheckConfig(cadence=cadence, amount=amount, next_date=next_date, active=bool(payload.get("active", True)))
    PaycheckRepository(graph.db_path).save(cfg)
    return jsonify({"state": "saved", "paycheck": {"cadence": cfg.cadence, "amount": cfg.amount, "next_date": cfg.next_date}})


def _last_paid_by_id(graph, commitment_repository):
    """Best-effort map of commitment_id -> last-paid amount from charge history.

    Drives the ``changed`` bill badge (amount drift) on the Plan card. Empty
    when no charge history matches, so the badge is never fabricated.
    """
    from meridian.billers import build_biller_monitor
    from meridian.repository import FinancialRepository

    financial = graph if isinstance(graph, FinancialRepository) else FinancialRepository(graph.db_path)
    transactions, _cursor = financial.list_transactions(limit=200)
    bills = build_biller_monitor(commitment_repository.list_active(), transactions)
    return {b.commitment_id: b.last_paid_amount for b in bills}


def _icloud_configured() -> bool:
    """iCloud Mail is configured when the owner set the IMAP username + app pw."""
    import os

    return bool(
        os.environ.get("ICLOUD_MAIL_USERNAME")
        and os.environ.get("ICLOUD_MAIL_APP_PASSWORD")
    )


@meridian_api.get("/icloud/status")
@login_required
@_safe_read
def icloud_status():
    """Read-only iCloud Mail connection status (configured or not)."""
    return jsonify(
        {
            "connected": _icloud_configured(),
            "configured": _icloud_configured(),
            "read_only": True,
        }
    )


@meridian_api.post("/icloud/intake")
@login_required
@_safe_read
def icloud_intake():
    """Ingest recent iCloud Mail as evidence (read-only, no iCloud mutation).

    Best-effort pilot: returns a sanitized summary. Quarantines/errors never
    leak message bodies.
    """
    from meridian.connectors.icloud_mail import IcloudMailReadError, IcloudMailTransport
    from meridian.evidence import EvidenceRepository
    from meridian.gmail_intake import ingest_icloud_recent
    from meridian.repository import FinancialRepository

    graph = _repository()
    if not _icloud_configured():
        return _error(
            "connection_unavailable",
            "iCloud Mail is not configured.",
            "Set ICLOUD_MAIL_USERNAME and ICLOUD_MAIL_APP_PASSWORD (an Apple app-specific password) and try again.",
            503,
        )
    try:
        transport = IcloudMailTransport()
        financial = graph if isinstance(graph, FinancialRepository) else FinancialRepository(graph.db_path)
        transactions, _cursor = financial.list_transactions(limit=200)
        summary = ingest_icloud_recent(
            transport=transport,
            evidence_repo=EvidenceRepository(graph.db_path),
            transactions=transactions,
            max_messages=100,
            since_days=30,
            blob_store=_evidence_blob_store(graph),
        )
    except IcloudMailReadError as exc:
        return _error("connection_unavailable", str(exc), "Check the iCloud Mail credentials and try again.", 503)
    return jsonify({"state": "ingested", "summary": summary})


@meridian_api.post("/gmail/intake")
@login_required
@_safe_read
def gmail_intake():
    """Backfill ~30 days of Gmail from every connected Gmail account into evidence.

    Read-only Gmail; builds a refresh-capable OAuth client from the owner's
    env-configured Google client so each stored account token can be refreshed
    on 401. Returns a per-account + total summary of stored mail evidence.
    """
    from meridian.evidence import EvidenceRepository
    from meridian.gmail_intake import ingest_all_gmail_accounts

    graph = _repository()

    def _token_client():
        from meridian.connectors.google_auth import (
            GoogleOAuth2Client,
            GoogleOAuthConfig,
        )

        return GoogleOAuth2Client(GoogleOAuthConfig.from_env(), scopes=("email",))

    summary = ingest_all_gmail_accounts(
        db_path=graph.db_path,
        evidence_repo=EvidenceRepository(graph.db_path),
        token_client=_token_client(),
        max_messages_per_account=50,
        since_days=30,
        blob_store=_evidence_blob_store(graph),
    )
    return jsonify({"state": "ingested", "summary": summary})


@meridian_api.get("/billers/monitor")
@login_required
@_safe_read
def billers_monitor():
    """Read-only biller monitor (R33).

    Computes bill state from Meridian's own bill commitments + transaction
    charge history. No provider/network, no payment-method switching, no
    autopay/statement/biller-health fields (Crew exposes none of these) — every
    returned field is tagged with provenance so nothing looks provider-backed
    when it was computed locally. Reuses existing commitment ids (no second
    bill identity).
    """
    from meridian.billers import build_biller_monitor
    from meridian.repository import FinancialRepository

    graph = _repository()
    _graph, commitment_repository, _rules = _plan_repositories()
    bill_commitments = [
        c for c in commitment_repository.list_active()
    ]
    # Pull available charge history via the financial repository (paged enough
    # to cover bill-charge matching; best-effort on brand aliases).
    financial = graph if isinstance(graph, FinancialRepository) else FinancialRepository(graph.db_path)
    transactions, _cursor = financial.list_transactions(limit=200)
    bills = build_biller_monitor(bill_commitments, transactions)
    return jsonify(
        {
            "bills": [b.__dict__ for b in bills],
            "safeguards": {
                "read_only": True,
                "no_payment_switching": True,
                "no_second_bill_identity": True,
            },
        }
    )


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
    return jsonify(build_today(graph, commitments, rules, paycheck=_paycheck_config(graph)))


@meridian_api.get("/sync")
@login_required
def sync_now():
    """Trigger a live data refresh on demand. Single-flight and safe.

    This is an idempotent read-side synchronization (not a financial mutation),
    so it uses GET for compatibility with the read-only fetch client.
    ``?wait=false`` returns immediately with the current report; the default
    waits for the refresh to finish (snapshots take a few seconds).
    """
    service = current_app.config.get("MERIDIAN_REFRESH_SERVICE")
    if service is None:
        return jsonify({"success": False, "error": "refresh_unavailable"}), 503
    wait = request.args.get("wait", "true").lower() != "false"
    try:
        if wait:
            report = service.refresh_once()
            if report is None:
                return jsonify({"success": False, "error": "refresh_failed"}), 502
            return jsonify(
                {
                    "success": True,
                    "provider": report.provider,
                    "status": report.status,
                    "accounts_synced": report.accounts_synced,
                    "transactions_synced": report.transactions_synced,
                    "errors": report.errors,
                    "refreshed_at": None,
                }
            )
        # Non-blocking: kick a refresh if none is running, report in_progress.
        report = service.refresh_once()
        return jsonify({"success": True, "status": report.status if report else "in_progress"})
    except Exception:  # noqa: BLE001 - the browser never sees provider errors
        return jsonify({"success": False, "error": "refresh_unavailable"}), 502


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
            db_path=graph.db_path if hasattr(graph, "db_path") else None,
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
        from meridian.connectors.google_auth import callback_redirect_uri

        handoff = authorizer(callback_redirect_uri(request.host_url))
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


@meridian_api.route("/connections/oauth/callback", methods=["GET", "POST"])
def settings_connection_oauth_callback():
    """Google OAuth redirect target: exchange code, persist token, mark connected.

    Called by the browser after the owner authorizes in Google (received with
    ?code&state&scope). Tokens are stored per-account in oauth_tokens; the
    connection record is upserted as connected. Read-only scopes only.

    NOT wrapped in @login_required: Google only redirects here after a real
    grant for this app's client, and the single-use code is exchanged and the
    token persisted server-side. Requiring an app session here wasted the
    one-time authorization code whenever the callback arrived in a tab without
    an app session (it 302'd to /login before exchange). The `state`/`kind`
    check and Google's own validation gate this endpoint; it performs no
    privileged financial action beyond storing an OAuth token.
    """
    kind_map = {"gmail": "gmail", "calendar": "calendar"}
    kind = request.args.get("state", "").replace("-connect", "")
    code = request.args.get("code", "")
    if not code or kind not in kind_map:
        return _error(
            "invalid_oauth_callback",
            "The OAuth callback was missing a code or kind.",
            "Start the connection again and authorize in Google.",
            400,
        )
    authorizer = current_app.config.get("MERIDIAN_CONNECTION_AUTHORIZERS", {}).get(kind)
    if authorizer is None:
        return _error(
            "connection_unavailable",
            "The connection provider is not configured.",
            "Set GOOGLE_OAUTH_CLIENT_ID/SECRET for this app.",
            503,
        )
    from meridian.connectors.calendar import READ_ONLY_CALENDAR_SCOPE
    from meridian.connectors.email import READ_ONLY_GMAIL_SCOPE
    from meridian.connectors.google_auth import (
        GoogleOAuth2Client,
        GoogleOAuthConfig,
        GoogleOAuthConfigError,
        OAuthTokenStore,
        email_from_id_token,
    )

    scope = READ_ONLY_GMAIL_SCOPE if kind == "gmail" else READ_ONLY_CALENDAR_SCOPE
    try:
        from meridian.connectors.google_auth import callback_redirect_uri

        client = GoogleOAuth2Client(GoogleOAuthConfig.from_env(), scopes=(scope,))
        tokens = client.exchange(code, redirect_uri=callback_redirect_uri(request.host_url))
    except GoogleOAuthConfigError as exc:
        return _error("connection_unavailable", str(exc), "Configure the OAuth client and retry.", 503)
    except Exception:  # noqa: BLE001 - exchange failure is endpoint-facing
        return _error("oauth_exchange_failed", "Google did not accept the authorization.",
                      "Try the connection again.", 502)
    # The authorizing account is identified by the id_token email claim
    # (granted via openid+email identity scopes); the connector's first
    # successful read may later enrich the record, never orphan it.
    account_email = (
        email_from_id_token(tokens.get("id_token", ""))
        or tokens.get("email")
        or f"{kind}-account"
    )
    OAuthTokenStore(_repository().db_path).save(
        kind=kind,
        account_email=account_email,
        access_token=tokens["access_token"],
        refresh_token=tokens.get("refresh_token", ""),
        expires_at=tokens.get("expires_at"),
    )
    _connection_repository().upsert(
        kind=kind,
        display_name="Gmail" if kind == "gmail" else "Google Calendar",
        state=ConnectionState.CONNECTED,
        granted_scopes=(scope,),
        last_successful_at=_now_iso(),
        retention_days=365 if kind == "gmail" else 90,
    )
    return jsonify({"state": "connected", "kind": kind, "account": account_email})


@meridian_api.post("/connections/oauth/<kind>/<account_email>/revoke")
@login_required
def settings_connection_oauth_revoke(kind: str, account_email: str):
    """R27: revoke ONE OAuth identity (token + ingestion cursor) without
    touching other accounts of the same kind."""
    if kind not in ("gmail", "calendar"):
        return _error("invalid_request", "Unsupported connection kind.", "Choose Gmail or Calendar.", 400)
    from meridian.connection_jobs import IngestionCursorStore

    db_path = _repository().db_path
    # Delete the token row for this identity.
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.execute(
        "DELETE FROM oauth_tokens WHERE kind=? AND account_email=?",
        (kind, account_email),
    )
    conn.commit()
    conn.close()
    IngestionCursorStore(db_path).revoke(kind=kind, account_email=account_email)
    return jsonify({"state": "revoked", "kind": kind, "account": account_email})


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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


@meridian_api.get("/settings/payday")
@login_required
@_safe_read
def settings_payday():
    from meridian.services.payday import build_payday_settings

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
    return jsonify(build_payday_settings(graph, commitments, rules, as_of=as_of))


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
                    _transaction_payload_with_suggestion(repository, item)
                    for item in get_review_queue(repository)
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
    try:
        content = factory().read(item.content_hash)
    except Exception:  # noqa: BLE001 - a missing/undecryptable blob must not
        # surface as a raw provider error; degrade to the evidence's cached facts.
        return _error(
            "evidence_content_missing",
            "This document's content is not stored yet.",
            "It was created before content was persisted; re-run the mail intake to backfill it.",
            404,
        )
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


# ── Crew live-edit proposals ────────────────────────────────────────────────
# Edits to a live Crew bill/rule create an approval-gated proposal; nothing
# reaches Crew until the owner approves and the executor runs.

@meridian_api.post("/crew/bills")
@login_required
@_safe_read
def update_crew_bill_proposal():
    """Propose a live Crew bill edit (approval-gated write-back)."""
    payload = request.get_json(silent=True) or {}
    if not payload.get("billId") or (not payload.get("name") and payload.get("amount") is None):
        return _error("invalid_request", "Provide a billId and a name or amount to update.",
                      "Provide at least one change and try again.", 400)
    return _management_payload("update_crew_bill", payload)


@meridian_api.patch("/crew/bills/<bill_id>/reserve-settings")
@login_required
@_safe_read
def update_crew_bill_reserve_settings_proposal(bill_id: str):
    """Propose a live Crew bill reserve/funding-settings edit."""
    payload = request.get_json(silent=True) or {}
    payload["billReserveId"] = payload.pop("billReserveId", None) or bill_id
    return _management_payload("update_crew_bill_reserve_settings", payload)


@meridian_api.post("/crew/rules")
@login_required
@_safe_read
def create_crew_autopilot_rule_proposal():
    """Propose a new live Crew autopilot rule (approval-gated write-back)."""
    payload = request.get_json(silent=True) or {}
    if not payload.get("name"):
        return _error("invalid_request", "name is required.",
                      "Provide a rule name and try again.", 400)
    return _management_payload("create_crew_autopilot_rule", payload)


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
