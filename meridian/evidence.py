"""Auditable metadata and provenance links for encrypted financial evidence."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from meridian.db import run_migrations
from meridian.storage import EncryptedBlobStore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class EvidenceItem:
    id: int
    source_kind: str
    source_id: str
    content_hash: str
    mime_type: str
    size_bytes: int
    title: str | None
    expires_at: str | None
    revoked_at: str | None
    content_deleted_at: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class EvidenceLink:
    id: int
    evidence_id: int
    target_kind: str
    target_id: str
    relation: str
    provenance: str
    created_at: str


class EvidenceRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path
        run_migrations(db_path)

    def _connect(self):
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def add_item(
        self,
        *,
        source_kind: str,
        source_id: str,
        content_hash: str,
        mime_type: str,
        size_bytes: int,
        expires_at: str | None = None,
        title: str | None = None,
    ) -> EvidenceItem:
        if not source_kind or not source_id or not mime_type:
            raise ValueError("source_kind, source_id, and mime_type are required")
        if len(content_hash) != 64 or size_bytes < 0:
            raise ValueError("invalid evidence content metadata")
        timestamp = _now()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO evidence_items(
                       source_kind, source_id, content_hash, mime_type, size_bytes,
                       title, expires_at, created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(source_kind, source_id, content_hash) DO UPDATE SET
                       title=excluded.title, expires_at=excluded.expires_at,
                       updated_at=excluded.updated_at""",
                (
                    source_kind,
                    source_id,
                    content_hash,
                    mime_type,
                    size_bytes,
                    title,
                    expires_at,
                    timestamp,
                    timestamp,
                ),
            )
            row = connection.execute(
                """SELECT * FROM evidence_items
                   WHERE source_kind=? AND source_id=? AND content_hash=?""",
                (source_kind, source_id, content_hash),
            ).fetchone()
        return EvidenceItem(**dict(row))

    def get_item(self, item_id: int, *, include_inaccessible: bool = False):
        condition = (
            ""
            if include_inaccessible
            else " AND revoked_at IS NULL AND content_deleted_at IS NULL"
        )
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT * FROM evidence_items WHERE id=?{condition}", (item_id,)
            ).fetchone()
        return EvidenceItem(**dict(row)) if row is not None else None

    def add_link(
        self,
        *,
        evidence_id: int,
        target_kind: str,
        target_id: str,
        relation: str,
        provenance: str,
    ) -> EvidenceLink:
        timestamp = _now()
        with self._connect() as connection:
            cursor = connection.execute(
                """INSERT INTO evidence_links(
                       evidence_id, target_kind, target_id, relation, provenance, created_at
                   ) VALUES (?, ?, ?, ?, ?, ?)""",
                (evidence_id, target_kind, target_id, relation, provenance, timestamp),
            )
            row = connection.execute(
                "SELECT * FROM evidence_links WHERE id=?", (cursor.lastrowid,)
            ).fetchone()
        return EvidenceLink(**dict(row))

    def list_links(self, evidence_id: int) -> list[EvidenceLink]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM evidence_links WHERE evidence_id=? ORDER BY id",
                (evidence_id,),
            ).fetchall()
        return [EvidenceLink(**dict(row)) for row in rows]

    def list_links_for_target(
        self, target_kind: str, target_id: str
    ) -> list[EvidenceLink]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT * FROM evidence_links
                   WHERE target_kind=? AND target_id=? ORDER BY id""",
                (target_kind, target_id),
            ).fetchall()
        return [EvidenceLink(**dict(row)) for row in rows]

    def remove_links_for_target(self, target_kind: str, target_id: str) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM evidence_links WHERE target_kind=? AND target_id=?",
                (target_kind, target_id),
            )
        return cursor.rowcount

    def revoke_source(self, source_kind: str, source_id: str) -> int:
        timestamp = _now()
        with self._connect() as connection:
            cursor = connection.execute(
                """UPDATE evidence_items SET revoked_at=?, updated_at=?
                   WHERE source_kind=? AND source_id=? AND revoked_at IS NULL""",
                (timestamp, timestamp, source_kind, source_id),
            )
        return cursor.rowcount

    def sweep_expired(
        self, store: EncryptedBlobStore, *, as_of: str | None = None
    ) -> int:
        timestamp = as_of or _now()
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT id, content_hash FROM evidence_items
                   WHERE expires_at IS NOT NULL AND expires_at <= ?
                     AND content_deleted_at IS NULL""",
                (timestamp,),
            ).fetchall()
            for row in rows:
                connection.execute(
                    "UPDATE evidence_items SET content_deleted_at=?, updated_at=? WHERE id=?",
                    (timestamp, timestamp, row["id"]),
                )
            hashes = {row["content_hash"] for row in rows}
            for content_hash in hashes:
                live = connection.execute(
                    """SELECT 1 FROM evidence_items
                       WHERE content_hash=? AND content_deleted_at IS NULL AND revoked_at IS NULL
                       LIMIT 1""",
                    (content_hash,),
                ).fetchone()
                if live is None:
                    store.delete(content_hash)
        return len(rows)
