"""Immutable, JSON-safe records returned by the Meridian repository."""

from dataclasses import asdict, dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class AccountRecord:
    id: int
    provider: str
    external_id: str
    name: str
    account_type: str
    balance: float
    currency: str
    available_balance: Optional[float]
    is_active: bool
    source_updated_at: Optional[str]
    synced_at: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TransactionRecord:
    id: int
    provider: str
    external_id: str
    account_id: int
    amount: float
    currency: str
    occurred_at: str
    posted_at: Optional[str]
    description: str
    merchant: Optional[str]
    status: str
    raw_description: Optional[str]
    source_updated_at: Optional[str]
    classification_category: Optional[str]
    classification_kind: Optional[str]
    classification_confidence: Optional[float]
    classification_rule_id: Optional[str]
    classification_evidence: Optional[str]
    classification_method: Optional[str]
    classification_provider: Optional[str]
    classification_model: Optional[str]
    classification_version: int
    synced_at: str
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
