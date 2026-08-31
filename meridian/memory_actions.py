"""Pipeline executors and verifiers for asset/contract management.

These are local planning-metadata writes: they never contact Crew and never
move money. They stay approval-gated through the shared action pipeline.
"""

from __future__ import annotations

from typing import Any, Callable, Dict

from meridian.assets import Asset, AssetRepository, Warranty
from meridian.contracts import Contract, ContractRepository, Obligation
from meridian.evidence import EvidenceRepository

MEMORY_ACTION_TYPES = (
    "create_asset",
    "update_asset",
    "delete_asset",
    "create_contract",
    "update_contract",
    "delete_contract",
)

_ASSET_FIELDS = (
    "name", "category", "purchased_on", "purchase_price", "return_until",
    "maintenance_interval_days", "replacement_reserve", "evidence_id",
    "evidence_span", "confidence",
)
_CONTRACT_FIELDS = (
    "kind", "name", "starts_on", "ends_on", "renews_on", "cancel_by",
    "escalation_percent", "deductible", "evidence_id", "evidence_span", "confidence",
)


def _asset_from_params(params: Dict[str, Any], asset_id: int | None = None) -> Asset:
    return Asset(
        id=asset_id,
        name=params["name"],
        category=params["category"],
        purchased_on=params.get("purchased_on"),
        purchase_price=params.get("purchase_price"),
        return_until=params.get("return_until"),
        maintenance_interval_days=params.get("maintenance_interval_days"),
        replacement_reserve=params.get("replacement_reserve"),
        evidence_id=params.get("evidence_id"),
        evidence_span=params.get("evidence_span") or "owner:managed",
        confidence=params.get("confidence", 1.0),
    )


def _contract_from_params(params: Dict[str, Any], contract_id: int | None = None) -> Contract:
    return Contract(
        id=contract_id,
        kind=params["kind"],
        name=params["name"],
        starts_on=params.get("starts_on"),
        ends_on=params.get("ends_on"),
        renews_on=params.get("renews_on"),
        cancel_by=params.get("cancel_by"),
        escalation_percent=params.get("escalation_percent"),
        deductible=params.get("deductible"),
        evidence_id=params.get("evidence_id"),
        evidence_span=params.get("evidence_span") or "owner:managed",
        confidence=params.get("confidence", 1.0),
    )


def _link_evidence(evidence: EvidenceRepository, target_kind: str, target_id: str, params: Dict[str, Any]) -> None:
    evidence_id = params.get("evidence_id")
    if evidence_id is None:
        return
    evidence.add_link(
        evidence_id=int(evidence_id),
        target_kind=target_kind,
        target_id=str(target_id),
        relation="supports",
        provenance=params.get("evidence_span") or "owner:managed",
    )


def asset_executors(db_path: str) -> Dict[str, tuple[Callable, Callable | None]]:
    repo = AssetRepository(db_path)
    evidence = EvidenceRepository(db_path)

    def create(params):
        record = repo.save_asset(_asset_from_params(params))
        _link_evidence(evidence, "asset", record.id, params)
        return {"success": True, "asset_id": record.id}

    def verify_create(params, result):
        record = repo.get_asset(result.get("asset_id"))
        return {"ok": record is not None and record.name == params["name"], "check": "asset-reread"}

    def update(params):
        record = repo.update_asset(_asset_from_params(params, asset_id=int(params["record_id"])))
        evidence.remove_links_for_target("asset", str(record.id))
        _link_evidence(evidence, "asset", record.id, params)
        return {"success": True, "asset_id": record.id}

    def verify_update(params, result):
        record = repo.get_asset(result.get("asset_id"))
        return {"ok": record is not None and record.name == params["name"], "check": "asset-reread"}

    def delete(params):
        asset_id = int(params["record_id"])
        evidence.remove_links_for_target("asset", str(asset_id))
        repo.delete_asset(asset_id)
        return {"success": True, "deleted": asset_id}

    def verify_delete(params, result):
        return {"ok": repo.get_asset(result.get("deleted")) is None, "check": "asset-gone"}

    return {
        "create_asset": (create, verify_create),
        "update_asset": (update, verify_update),
        "delete_asset": (delete, verify_delete),
    }


def contract_executors(db_path: str) -> Dict[str, tuple[Callable, Callable | None]]:
    repo = ContractRepository(db_path)
    evidence = EvidenceRepository(db_path)

    def create(params):
        record = repo.save_contract(_contract_from_params(params))
        _link_evidence(evidence, "contract", record.id, params)
        return {"success": True, "contract_id": record.id}

    def verify_create(params, result):
        record = repo.get_contract(result.get("contract_id"))
        return {"ok": record is not None and record.name == params["name"], "check": "contract-reread"}

    def update(params):
        record = repo.update_contract(_contract_from_params(params, contract_id=int(params["record_id"])))
        evidence.remove_links_for_target("contract", str(record.id))
        _link_evidence(evidence, "contract", record.id, params)
        return {"success": True, "contract_id": record.id}

    def verify_update(params, result):
        record = repo.get_contract(result.get("contract_id"))
        return {"ok": record is not None and record.name == params["name"], "check": "contract-reread"}

    def delete(params):
        contract_id = int(params["record_id"])
        evidence.remove_links_for_target("contract", str(contract_id))
        repo.delete_contract(contract_id)
        return {"success": True, "deleted": contract_id}

    def verify_delete(params, result):
        return {"ok": repo.get_contract(result.get("deleted")) is None, "check": "contract-gone"}

    return {
        "create_contract": (create, verify_create),
        "update_contract": (update, verify_update),
        "delete_contract": (delete, verify_delete),
    }
