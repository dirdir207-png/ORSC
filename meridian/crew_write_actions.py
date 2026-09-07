"""Crew write-back executors for the proposal→approval→execute pipeline.

Each executor wraps meridian.crew_write.execute_crew_write so an approved
proposal can push a bill/rule change to Crew through the crew-write CLI.
The ExecutorSpec.execute gets the proposal params; the verifier re-reads the
local commitment to confirm the change landed.
"""

from typing import Any, Callable, Dict, Optional

from .commitments import CommitmentRepository
from .crew_write import execute_crew_write

# Params payloads follow the Crew wire contract (camelCase) so the executor is a
# thin pass-through; the UI/proposal layer maps local records to wire form.


def _crew_write_executor(operation: str):
    def execute(params: Dict[str, Any]) -> Dict[str, Any]:
        outcome = execute_crew_write(operation, params)
        if not outcome.get("ok"):
            raise RuntimeError(outcome.get("message") or outcome.get("error") or "Crew write failed")
        # execute_approved_action expects an explicit success flag.
        return {"success": True, "crew": outcome}

    return execute


def _verify_stored(db_path: str, check_field: str):
    """Returns a verifier that re-reads the commitment for an expected value.

    The Crew write acceptance is the authoritative result; the local re-read is
    advisory (records may not be created locally yet, or the refresh hasn't
    repulled the change). Never fail an accepted Crew write over local state.
    """
    repo = CommitmentRepository(db_path)

    def verify(params: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
        commitment_id = params.get("commitment_id")
        if commitment_id is None:
            return {"ok": True, "check": "crew-write-accepted", "note": "no local record to re-read"}
        record = repo.get_commitment(int(commitment_id))
        expected = params.get(check_field)
        actual = getattr(record, check_field) if record else None
        local_ok = record is not None and (expected is None or actual == expected)
        return {"ok": local_ok or bool(result.get("ok")), "check": f"commitment-{check_field}"}

    return verify


def crew_write_executors(db_path: str) -> Dict[str, tuple[Callable, Optional[Callable]]]:
    """Register the Crew write executor specs (params-dict adapters)."""
    def _exec(op: str):
        return _crew_write_executor(op)

    no_verify = None
    base: Dict[str, tuple[Callable, Optional[Callable]]] = {
        "update_crew_bill": (_exec("update_bill"), _verify_stored(db_path, "name")),
        "update_crew_bill_reserve_settings": (
            _exec("update_bill_reserve_settings"),
            _verify_stored(db_path, "name"),
        ),
        "create_crew_autopilot_rule": (_exec("create_autopilot_rule"), no_verify),
        "create_crew_bill": (_exec("create_bill"), no_verify),
        "archive_crew_bill": (_exec("archive_bill"), no_verify),
        "create_crew_pocket": (_exec("create_subaccount"), no_verify),
        "delete_crew_pocket": (_exec("delete_subaccount"), no_verify),
        "crew_initiate_transfer": (_exec("initiate_transfer"), no_verify),
        "create_crew_paycheck_funding_plan": (
            _exec("create_paycheck_funding_plan"),
            no_verify,
        ),
        "update_crew_paycheck_funding_plan": (
            _exec("update_paycheck_funding_plan"),
            no_verify,
        ),
        "delete_crew_paycheck_funding_plan": (
            _exec("delete_paycheck_funding_plan"),
            no_verify,
        ),
        "top_up_crew_reserve": (_exec("top_up_reserve"), no_verify),
        "delete_crew_autopilot_rule": (_exec("delete_rule"), no_verify),
        "create_crew_pocket_reassignment_rule": (
            _exec("create_pocket_reassignment_rule"),
            no_verify,
        ),
        "delete_crew_pocket_reassignment_rule": (
            _exec("delete_pocket_reassignment_rule"),
            no_verify,
        ),
    }
    return base
