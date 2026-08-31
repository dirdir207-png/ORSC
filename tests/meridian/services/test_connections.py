import json

from meridian.connections import ConnectionRepository, ConnectionState
from meridian.connectors.calendar import READ_ONLY_CALENDAR_SCOPE
from meridian.connectors.email import READ_ONLY_GMAIL_SCOPE
from meridian.repository import FinancialRepository
from meridian.services.connections import build_connections, get_connection_detail


def _financial_connection(graph: FinancialRepository) -> None:
    run = graph.begin_sync_run(
        provider="crew",
        connection_external_id="private-household-id",
        connection_name="Crew",
    )
    graph.finish_sync_run(
        run.id,
        status="complete",
        accounts_synced=0,
        transactions_synced=0,
        errors=0,
    )


def test_connections_group_money_evidence_and_time_without_secret_fields(tmp_path):
    graph = FinancialRepository(str(tmp_path / "financial.db"))
    authorizations = ConnectionRepository(graph.db_path)
    _financial_connection(graph)
    gmail = authorizations.upsert(
        kind="gmail",
        display_name="Gmail",
        state=ConnectionState.CONNECTED,
        granted_scopes=(READ_ONLY_GMAIL_SCOPE,),
        last_successful_at="2026-08-31T07:47:00Z",
        retention_days=365,
    )
    authorizations.upsert(
        kind="calendar",
        display_name="Google Calendar",
        state=ConnectionState.CONNECTED,
        granted_scopes=(READ_ONLY_CALENDAR_SCOPE,),
        last_successful_at="2026-08-31T07:52:00Z",
        retention_days=90,
    )

    payload = build_connections(graph, authorizations, selected_id=gmail.public_id)

    assert [group["kind"] for group in payload["groups"]] == [
        "money",
        "evidence",
        "time",
    ]
    assert payload["selected"]["public_id"] == gmail.public_id
    assert payload["selected"]["permissions"] == [
        "Read bills, statements, and receipts"
    ]
    assert payload["selected"]["safeguards"]["read_only"] is True
    serialized = json.dumps(payload)
    assert "private-household-id" not in serialized
    assert "access_token" not in serialized
    assert "external_id" not in serialized


def test_connection_detail_is_absent_for_unknown_public_id(tmp_path):
    graph = FinancialRepository(str(tmp_path / "financial.db"))
    authorizations = ConnectionRepository(graph.db_path)

    assert get_connection_detail(authorizations, "gmail_missing") is None
