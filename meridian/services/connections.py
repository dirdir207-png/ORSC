"""Presentation-safe read models for Meridian connection settings."""

from __future__ import annotations

from typing import Protocol

from meridian.connections import (
    ConnectionRecord,
    ConnectionRepository,
    ConnectionState,
    public_connection_id,
)


class FinancialConnectionSource(Protocol):
    def list_connection_freshness(self): ...


_GROUP = {
    "crew": "money",
    "simplefin": "money",
    "lunchflow": "money",
    "splitwise": "money",
    "gmail": "evidence",
    "calendar": "time",
}

_USES = {
    "crew": ("Balances", "Transactions", "Income", "Cash flow"),
    "simplefin": ("Balances", "Transactions", "Interest"),
    "lunchflow": ("Balances", "Transactions"),
    "splitwise": ("Reimbursements", "Shared expenses"),
    "gmail": ("Bills", "Statements", "Receipts"),
    "calendar": ("Paydays", "Due dates", "Events"),
}

_PERMISSIONS = {
    "gmail": ("Read bills, statements, and receipts",),
    "calendar": ("Read payday, due-date, travel, and event timing",),
}

_GROUP_LABELS = {
    "money": "Money",
    "evidence": "Evidence",
    "time": "Time",
}


def _authorization_payload(record: ConnectionRecord) -> dict[str, object]:
    return {
        "public_id": record.public_id,
        "kind": record.kind,
        "display_name": record.display_name,
        "group": _GROUP.get(record.kind, "evidence"),
        "state": record.state.value,
        "freshness": record.last_successful_at,
        "uses": list(_USES.get(record.kind, ())),
        "read_only": True,
    }


def _financial_payload(connection) -> dict[str, object]:
    provider = str(connection.provider).lower()
    healthy = connection.status in {"complete", "healthy"}
    return {
        "public_id": public_connection_id(provider, connection.connection_id),
        "kind": provider,
        "display_name": provider.title(),
        "group": "money",
        "state": "connected" if healthy else "failed",
        "freshness": connection.last_successful_at,
        "uses": list(_USES.get(provider, ("Balances", "Transactions"))),
        "read_only": True,
    }


def get_connection_detail(
    authorizations: ConnectionRepository, public_id: str
) -> dict[str, object] | None:
    record = authorizations.get(public_id)
    if record is None:
        return None
    permissions = list(_PERMISSIONS.get(record.kind, ("Read connected source data",)))
    return {
        **_authorization_payload(record),
        "permissions": permissions,
        "retention_days": record.retention_days,
        "can_revoke": record.state is not ConnectionState.REVOKED,
        "safeguards": {
            "read_only": True,
            "individually_revocable": True,
            "proposal_only_financial_changes": True,
        },
        "usage_explanation": (
            "Meridian may enrich forecasts and draft proposals from this source. "
            "It cannot change the source or execute financial actions."
        ),
    }


def build_connections(
    graph: FinancialConnectionSource,
    authorizations: ConnectionRepository,
    *,
    selected_id: str | None = None,
) -> dict[str, object]:
    rows = [_financial_payload(item) for item in graph.list_connection_freshness()]
    rows.extend(_authorization_payload(item) for item in authorizations.list_all())
    groups = []
    for kind in ("money", "evidence", "time"):
        groups.append(
            {
                "kind": kind,
                "label": _GROUP_LABELS[kind],
                "connections": [row for row in rows if row["group"] == kind],
            }
        )
    return {
        "groups": groups,
        "selected": (
            get_connection_detail(authorizations, selected_id)
            if selected_id is not None
            else None
        ),
        "safeguards": {
            "read_only": True,
            "individually_revocable": True,
            "proposal_only_financial_changes": True,
        },
    }
