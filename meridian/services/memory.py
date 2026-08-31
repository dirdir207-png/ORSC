"""Composed memory across Today, Plan, Activity, and Accounts workspaces."""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Union

from meridian.assets import Asset, AssetRepository, Warranty, asset_events
from meridian.contracts import Contract, ContractRepository, contract_events


def _compose_today(events: List[Union[Any, Any]]) -> List[Dict[str, Any]]:
    """Compose Today workspace items with urgency ordering and why_it_matters."""
    today_items = []

    for event in events:
        due_on = event.due_on
        if due_on is None:
            continue

        try:
            due_date = date.fromisoformat(due_on)
        except ValueError:
            continue

        if due_date < date.today():
            urgency = "overdue"
        elif due_date <= date.today().replace(day=15):
            urgency = "upcoming"
        else:
            urgency = "future"

        # Build why_it_matters
        if event.kind == "return_deadline":
            why = f"Return window closes; refund of ${event.amount:.2f} at risk"
        elif event.kind == "maintenance_due":
            why = "Scheduled maintenance to preserve asset value and warranty"
        elif event.kind == "replacement_reserve":
            why = f"${event.amount:.2f} reserve needed for future replacement"
        elif event.kind == "warranty_expiration":
            why = f"Warranty expires; ${event.amount:.2f} deductible applies if claim needed"
        elif event.kind == "obligation_due":
            why = f"${event.amount:.2f} payment due under contract"
        elif event.kind == "cancellation_deadline":
            why = "Must cancel by this date to avoid auto-renewal charges"
        elif event.kind == "renewal":
            why = "Contract renews; review terms and pricing before commitment"
        elif event.kind == "escalation_review":
            why = f"{event.amount:.1f}% escalation clause triggers at renewal"
        else:
            why = "Requires attention"

        today_items.append({
            "kind": event.kind,
            "title": event.title,
            "due_on": due_on,
            "amount": event.amount,
            "evidence_id": event.evidence_id,
            "evidence_url": event.evidence_id,
            "confidence": event.confidence,
            "urgency": urgency,
            "why_it_matters": why,
        })

    # Sort: overdue first, then upcoming, then by date
    today_items.sort(key=lambda x: (
        0 if x["urgency"] == "overdue" else (1 if x["urgency"] == "upcoming" else 2),
        x["due_on"] or "9999-12-31"
    ))

    return today_items


def _compose_plan(asset_events: List[Any], contract_events: List[Any]) -> List[Dict[str, Any]]:
    """Compose Plan workspace items with reserve/obligation amounts."""
    plan_items = []

    for event in asset_events:
        if event.kind == "replacement_reserve" and event.amount is not None:
            plan_items.append({
                "kind": "replacement_reserve",
                "title": event.title,
                "amount": event.amount,
                "evidence_id": event.evidence_id,
                "confidence": event.confidence,
            })

    for event in contract_events:
        if event.kind == "obligation_due" and event.amount is not None:
            plan_items.append({
                "kind": "obligation",
                "title": event.title,
                "amount": event.amount,
                "evidence_id": event.evidence_id,
                "confidence": event.confidence,
            })
        elif event.kind == "escalation_review" and event.amount is not None:
            plan_items.append({
                "kind": "escalation",
                "title": event.title,
                "amount": event.amount,  # escalation_percent
                "evidence_id": event.evidence_id,
                "confidence": event.confidence,
            })

    return plan_items


def _compose_accounts(assets: List[Asset], contracts: List[Contract], warranties: List[Warranty]) -> Dict[str, List[Dict[str, Any]]]:
    """Compose Accounts workspace with assets and contracts."""
    account_assets = []
    for asset in assets:
        account_assets.append({
            "id": asset.id,
            "name": asset.name,
            "category": asset.category,
            "purchased_on": asset.purchased_on,
            "purchase_price": asset.purchase_price,
            "return_until": asset.return_until,
            "maintenance_interval_days": asset.maintenance_interval_days,
            "replacement_reserve": asset.replacement_reserve,
            "evidence_id": asset.evidence_id,
            "evidence_span": asset.evidence_span,
            "confidence": asset.confidence,
        })

    account_contracts = []
    for contract in contracts:
        account_contracts.append({
            "id": contract.id,
            "kind": contract.kind,
            "name": contract.name,
            "starts_on": contract.starts_on,
            "ends_on": contract.ends_on,
            "renews_on": contract.renews_on,
            "cancel_by": contract.cancel_by,
            "escalation_percent": contract.escalation_percent,
            "deductible": contract.deductible,
            "evidence_id": contract.evidence_id,
            "evidence_span": contract.evidence_span,
            "confidence": contract.confidence,
        })

    return {
        "assets": account_assets,
        "contracts": account_contracts,
    }


def build_memory(db_path: str, *, as_of: date | None = None) -> Dict[str, Any]:
    """Build composed memory for all four workspaces."""
    as_of = as_of or date.today()

    asset_repo = AssetRepository(db_path)
    contract_repo = ContractRepository(db_path)

    assets = asset_repo.list_assets()
    warranties = asset_repo.list_warranties()
    contracts = contract_repo.list_contracts()
    obligations = contract_repo.list_obligations()

    # Gather all events
    all_asset_events = []
    for asset in assets:
        asset_warranties = [w for w in warranties if w.asset_id == asset.id]
        all_asset_events.extend(asset_events(asset, asset_warranties, as_of=as_of))

    all_contract_events = []
    for contract in contracts:
        contract_obligations = [o for o in obligations if o.contract_id == contract.id]
        all_contract_events.extend(contract_events(contract, contract_obligations, as_of=as_of))

    # Compose for each workspace
    return {
        "today": _compose_today(all_asset_events + all_contract_events),
        "plan": _compose_plan(all_asset_events, all_contract_events),
        "activity": [],  # Placeholder - no activity events yet
        "accounts": _compose_accounts(assets, contracts, warranties),
    }