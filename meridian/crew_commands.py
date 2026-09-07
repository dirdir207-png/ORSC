"""Validated, provider-specific command payloads for Meridian proposals."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from crew.operations import (
    CREATE_SUBACCOUNT_MUTATION as BROKER_CREATE_SUBACCOUNT_MUTATION,
)
from crew.operations import (
    DELETE_SUBACCOUNT_MUTATION as BROKER_DELETE_SUBACCOUNT_MUTATION,
)
from crew.operations import (
    SET_SPEND_POCKET_MUTATION as BROKER_SET_SPEND_POCKET_MUTATION,
)
from crew.operations import (
    UPDATE_VIRTUAL_CARD_MUTATION as BROKER_UPDATE_VIRTUAL_CARD_MUTATION,
)


@dataclass(frozen=True)
class CommandSpec:
    operation_name: str
    query: str
    readback_key: str
    is_mutation: bool = True


CREATE_SUBACCOUNT_MUTATION = """mutation CreateSubaccount($input: CreateSubaccountInput!) {
  createSubaccount(input: $input) {
    result { id name balance goal status subaccountType }
  }
}"""

CREATE_BILL_MUTATION = """mutation CreateBill($input: CreateBillInput!) {
  createBill(input: $input) {
    result { id name status amount reservedAmount }
  }
}"""

DELETE_SUBACCOUNT_MUTATION = """mutation DeleteSubaccount($id: ID!) {
  deleteSubaccount(input: { subaccountId: $id }) {
    result { id name status }
  }
}"""

DELETE_BILL_MUTATION = """mutation DeleteBill($id: ID!) {
  deleteBill(input: { billId: $id }) {
    result { id status name }
  }
}"""

CREATE_ROUND_UP_MUTATION = """mutation CreateRoundUpRule($input: CreateRuleInput!) {
  createRule(input: $input) {
    result { id name isPaused }
  }
}"""

EDIT_ROUND_UP_MUTATION = """mutation EditRoundUpRule($input: UpdateRuleInput!) {
  updateRule(input: $input) {
    result { id name isPaused }
  }
}"""

DELETE_RULE_MUTATION = """mutation DeleteRule($input: DeleteRuleInput!) {
  deleteRule(input: $input) {
    result { id }
  }
}"""

SET_SPEND_POCKET_MUTATION = """mutation SetActiveSpendPocketScottie($input: SetSpendSubaccountInput!) {
  setSpendSubaccount(input: $input) {
    result { id userSpendConfig { id selectedSpendSubaccount { id clearedBalance } } }
  }
}"""

UPDATE_VIRTUAL_CARD_MUTATION = """mutation UpdateVirtualDebitCard($input: UpdateVirtualDebitCardInput!) {
  updateVirtualDebitCard(input: $input) {
    result { id subaccount { id displayName } }
  }
}"""

CREATE_POCKET_REASSIGNMENT_MUTATION = """mutation CreatePocketReassignmentRule($input: CreateReassignmentRuleInput!) {
  createReassignmentRule(input: $input) {
    result { id match minAmount maxAmount assignmentSubaccount { id displayName } }
  }
}"""

DELETE_POCKET_REASSIGNMENT_MUTATION = """mutation DeletePocketReassignmentRule($input: DeleteReassignmentRuleInput!) {
  deleteReassignmentRule(input: $input) {
    result { id match }
  }
}"""


_SPECS = {
    "create_pocket": CommandSpec(
        "CreateSubaccount", BROKER_CREATE_SUBACCOUNT_MUTATION, "createSubaccount"
    ),
    "delete_pocket": CommandSpec(
        "DeleteSubaccount", BROKER_DELETE_SUBACCOUNT_MUTATION, "deleteSubaccount"
    ),
    "create_bill": CommandSpec("CreateBill", CREATE_BILL_MUTATION, "createBill"),
    "delete_bill": CommandSpec("DeleteBill", DELETE_BILL_MUTATION, "deleteBill"),
    "create_autopilot_rule": CommandSpec(
        "CreateRoundUpRule", CREATE_ROUND_UP_MUTATION, "createRule"
    ),
    "edit_autopilot_rule": CommandSpec(
        "EditRoundUpRule", EDIT_ROUND_UP_MUTATION, "updateRule"
    ),
    "delete_autopilot_rule": CommandSpec(
        "DeleteRule", DELETE_RULE_MUTATION, "deleteRule"
    ),
    "create_pocket_reassignment_rule": CommandSpec(
        "CreatePocketReassignmentRule",
        CREATE_POCKET_REASSIGNMENT_MUTATION,
        "createReassignmentRule",
    ),
    "delete_pocket_reassignment_rule": CommandSpec(
        "DeletePocketReassignmentRule",
        DELETE_POCKET_REASSIGNMENT_MUTATION,
        "deleteReassignmentRule",
    ),
    "set_spend_pocket": CommandSpec(
        "SetActiveSpendPocketScottie", BROKER_SET_SPEND_POCKET_MUTATION, "setSpendSubaccount"
    ),
    "update_virtual_card": CommandSpec(
        "UpdateVirtualDebitCard", BROKER_UPDATE_VIRTUAL_CARD_MUTATION, "updateVirtualDebitCard"
    ),
}


def command_spec(kind: str) -> CommandSpec:
    try:
        return _SPECS[kind]
    except KeyError as exc:
        raise ValueError(f"unsupported Crew command: {kind}") from exc


def _cents(value, field: str) -> int:
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a valid amount") from exc
    if amount < 0:
        raise ValueError(f"{field} must be non-negative")
    return int(amount * 100)


def build_command_payload(kind: str, params: dict[str, object]):
    spec = command_spec(kind)
    if kind == "create_pocket":
        account_id = str(params.get("account_id") or "").strip()
        name = str(params.get("name") or "").strip()
        if not account_id or not name:
            raise ValueError("account_id and name are required")
        target_amount = _cents(params.get("target_amount"), "target_amount")
        initial_amount = _cents(params.get("initial_amount"), "initial_amount")
        variables = {
            "input": {
                "type": "SAVINGS",
                "piggyBanked": False,
                "accountId": account_id,
                "name": name,
                "targetAmount": target_amount,
                "initialTransferAmount": initial_amount,
                "note": str(params.get("note") or ""),
            }
        }
    elif kind == "delete_pocket":
        subaccount_id = str(params.get("subaccount_id") or "").strip()
        if not subaccount_id:
            raise ValueError("subaccount_id is required")
        variables = {"id": subaccount_id}
    elif kind == "create_bill":
        account_id = str(params.get("account_id") or "").strip()
        name = str(params.get("name") or "").strip()
        if not account_id or not name:
            raise ValueError("account_id and name are required")
        try:
            interval = int(params.get("frequency_interval", 1))
        except (TypeError, ValueError) as exc:
            raise ValueError("frequency_interval must be an integer") from exc
        if interval < 1:
            raise ValueError("frequency_interval must be positive")
        frequency = str(params.get("frequency") or "").strip().upper()
        anchor_date = str(params.get("anchor_date") or "").strip()
        if not frequency or not anchor_date:
            raise ValueError("frequency and anchor_date are required")
        variables = {
            "input": {
                "accountId": account_id,
                "amount": _cents(params.get("amount"), "amount"),
                "anchorDate": anchor_date,
                "frequency": frequency,
                "frequencyInterval": interval,
                "autoAdjustAmount": bool(params.get("auto_adjust_amount", False)),
                "paused": False,
                "name": name,
            }
        }
    elif kind == "delete_bill":
        bill_id = str(params.get("bill_id") or "").strip()
        if not bill_id:
            raise ValueError("bill_id is required")
        variables = {"id": bill_id}
    elif kind == "set_spend_pocket":
        user_id = str(params.get("user_id") or "").strip()
        subaccount_id = str(params.get("subaccount_id") or "").strip()
        if not user_id or not subaccount_id:
            raise ValueError("user_id and subaccount_id are required")
        variables = {"input": {
            "userId": user_id,
            "selectedSpendSubaccountId": subaccount_id,
        }}
    elif kind == "update_virtual_card":
        debit_card_id = str(params.get("debit_card_id") or "").strip()
        subaccount_id = str(params.get("subaccount_id") or "").strip()
        if not debit_card_id or not subaccount_id:
            raise ValueError("debit_card_id and subaccount_id are required")
        variables = {"input": {
            "debitCardId": debit_card_id,
            "subaccountId": subaccount_id,
        }}
    elif kind == "create_autopilot_rule" or kind == "edit_autopilot_rule":
        rule_id = str(params.get("rule_id") or "").strip()
        name = str(params.get("name") or "Autopilot rule").strip()
        if not name:
            raise ValueError("name is required")
        if kind == "edit_autopilot_rule" and not rule_id:
            raise ValueError("rule_id is required")
        # Build the REAL Crew AutopilotRule formula. The schema supports a full
        # action-type union (RoundUpTransfer / TargetBalanceTransfer /
        # SplitDeposit / SplitDepositByAmount / InternalTransfer /
        # SendNotification / SendWebhook / sweepExcess) and IdMatch/Or/And
        # conditions. Accept either an explicit verified ``formula`` (preferred,
        # any action type) or a roundUpTransfer convenience.
        if isinstance(params.get("formula"), dict):
            formula = _build_formula_from_payload(params["formula"])
        else:
            formula = _build_roundup_formula(params)
        if kind == "create_autopilot_rule":
            variables = {"input": {"name": name, "formula": formula}}
        else:
            variables = {"input": {
                "ruleId": rule_id,
                "name": name,
                "enabled": bool(params.get("enabled", True)),
                "formula": formula,
            }}
    elif kind == "create_pocket_reassignment_rule":
        match = str(params.get("match") or "").strip()
        account_id = str(params.get("account_id") or "").strip()
        assignment_subaccount_id = str(params.get("assignment_subaccount_id") or "").strip()
        if not match or not account_id or not assignment_subaccount_id:
            raise ValueError("match, account_id and assignment_subaccount_id are required")
        variables = {"input": {
            "match": match,
            "accountId": account_id,
            "assignmentSubaccountId": assignment_subaccount_id,
            "minAmount": _cents(params.get("min_amount"), "min_amount") if params.get("min_amount") is not None else None,
            "maxAmount": _cents(params.get("max_amount"), "max_amount") if params.get("max_amount") is not None else None,
        }}
    elif kind == "delete_pocket_reassignment_rule":
        reassignment_rule_id = str(params.get("reassignment_rule_id") or "").strip()
        if not reassignment_rule_id:
            raise ValueError("reassignment_rule_id is required")
        variables = {"input": {"reassignmentRuleId": reassignment_rule_id}}
    else:
        rule_id = str(params.get("rule_id") or "").strip()
        if kind == "delete_autopilot_rule" and not rule_id:
            raise ValueError("rule_id is required")
        variables = {"input": {"ruleId": rule_id}}
    return spec.operation_name, spec.query, variables


def _build_roundup_formula(params: dict[str, object]) -> dict:
    """RoundUpTransfer convenience rule (one of the supported action types)."""
    name = str(params.get("name") or "Round Up").strip()
    account_id = str(params.get("account_id") or "").strip()
    if not account_id or not name:
        raise ValueError("account_id and name are required")
    try:
        round_to_nearest = int(params.get("round_to_nearest", 100))
    except (TypeError, ValueError) as exc:
        raise ValueError("round_to_nearest must be an integer") from exc
    if round_to_nearest < 1:
        raise ValueError("round_to_nearest must be positive")
    card_ids = [str(item).strip() for item in params.get("card_ids", ()) if str(item).strip()]
    trigger = "DEBIT_CARD_TRANSACTION" if card_ids else "CASH_TRANSACTION_OCCURRED"
    formula = {
        "name": name,
        "description": "Save extra change from card purchases." if card_ids else "Round up transactions to the nearest dollar",
        "triggers": [trigger],
        "actions": [{"roundUpTransfer": {
            "accountId": account_id,
            "roundToNearest": round_to_nearest,
            "accountType": "ACCOUNT",
        }}],
    }
    subaccount_id = str(params.get("subaccount_id") or "").strip()
    if subaccount_id:
        formula["actions"][0]["roundUpTransfer"]["subaccountId"] = subaccount_id
    if card_ids:
        matches = [
            {"idMatch": {"entityId": card_id, "entitySchema": "DEBIT_CARDS"}}
            for card_id in card_ids
        ]
        formula["conditions"] = matches[0] if len(matches) == 1 else {"or": {"conditions": matches}}
    return formula


def _build_formula_from_payload(payload: dict) -> dict:
    """Validate + normalize a verified AutopilotRule formula payload.

    Accepts the exact Crew formula shape: {name, description, triggers,
    conditions{and.conditions[idMatch{entityId,entitySchema}]}, actions[
    <actionType>{...}]}. Every action key must be a known action type (the
    union from the real schema) so we never emit an invented action.
    """
    formula = dict(payload)
    if "name" not in formula:
        raise ValueError("formula.name is required")
    triggers = formula.get("triggers")
    if not isinstance(triggers, list) or not triggers:
        raise ValueError("formula.triggers must be a non-empty list")
    actions = formula.get("actions")
    if not isinstance(actions, list) or not actions:
        raise ValueError("formula.actions must be a non-empty list")
    _KNOWN_ACTIONS = frozenset({
        "roundUpTransfer", "targetBalanceTransfer", "splitDeposit",
        "splitDepositByAmount", "internalTransfer", "sendNotification",
        "sendWebhook", "sweepExcess",
    })
    for action in actions:
        if not isinstance(action, dict) or len(action) != 1:
            raise ValueError("each formula.actions entry must be a single {type: {...}} object")
        key = next(iter(action))
        if key not in _KNOWN_ACTIONS:
            raise ValueError(f"unknown autopilot rule action type: {key}")
    conditions = formula.get("conditions")
    if conditions is not None and not isinstance(conditions, dict):
        raise ValueError("formula.conditions must be an object (or absent)")
    return {"name": formula["name"], "description": formula.get("description"),
            "triggers": triggers, "conditions": conditions,
            "actions": actions}
