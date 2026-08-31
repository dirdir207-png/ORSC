"""Sanitized metadata for user-controlled external connections.

Provider credentials remain in their owning adapters. This repository stores
only presentation-safe state, scope names, freshness, and retention policy.
"""

from __future__ import annotations

import json
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from .db import run_migrations


class ConnectionState(str, Enum):
    CONNECTED = "connected"
    PENDING = "pending"
    LIMITED = "limited"
    FAILED = "failed"
    REVOKED = "revoked"


@dataclass(frozen=True)
class ConnectionRecord:
    public_id: str
    kind: str
    display_name: str
    state: ConnectionState
    granted_scopes: tuple[str, ...]
    last_successful_at: str | None
    retention_days: int | None
    created_at: str
    updated_at: str


def public_connection_id(kind: str, record_id: int | None = None) -> str:
    """Return an opaque browser-safe identifier without provider identity."""
    suffix = str(record_id) if record_id is not None else secrets.token_hex(8)
    return f"{kind}_{suffix}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ConnectionRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path
        run_migrations(db_path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def upsert(
        self,
        *,
        kind: str,
        display_name: str,
        state: ConnectionState,
        granted_scopes: tuple[str, ...],
        last_successful_at: str | None,
        retention_days: int | None,
        public_id: str | None = None,
    ) -> ConnectionRecord:
        if not kind or not display_name:
            raise ValueError("kind and display_name are required")
        if retention_days is not None and retention_days < 0:
            raise ValueError("retention_days must be non-negative")
        connection_id = public_id or public_connection_id(kind)
        timestamp = _now()
        scopes = json.dumps(sorted(set(granted_scopes)), separators=(",", ":"))
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO connection_authorizations (
                    public_id, kind, display_name, state, granted_scopes,
                    last_successful_at, retention_days, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(public_id) DO UPDATE SET
                    kind = excluded.kind,
                    display_name = excluded.display_name,
                    state = excluded.state,
                    granted_scopes = excluded.granted_scopes,
                    last_successful_at = excluded.last_successful_at,
                    retention_days = excluded.retention_days,
                    updated_at = excluded.updated_at
                """,
                (
                    connection_id,
                    kind,
                    display_name,
                    ConnectionState(state).value,
                    scopes,
                    last_successful_at,
                    retention_days,
                    timestamp,
                    timestamp,
                ),
            )
        record = self.get(connection_id)
        if record is None:  # pragma: no cover - guarded by the successful insert
            raise RuntimeError("connection metadata was not persisted")
        return record

    def get(self, public_id: str) -> ConnectionRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM connection_authorizations WHERE public_id = ?",
                (public_id,),
            ).fetchone()
        return self._from_row(row) if row is not None else None

    def list_all(self) -> list[ConnectionRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM connection_authorizations ORDER BY id"
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def mark_state(
        self,
        public_id: str,
        state: ConnectionState,
        *,
        last_successful_at: str | None = None,
    ) -> ConnectionRecord:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE connection_authorizations
                SET state = ?,
                    last_successful_at = COALESCE(?, last_successful_at),
                    updated_at = ?
                WHERE public_id = ?
                """,
                (
                    ConnectionState(state).value,
                    last_successful_at,
                    _now(),
                    public_id,
                ),
            )
        if cursor.rowcount != 1:
            raise KeyError(public_id)
        record = self.get(public_id)
        if record is None:  # pragma: no cover - guarded by rowcount
            raise KeyError(public_id)
        return record

    def revoke(self, public_id: str) -> ConnectionRecord:
        return self.mark_state(public_id, ConnectionState.REVOKED)

    @staticmethod
    def _from_row(row: sqlite3.Row) -> ConnectionRecord:
        scopes = json.loads(row["granted_scopes"])
        return ConnectionRecord(
            public_id=row["public_id"],
            kind=row["kind"],
            display_name=row["display_name"],
            state=ConnectionState(row["state"]),
            granted_scopes=tuple(str(scope) for scope in scopes),
            last_successful_at=row["last_successful_at"],
            retention_days=row["retention_days"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
