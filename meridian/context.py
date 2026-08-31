"""Opt-in contextual signals and explicitly bounded scenario assumptions."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone

from meridian.db import run_migrations
from meridian.repository import FinancialRepository


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ContextSignal:
    id: int | None
    source_kind: str
    source_id: str
    kind: str
    occurred_on: str
    range_min: float | None
    range_max: float | None
    confidence: float
    confirmed: bool
    revoked_at: str | None = None


@dataclass(frozen=True)
class Assumption:
    kind: str
    source_ids: tuple[str, ...]
    confidence: float
    range_min: float | None
    range_max: float | None
    confirmation_state: str
    explanation: str


class ContextRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path
        run_migrations(db_path)

    def _connect(self):
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _from_row(row) -> ContextSignal:
        values = dict(row)
        values.pop("created_at", None)
        values.pop("updated_at", None)
        values["confirmed"] = bool(values["confirmed"])
        return ContextSignal(**values)

    def save(self, signal: ContextSignal) -> ContextSignal:
        if not 0 <= signal.confidence <= 1:
            raise ValueError("confidence must be between zero and one")
        if signal.range_min is not None and signal.range_max is not None:
            if signal.range_min > signal.range_max:
                raise ValueError("range_min cannot exceed range_max")
        timestamp = _now()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO context_signals(
                       source_kind, source_id, kind, occurred_on, range_min, range_max,
                       confidence, confirmed, revoked_at, created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?)
                   ON CONFLICT(source_kind, source_id, kind) DO UPDATE SET
                       occurred_on=excluded.occurred_on, range_min=excluded.range_min,
                       range_max=excluded.range_max, confidence=excluded.confidence,
                       confirmed=excluded.confirmed, revoked_at=NULL,
                       updated_at=excluded.updated_at""",
                (
                    signal.source_kind,
                    signal.source_id,
                    signal.kind,
                    signal.occurred_on,
                    signal.range_min,
                    signal.range_max,
                    signal.confidence,
                    int(signal.confirmed),
                    timestamp,
                    timestamp,
                ),
            )
            row = connection.execute(
                """SELECT * FROM context_signals
                   WHERE source_kind=? AND source_id=? AND kind=?""",
                (signal.source_kind, signal.source_id, signal.kind),
            ).fetchone()
        return self._from_row(row)

    def get(self, signal_id: int):
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM context_signals WHERE id=? AND revoked_at IS NULL",
                (signal_id,),
            ).fetchone()
        return self._from_row(row) if row is not None else None

    def revoke_source(self, source_kind: str, source_id: str) -> int:
        timestamp = _now()
        with self._connect() as connection:
            cursor = connection.execute(
                """UPDATE context_signals SET revoked_at=?, updated_at=?
                   WHERE source_kind=? AND source_id=? AND revoked_at IS NULL""",
                (timestamp, timestamp, source_kind, source_id),
            )
        return cursor.rowcount


def scenario_assumptions(
    signals: list[ContextSignal] | tuple[ContextSignal, ...], graph: FinancialRepository
) -> list[Assumption]:
    transactions, _ = graph.list_transactions(limit=200)
    assumptions = []
    for signal in signals:
        if signal.revoked_at is not None:
            continue
        source = (f"{signal.source_kind}:{signal.source_id}",)
        state = "confirmed" if signal.confirmed else "needs_confirmation"
        if signal.kind == "travel":
            assumptions.append(
                Assumption(
                    "travel_pressure",
                    source,
                    signal.confidence,
                    signal.range_min if signal.confirmed else None,
                    signal.range_max if signal.confirmed else None,
                    state,
                    "Dated travel may affect cash flow; no expense is inferred.",
                )
            )
        elif signal.kind == "pay_stub" and signal.range_min is not None:
            deposits = [
                item
                for item in transactions
                if item.amount > 0 and item.occurred_at[:10] == signal.occurred_on
            ]
            if deposits:
                difference_low = max(
                    0.0, signal.range_min - max(item.amount for item in deposits)
                )
                expected_high = (
                    signal.range_max
                    if signal.range_max is not None
                    else signal.range_min
                )
                difference_high = max(
                    0.0, expected_high - max(item.amount for item in deposits)
                )
                if difference_high > 0:
                    assumptions.append(
                        Assumption(
                            "payroll_mismatch",
                            source,
                            signal.confidence,
                            round(difference_low, 2),
                            round(difference_high, 2),
                            state,
                            "Pay-stub evidence differs from the observed deposit.",
                        )
                    )
    return assumptions
