"""Evidence-backed asset and warranty memory with proposal-only corrections."""

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from meridian.db import run_migrations


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Asset:
    id: int | None
    name: str
    category: str
    purchased_on: str | None
    purchase_price: float | None
    return_until: str | None
    maintenance_interval_days: int | None
    replacement_reserve: float | None
    evidence_id: int | None
    evidence_span: str
    confidence: float


@dataclass(frozen=True)
class Warranty:
    id: int | None
    asset_id: int
    provider: str
    expires_on: str | None
    deductible: float | None
    evidence_id: int | None
    evidence_span: str
    confidence: float


@dataclass(frozen=True)
class MemoryEvent:
    kind: str
    title: str
    due_on: str | None
    amount: float | None
    evidence_id: int | None
    confidence: float


@dataclass(frozen=True)
class CorrectionProposal:
    id: int
    asset_id: int
    field: str
    proposed_value: str
    evidence_id: int | None
    status: str
    requires_approval: bool = True


class AssetRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path
        run_migrations(db_path)

    def _connect(self):
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _asset(row):
        values = dict(row)
        values.pop("created_at", None)
        values.pop("updated_at", None)
        return Asset(**values)

    def save_asset(self, asset: Asset) -> Asset:
        timestamp = _now()
        with self._connect() as connection:
            cursor = connection.execute(
                """INSERT INTO assets(
                       name, category, purchased_on, purchase_price, return_until,
                       maintenance_interval_days, replacement_reserve, evidence_id,
                       evidence_span, confidence, created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    asset.name,
                    asset.category,
                    asset.purchased_on,
                    asset.purchase_price,
                    asset.return_until,
                    asset.maintenance_interval_days,
                    asset.replacement_reserve,
                    asset.evidence_id,
                    asset.evidence_span,
                    asset.confidence,
                    timestamp,
                    timestamp,
                ),
            )
            row = connection.execute(
                "SELECT * FROM assets WHERE id=?", (cursor.lastrowid,)
            ).fetchone()
        return self._asset(row)

    def get_asset(self, asset_id: int):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM assets WHERE id=?", (asset_id,)
            ).fetchone()
        return self._asset(row) if row is not None else None

    def list_assets(self) -> list[Asset]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM assets ORDER BY name, id"
            ).fetchall()
        return [self._asset(row) for row in rows]

    def save_warranty(self, warranty: Warranty) -> Warranty:
        timestamp = _now()
        with self._connect() as connection:
            cursor = connection.execute(
                """INSERT INTO warranties(
                       asset_id, provider, expires_on, deductible, evidence_id,
                       evidence_span, confidence, created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    warranty.asset_id,
                    warranty.provider,
                    warranty.expires_on,
                    warranty.deductible,
                    warranty.evidence_id,
                    warranty.evidence_span,
                    warranty.confidence,
                    timestamp,
                    timestamp,
                ),
            )
            row = connection.execute(
                "SELECT * FROM warranties WHERE id=?", (cursor.lastrowid,)
            ).fetchone()
        values = dict(row)
        values.pop("created_at")
        values.pop("updated_at")
        return Warranty(**values)

    def list_warranties(self, asset_id: int | None = None) -> list[Warranty]:
        query = "SELECT * FROM warranties"
        parameters = ()
        if asset_id is not None:
            query += " WHERE asset_id=?"
            parameters = (asset_id,)
        query += " ORDER BY expires_on, id"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        result = []
        for row in rows:
            values = dict(row)
            values.pop("created_at")
            values.pop("updated_at")
            result.append(Warranty(**values))
        return result

    def propose_correction(
        self, asset_id: int, *, field: str, proposed_value: str, evidence_id: int | None
    ) -> CorrectionProposal:
        allowed = {
            "name",
            "category",
            "purchase_price",
            "return_until",
            "replacement_reserve",
        }
        if field not in allowed:
            raise ValueError("field is not correctable")
        with self._connect() as connection:
            cursor = connection.execute(
                """INSERT INTO asset_correction_proposals(
                       asset_id, field, proposed_value, evidence_id, status, created_at
                   ) VALUES (?, ?, ?, ?, 'proposed', ?)""",
                (asset_id, field, proposed_value, evidence_id, _now()),
            )
        return CorrectionProposal(
            cursor.lastrowid, asset_id, field, proposed_value, evidence_id, "proposed"
        )

    def list_corrections(self, asset_id: int) -> list[CorrectionProposal]:
        with self._connect() as connection:
            rows = connection.execute(
                """SELECT id, asset_id, field, proposed_value, evidence_id, status
                   FROM asset_correction_proposals WHERE asset_id=? ORDER BY id""",
                (asset_id,),
            ).fetchall()
        return [CorrectionProposal(**dict(row)) for row in rows]

    def update_asset(self, asset: Asset) -> Asset:
        if asset.id is None:
            raise ValueError("asset id is required for update")
        timestamp = _now()
        with self._connect() as connection:
            cursor = connection.execute(
                """UPDATE assets SET
                       name=?, category=?, purchased_on=?, purchase_price=?,
                       return_until=?, maintenance_interval_days=?, replacement_reserve=?,
                       evidence_id=?, evidence_span=?, confidence=?, updated_at=?
                   WHERE id=?""",
                (
                    asset.name, asset.category, asset.purchased_on, asset.purchase_price,
                    asset.return_until, asset.maintenance_interval_days,
                    asset.replacement_reserve, asset.evidence_id, asset.evidence_span,
                    asset.confidence, timestamp, asset.id,
                ),
            )
            if cursor.rowcount == 0:
                raise ValueError("asset not found")
            row = connection.execute(
                "SELECT * FROM assets WHERE id=?", (asset.id,)
            ).fetchone()
        return self._asset(row)

    def delete_asset(self, asset_id: int) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM assets WHERE id=?", (asset_id,))

    def replace_warranties(
        self, asset_id: int, warranties: list[Warranty]
    ) -> list[Warranty]:
        timestamp = _now()
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM warranties WHERE asset_id=?", (asset_id,)
            )
            stored = []
            for warranty in warranties:
                cursor = connection.execute(
                    """INSERT INTO warranties(
                           asset_id, provider, expires_on, deductible, evidence_id,
                           evidence_span, confidence, created_at, updated_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        asset_id, warranty.provider, warranty.expires_on,
                        warranty.deductible, warranty.evidence_id,
                        warranty.evidence_span, warranty.confidence, timestamp, timestamp,
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM warranties WHERE id=?", (cursor.lastrowid,)
                ).fetchone()
                values = dict(row)
                values.pop("created_at")
                values.pop("updated_at")
                stored.append(Warranty(**values))
        return stored


def asset_events(
    asset: Asset, warranties: list[Warranty], *, as_of: date
) -> list[MemoryEvent]:
    events = []
    if asset.return_until and date.fromisoformat(asset.return_until) >= as_of:
        events.append(
            MemoryEvent(
                "return_deadline",
                f"Return window for {asset.name}",
                asset.return_until,
                asset.purchase_price,
                asset.evidence_id,
                asset.confidence,
            )
        )
    if asset.purchased_on and asset.maintenance_interval_days:
        due = date.fromisoformat(asset.purchased_on) + timedelta(
            days=asset.maintenance_interval_days
        )
        events.append(
            MemoryEvent(
                "maintenance_due",
                f"Maintenance for {asset.name}",
                due.isoformat(),
                None,
                asset.evidence_id,
                asset.confidence,
            )
        )
    if asset.replacement_reserve is not None:
        events.append(
            MemoryEvent(
                "replacement_reserve",
                f"Replacement reserve for {asset.name}",
                None,
                asset.replacement_reserve,
                asset.evidence_id,
                asset.confidence,
            )
        )
    for warranty in warranties:
        events.append(
            MemoryEvent(
                "warranty_expiration",
                f"{warranty.provider} warranty for {asset.name}",
                warranty.expires_on,
                warranty.deductible,
                warranty.evidence_id,
                warranty.confidence,
            )
        )
    return events
