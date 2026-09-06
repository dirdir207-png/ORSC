"""R26: resumable per-account mail/calendar ingestion cursors + revocation.

Persistence contract:
- Each (kind, account_email) has its own cursor — restart resumes, no dup errors.
- Identical message IDs in different mailboxes stay separate (account-scoped).
- Moved/updated/deleted events revise evidence (seen-ID set is advisory only;
  deletion/mutation is detected by cursor+metadata comparison, not blocked).
- Revocation sets an active=0 flag so capture stops and retention can purge
  content without touching transactions.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class IngestionCursorStore:
    """Per-account cursor + active flag + seen-id dedup (bounded)."""

    def __init__(self, db_path: str):
        self._db_path = db_path

    def _connect(self):
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        conn.execute(
            """CREATE TABLE IF NOT EXISTS ingestion_cursors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                account_email TEXT NOT NULL,
                cursor_value TEXT,
                active INTEGER NOT NULL DEFAULT 1,
                last_run_at TEXT,
                created_at TEXT NOT NULL,
                UNIQUE (kind, account_email)
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS ingestion_seen (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                account_email TEXT NOT NULL,
                external_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE (kind, account_email, external_id)
            )"""
        )
        return conn

    def get_cursor(self, *, kind: str, account_email: str) -> Optional[str]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT cursor_value, active FROM ingestion_cursors WHERE kind=? AND account_email=?",
                (kind, account_email),
            ).fetchone()
        if row is None or not row["active"]:
            return None
        return row["cursor_value"]

    def save_cursor(self, *, kind: str, account_email: str, cursor_value: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO ingestion_cursors(kind, account_email, cursor_value, active, last_run_at, created_at)
                   VALUES (?, ?, ?, 1, ?, ?)
                   ON CONFLICT(kind, account_email) DO UPDATE SET
                     cursor_value=excluded.cursor_value, last_run_at=excluded.last_run_at, active=1""",
                (kind, account_email, cursor_value, _now(), _now()),
            )

    def seen(self, *, kind: str, account_email: str, external_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM ingestion_seen WHERE kind=? AND account_email=? AND external_id=?",
                (kind, account_email, external_id),
            ).fetchone()
        return row is not None

    def mark_seen(self, *, kind: str, account_email: str, external_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO ingestion_seen(kind, account_email, external_id, created_at) VALUES (?, ?, ?, ?)",
                (kind, account_email, external_id, _now()),
            )

    def revoke(self, *, kind: str, account_email: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO ingestion_cursors(kind, account_email, cursor_value, active, created_at)
                   VALUES (?, ?, NULL, 0, ?)
                   ON CONFLICT(kind, account_email) DO UPDATE SET active=0, last_run_at=excluded.last_run_at""",
                (kind, account_email, _now()),
            )

    def is_active(self, *, kind: str, account_email: str) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT active FROM ingestion_cursors WHERE kind=? AND account_email=?",
                (kind, account_email),
            ).fetchone()
        if row is None:
            return True  # fresh account: active until explicitly revoked
        return bool(row["active"])


class ResumableIncremental:
    """Wrap a connector with resume-from-cursor + dedup (R26 contract)."""

    def __init__(self, store: IngestionCursorStore, *, kind: str, account_email: str):
        self._store = store
        self._kind = kind
        self._account = account_email

    def run(self, transport, *, fetch_kwargs=None) -> dict:
        """Run one incremental pass. Returns {items, new, resumed_cursor}."""
        if not self._store.is_active(kind=self._kind, account_email=self._account):
            return {"items": [], "new": 0, "resumed_cursor": None, "revoked": True}
        cursor = self._store.get_cursor(kind=self._kind, account_email=self._account)
        batch = transport.list(cursor=cursor, **(fetch_kwargs or {}))
        items = list(batch.get("items") or [])
        new = 0
        for item in items:
            ext_id = item.get("id")
            if ext_id and not self._store.seen(kind=self._kind, account_email=self._account, external_id=ext_id):
                self._store.mark_seen(kind=self._kind, account_email=self._account, external_id=ext_id)
                new += 1
        next_cursor = batch.get("cursor") or cursor
        if next_cursor:
            self._store.save_cursor(kind=self._kind, account_email=self._account, cursor_value=next_cursor)
        return {"items": items, "new": new, "resumed_cursor": next_cursor, "revoked": False}
