from datetime import date, datetime, timezone
from typing import Any, Dict, List

from meridian.assets import Asset, AssetRepository, Warranty, asset_events
from meridian.contracts import Contract, ContractRepository, contract_events
from meridian.evidence import EvidenceRepository

WORKSPACES = ("today", "plan", "activity", "accounts")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _evidence_entries(
    db_path: str, evidence_id: int | None, span: str | None, confidence: float | None
) -> list[Dict[str, Any]]:
    if evidence_id is None:
        return []
    item = EvidenceRepository(db_path).get_item(evidence_id)
    if item is None:
        return []
    if item.expires_at is not None and item.expires_at <= _now_iso():
        return []
    return [{"id": item.id, "span": span or item.title or "record", "confidence": confidence}]


def _urgency(due_on: str | None, as_of: date) -> str | None:
    if due_on is None:
        return None
    try:
        due_date = date.fromisoformat(due_on)
    except ValueError:
        return None
    if due_date < as_of:
        return "overdue"
    if due_date <= as_of.replace(day=15):
        return "upcoming"
    return "future"


def _why_it_matters(event: Any) -> str:
    why = {
        "return_deadline": lambda: f"Return window closes; refund of ${event.amount:.2f} at risk",
        "maintenance_due": lambda: "Scheduled maintenance to preserve asset value and warranty",
        "replacement_reserve": lambda: f"${event.amount:.2f} reserve needed for future replacement",
        "warranty_expiration": lambda: f"Warranty expires; ${event.amount:.2f} deductible applies if claim needed",
        "obligation_due": lambda: f"${event.amount:.2f} payment due under contract",
        "cancellation_deadline": lambda: "Must cancel by this date to avoid auto-renewal charges",
        "renewal": lambda: "Contract renews; review terms and pricing before commitment",
        "escalation_review": lambda: f"{event.amount:.1f}% escalation clause triggers at renewal",
    }.get(event.kind)
    return why() if why else "Requires attention"


def _base_item(event: Any, db_path: str, as_of: date) -> Dict[str, Any]:
    return {
        "id": f"{event.title.lower().replace(' ', '-')}:{event.kind}",
        "kind": event.kind,
        "title": event.title,
        "due_on": event.due_on,
        "amount": event.amount,
        "confidence": event.confidence,
        "urgency": _urgency(event.due_on, as_of),
        "why_it_matters": _why_it_matters(event) if event.due_on else None,
        "evidence": _evidence_entries(db_path, event.evidence_id, None, event.confidence),
        "reference_transaction_id": None,
        "escalation_percent": None,
    }


def _compose_today(events: List[Any], db_path: str, as_of: date) -> List[Dict[str, Any]]:
    items = [_base_item(e, db_path, as_of) for e in events if e.due_on is not None]
    items.sort(key=lambda x: (
        0 if x["urgency"] == "overdue" else (1 if x["urgency"] == "upcoming" else 2),
        x["due_on"] or "9999-12-31",
    ))
    return items


def _compose_plan(events: List[Any], db_path: str) -> List[Dict[str, Any]]:
    items = []
    for event in events:
        item = _base_item(event, db_path, date.today())
        if event.kind == "replacement_reserve" and event.amount is not None:
            item["urgency"] = None
            items.append(item)
        elif event.kind in ("obligation_due", "escalation_review") and event.amount is not None:
            item["urgency"] = None
            items.append(item)
    return items


def _compose_activity(events: List[Any], db_path: str, as_of: date) -> List[Dict[str, Any]]:
    return [_base_item(e, db_path, as_of) for e in events]


def _compose_accounts(
    assets: List[Asset], contracts: List[Contract],
    warranties: List[Warranty], obligations: List[Any], db_path: str,
) -> List[Dict[str, Any]]:
    items = []
    for asset in assets:
        items.append({
            "id": f"asset:{asset.id}",
            "kind": "asset",
            "title": asset.name,
            "due_on": None,
            "amount": asset.purchase_price,
            "confidence": asset.confidence,
            "urgency": None,
            "why_it_matters": None,
            "evidence": _evidence_entries(db_path, asset.evidence_id, asset.evidence_span, asset.confidence),
            "reference_transaction_id": None,
            "escalation_percent": None,
            "category": asset.category,
            "purchased_on": asset.purchased_on,
            "return_until": asset.return_until,
            "maintenance_interval_days": asset.maintenance_interval_days,
            "replacement_reserve": asset.replacement_reserve,
            "warranties": [
                {
                    "id": w.id, "provider": w.provider, "expires_on": w.expires_on,
                    "deductible": w.deductible, "confidence": w.confidence,
                    "evidence": _evidence_entries(db_path, w.evidence_id, w.evidence_span, w.confidence),
                }
                for w in warranties if w.asset_id == asset.id
            ],
        })
    for contract in contracts:
        items.append({
            "id": f"contract:{contract.id}",
            "kind": "contract",
            "title": contract.name,
            "due_on": None,
            "amount": None,
            "confidence": contract.confidence,
            "urgency": None,
            "why_it_matters": None,
            "evidence": _evidence_entries(db_path, contract.evidence_id, contract.evidence_span, contract.confidence),
            "reference_transaction_id": None,
            "escalation_percent": contract.escalation_percent,
            "contract_kind": contract.kind,
            "starts_on": contract.starts_on,
            "ends_on": contract.ends_on,
            "renews_on": contract.renews_on,
            "cancel_by": contract.cancel_by,
            "deductible": contract.deductible,
            "obligations": [
                {
                    "id": o.id, "name": o.name, "amount": o.amount, "due_on": o.due_on,
                    "recurrence": o.recurrence, "confidence": o.confidence,
                    "evidence": _evidence_entries(db_path, o.evidence_id, o.evidence_span, o.confidence),
                }
                for o in obligations if o.contract_id == contract.id
            ],
        })
    return items


def build_memory(db_path: str, workspace: str, *, as_of: date | None = None) -> Dict[str, Any]:
    if workspace not in WORKSPACES:
        raise ValueError(f"unknown workspace: {workspace}")
    as_of = as_of or date.today()

    asset_repo = AssetRepository(db_path)
    contract_repo = ContractRepository(db_path)
    assets = asset_repo.list_assets()
    warranties = asset_repo.list_warranties()
    contracts = contract_repo.list_contracts()
    obligations = contract_repo.list_obligations()

    all_asset_events = []
    for asset in assets:
        asset_warranties = [w for w in warranties if w.asset_id == asset.id]
        all_asset_events.extend(asset_events(asset, asset_warranties, as_of=as_of))
    all_contract_events = []
    for contract in contracts:
        contract_obligations = [o for o in obligations if o.contract_id == contract.id]
        all_contract_events.extend(contract_events(contract, contract_obligations, as_of=as_of))

    events = all_asset_events + all_contract_events
    composers = {
        "today": lambda: _compose_today(events, db_path, as_of),
        "plan": lambda: _compose_plan(events, db_path),
        "activity": lambda: _compose_activity(events, db_path, as_of),
        "accounts": lambda: _compose_accounts(
            assets, contracts, warranties, obligations, db_path
        ),
    }
    return {"workspace": workspace, "items": composers[workspace]()}
