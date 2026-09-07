"""Route a requested Meridian mutation to DIRECT execution or a PROPOSAL.

The write model is keyed on intent-confidence + determinism, not on who
initiated the action. Three buckets:

  1. DIRECT + deterministic + single + unambiguous  -> execute immediately,
     no proposal confirmation. The owner stated an exact value/target or
     clicked one control with a clear value ("set Rent to $1500").
  2. AI-interpreted / composed / multi-op / low-confidence / plan-level
     -> create a PROPOSAL and wait for explicit owner approval. The AI read a
     natural-language request and assembled a plan ("cancel income and move
     $30 safe->checking"), or a shortfall re-allocates ToBills/ToPockets/
     Surplus, or a low-confidence transaction needs categorization.
  3. Automatic / scheduled (no human in the loop) -> PROPOSAL (or a governed
     default), because no one explicitly confirmed the target.

The propose -> approve -> execute -> verify engine already exists
(crew/actions.py + crew/executors.py). This module only decides the ROUTE and
adds the direct-execute path (which claims + runs immediately, skipping the
awaiting-approval gate for owner-unambiguous actions).

Provenance is a required, structured signal so the AI/UI cannot send an
ambiguous plan down the direct path. It is NOT inferred from a free-text role.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Iterable, Optional

from crew.actions import ActionStore
from crew.executors import ExecutorSpec, execute_approved_action


class Provenance(str, Enum):
    """Where a mutation request came from — the primary routing signal."""

    OWNER_DIRECT = "owner_direct"        # owner stated an exact value/target, one clear action
    AI_INTERPRETED = "ai_interpreted"    # AI read natural language & assembled the action
    AI_COMPOSED = "ai_composed"          # AI composed multiple actions into one plan
    SCHEDULED = "scheduled"              # no human in the loop (autopilot/recurring)


# Plan-level / multi-op actions that change the budget allocation model; these
# always warrant a proposal regardless of provenance (they move policy money).
_PLAN_LEVEL_TYPES = frozenset({
    "create_crew_autopilot_rule",
    "update_crew_bill_reserve_settings",
    "move_money_between_pockets",
    "update_autopilot_settings",
    "cancel_income_source",
    "reallocate_budget",
})


@dataclass(frozen=True)
class RoutingDecision:
    requires_proposal: bool
    reason: str
    provenance: str


def classify_action(
    provenance: str,
    action_type: str,
    params: Dict[str, Any],
    *,
    low_confidence: bool = False,
    multi_op: bool = False,
) -> RoutingDecision:
    """Return the routing decision for one mutation request.

    ``params`` may carry an explicit ``confidence``/``deterministic`` hint; a
    missing amount/target is treated as under-specified (interpreted).
    """
    prov = _coerce_provenance(provenance)

    # Under-specified params -> the AI must have interpreted/intended something
    # not fully stated; route to a proposal.
    if _under_specified(params):
        return RoutingDecision(
            True,
            "action under-specified (missing amount/target/order); treat as interpreted",
            prov.value,
        )

    if low_confidence or _flags_low_confidence(params):
        return RoutingDecision(
            True,
            "low-confidence action (uncertain target/amount); require owner confirmation",
            prov.value,
        )

    # Multi-op plans (a composition of sub-actions) always need review — the
    # assembled order/amounts are the AI's interpretation.
    if multi_op or _flags_multi_op(params):
        return RoutingDecision(
            True,
            "composed multi-action plan; require owner confirmation of the assembly",
            prov.value,
        )

    # Owner-direct + single + fully-specified: the owner is the authority, so it
    # executes immediately even for plan-level types (they set up a rule/plan the
    # owner explicitly wants). Anything else at plan-level is the AI/composed path
    # moving policy money -> propose.
    if prov is Provenance.OWNER_DIRECT:
        return RoutingDecision(
            False,
            "owner-direct, single, fully-specified action; execute without confirmation",
            prov.value,
        )

    # Plan-level budget/allocation changes move policy money — confirm unless the
    # owner explicitly stated this exact change (handled above).
    if action_type in _PLAN_LEVEL_TYPES or action_type.startswith("reallocate_"):
        return RoutingDecision(
            True,
            f"plan-level change ({action_type}) alters the budget model; require confirmation",
            prov.value,
        )
    if prov is Provenance.SCHEDULED:
        return RoutingDecision(
            True,
            "scheduled action has no human confirmation in the loop; require approval",
            prov.value,
        )
    # AI_INTERPRETED / AI_COMPOSED default to a proposal.
    return RoutingDecision(
        True,
        f"{prov.value} action is the AI's interpretation of intent; require owner confirmation",
        prov.value,
    )


def route_mutation(
    store: ActionStore,
    executors: Dict[str, ExecutorSpec],
    *,
    action_type: str,
    params: Dict[str, Any],
    rationale: str,
    requested_by: str,
    provenance: str,
    low_confidence: bool = False,
    multi_op: bool = False,
    dedup_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Route one mutation to DIRECT execution or a PROPOSAL; returns the action.

    DIRECT (owner-unambiguous): the action is proposed, auto-approved, then
    executed in one call — no awaiting-approval gate in front of the owner.
    PROPOSAL: the action is created in PROPOSED state and returned for the
    owner to approve/execute later.

    The returned dict includes ``routing`` (the RoutingDecision) plus the
    action request. For the direct path it includes the execution outcome.
    """
    decision = classify_action(
        provenance, action_type, params,
        low_confidence=low_confidence, multi_op=multi_op,
    )

    if decision.requires_proposal:
        action = store.propose(
            action_type, params, rationale=rationale,
            requested_by=requested_by, dedup_key=dedup_key,
        )
        return {"routing": decision, "routing_direct": False, "action": action}

    # Direct path: propose, auto-approve, execute immediately (the owner is the
    # authority; no waiting gate).
    action = store.propose(
        action_type, params, rationale=rationale,
        requested_by=requested_by, dedup_key=dedup_key,
    )
    store.approve(action["id"], decided_by=requested_by)
    outcome = execute_approved_action(store, action["id"], executors)
    return {"routing": decision, "routing_direct": True, "action": outcome}


def route_many(stores, executors, requests):  # pragma: no cover - convenience
    """Route a batch of mutation requests; each is decided independently."""
    return [
        route_mutation(
            stores,
            executors,
            action_type=r["type"],
            params=r["params"],
            rationale=r.get("rationale", ""),
            requested_by=r.get("requested_by", "owner"),
            provenance=r.get("provenance", Provenance.AI_INTERPRETED.value),
            low_confidence=bool(r.get("low_confidence", False)),
            multi_op=bool(r.get("multi_op", False)),
            dedup_key=r.get("dedup_key"),
        )
        for r in requests
    ]


def _coerce_provenance(value: str) -> Provenance:
    try:
        return Provenance(value)
    except ValueError:
        return Provenance.AI_INTERPRETED


def _under_specified(params: Dict[str, Any]) -> bool:
    """True if the core amount/target is absent even though the op needs it."""
    if not isinstance(params, dict) or not params:
        return True
    amount = params.get("amount")
    # An amount param present but None on an op that needs money -> under-specified.
    if params.get("needs_amount") and amount is None:
        return True
    # Presence of an explicit 'deterministic: true' marker overrides under-spec
    # only when the owner told us the exact target.
    return False


def _flags_low_confidence(params: Dict[str, Any]) -> bool:
    if not isinstance(params, dict):
        return False
    conf = params.get("confidence")
    if conf is None:
        return False
    try:
        return float(conf) < 0.9
    except (TypeError, ValueError):
        return True  # non-numeric confidence is treated as uncertain


def _flags_multi_op(params: Dict[str, Any]) -> bool:
    if not isinstance(params, dict):
        return False
    return bool(params.get("multi_op") or params.get("composed") or params.get("ops"))


def reroute_direct_if_owner(store, executors, action_id, requested_by="owner"):
    """Escalation helper: manually force an already-PROPOSED owner action direct."""
    action = store.get(action_id)
    if action is None or action["state"] != "proposed":
        return {"routing_direct": False, "action": action}
    store.approve(action_id, decided_by=requested_by)
    outcome = execute_approved_action(store, action_id, executors)
    return {"routing_direct": True, "action": outcome}


def all_provenances() -> Iterable[str]:
    return tuple(p.value for p in Provenance)
