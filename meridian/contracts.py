"""Evidence-backed contract facts without professional determinations."""

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone

from meridian.db import run_migrations


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Contract:
    id: int | None
    kind: str
    name: str
    starts_on: str | None
    ends_on: str | None
    renews_on: str | None
    cancel_by: str | None
    escalation_percent: float | None
    deductible: float | None
    evidence_id: int | None
    evidence_span: str
    confidence: float


@dataclass(frozen=True)
class Obligation:
    id: int | None
    contract_id: int
    name: str
    amount: float
    due_on: str | None
    recurrence: str | None
    commitment_id: int | None
    evidence_id: int | None
    evidence_span: str
    confidence: float


@dataclass(frozen=True)
class ContractEvent:
    kind: str
    title: str
    due_on: str | None
    amount: float | None
    evidence_id: int | None
    confidence: float


@dataclass(frozen=True)
class AdvisoryBoundary:
    quoted_facts: dict[str, float]
    deadlines: tuple[str, ...]
    determinations: tuple[str, ...]
    disclaimer: str


class ContractRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path
        run_migrations(db_path)

    def _connect(self):
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _record(row, kind):
        values = dict(row)
        values.pop("created_at", None)
        values.pop("updated_at", None)
        return kind(**values)

    def save_contract(self, contract: Contract) -> Contract:
        timestamp = _now()
        with self._connect() as connection:
            cursor = connection.execute(
                """INSERT INTO contracts(
                       kind, name, starts_on, ends_on, renews_on, cancel_by,
                       escalation_percent, deductible, evidence_id, evidence_span,
                       confidence, created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    contract.kind,
                    contract.name,
                    contract.starts_on,
                    contract.ends_on,
                    contract.renews_on,
                    contract.cancel_by,
                    contract.escalation_percent,
                    contract.deductible,
                    contract.evidence_id,
                    contract.evidence_span,
                    contract.confidence,
                    timestamp,
                    timestamp,
                ),
            )
            row = connection.execute(
                "SELECT * FROM contracts WHERE id=?", (cursor.lastrowid,)
            ).fetchone()
        return self._record(row, Contract)

    def list_contracts(self) -> list[Contract]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM contracts ORDER BY name, id"
            ).fetchall()
        return [self._record(row, Contract) for row in rows]

    def save_obligation(self, obligation: Obligation) -> Obligation:
        timestamp = _now()
        with self._connect() as connection:
            cursor = connection.execute(
                """INSERT INTO obligations(
                       contract_id, name, amount, due_on, recurrence, commitment_id,
                       evidence_id, evidence_span, confidence, created_at, updated_at
                   ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    obligation.contract_id,
                    obligation.name,
                    obligation.amount,
                    obligation.due_on,
                    obligation.recurrence,
                    obligation.commitment_id,
                    obligation.evidence_id,
                    obligation.evidence_span,
                    obligation.confidence,
                    timestamp,
                    timestamp,
                ),
            )
            row = connection.execute(
                "SELECT * FROM obligations WHERE id=?", (cursor.lastrowid,)
            ).fetchone()
        return self._record(row, Obligation)

    def list_obligations(self, contract_id: int | None = None) -> list[Obligation]:
        query = "SELECT * FROM obligations"
        parameters = ()
        if contract_id is not None:
            query += " WHERE contract_id=?"
            parameters = (contract_id,)
        query += " ORDER BY due_on, id"
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [self._record(row, Obligation) for row in rows]

    def get_contract(self, contract_id: int) -> Contract | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM contracts WHERE id=?", (contract_id,)
            ).fetchone()
        return self._record(row, Contract) if row is not None else None

    def update_contract(self, contract: Contract) -> Contract:
        if contract.id is None:
            raise ValueError("contract id is required for update")
        timestamp = _now()
        with self._connect() as connection:
            cursor = connection.execute(
                """UPDATE contracts SET
                       kind=?, name=?, starts_on=?, ends_on=?, renews_on=?, cancel_by=?,
                       escalation_percent=?, deductible=?, evidence_id=?, evidence_span=?,
                       confidence=?, updated_at=?
                   WHERE id=?""",
                (
                    contract.kind, contract.name, contract.starts_on, contract.ends_on,
                    contract.renews_on, contract.cancel_by, contract.escalation_percent,
                    contract.deductible, contract.evidence_id, contract.evidence_span,
                    contract.confidence, timestamp, contract.id,
                ),
            )
            if cursor.rowcount == 0:
                raise ValueError("contract not found")
            row = connection.execute(
                "SELECT * FROM contracts WHERE id=?", (contract.id,)
            ).fetchone()
        return self._record(row, Contract)

    def delete_contract(self, contract_id: int) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM contracts WHERE id=?", (contract_id,)
            )

    def replace_obligations(
        self, contract_id: int, obligations: list[Obligation]
    ) -> list[Obligation]:
        timestamp = _now()
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM obligations WHERE contract_id=?", (contract_id,)
            )
            stored = []
            for obligation in obligations:
                cursor = connection.execute(
                    """INSERT INTO obligations(
                           contract_id, name, amount, due_on, recurrence, commitment_id,
                           evidence_id, evidence_span, confidence, created_at, updated_at
                       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        contract_id, obligation.name, obligation.amount, obligation.due_on,
                        obligation.recurrence, obligation.commitment_id,
                        obligation.evidence_id, obligation.evidence_span,
                        obligation.confidence, timestamp, timestamp,
                    ),
                )
                row = connection.execute(
                    "SELECT * FROM obligations WHERE id=?", (cursor.lastrowid,)
                ).fetchone()
                values = dict(row)
                values.pop("created_at")
                values.pop("updated_at")
                stored.append(Obligation(**values))
        return stored


def contract_events(
    contract: Contract, obligations: list[Obligation], *, as_of: date
) -> list[ContractEvent]:
    del as_of
    events = []
    for obligation in obligations:
        events.append(
            ContractEvent(
                "obligation_due",
                obligation.name,
                obligation.due_on,
                obligation.amount,
                obligation.evidence_id,
                obligation.confidence,
            )
        )
    for kind, title, due_on in (
        ("cancellation_deadline", f"Cancel {contract.name}", contract.cancel_by),
        ("renewal", f"Renewal for {contract.name}", contract.renews_on),
    ):
        if due_on:
            events.append(
                ContractEvent(
                    kind, title, due_on, None, contract.evidence_id, contract.confidence
                )
            )
    if contract.escalation_percent is not None:
        events.append(
            ContractEvent(
                "escalation_review",
                f"{contract.name} escalation clause",
                contract.renews_on or contract.ends_on,
                contract.escalation_percent,
                contract.evidence_id,
                contract.confidence,
            )
        )
    return events


def advisory_boundary(contract: Contract) -> AdvisoryBoundary:
    facts = {}
    if contract.deductible is not None:
        facts["deductible"] = contract.deductible
    if contract.escalation_percent is not None:
        facts["escalation_percent"] = contract.escalation_percent
    deadlines = tuple(
        value
        for value in (contract.cancel_by, contract.ends_on, contract.renews_on)
        if value
    )
    return AdvisoryBoundary(
        facts,
        deadlines,
        (),
        "Quoted financial facts only; not medical, legal, coverage, or tax advice.",
    )
