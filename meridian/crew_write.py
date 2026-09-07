"""Crew write-back executor (personal-use).

Executes an approved write proposal by invoking the WorkAssistant `crew-write`
CLI. The CLI owns the Keychain credential; Meridian only passes a validated
operation + input. Safety: unknown operations are never shelled out; a write
that returns 4/uncertain is reported as not-retryable; a rejected/blocked write
surfaces for the user.

Never imports Crew credentials into this process; never auto-retries.
"""

import json
import os
import subprocess
from typing import Any

# Only reviewed write operations ever reach the subprocess. Each op maps to a
# verified Crew mutation contract (see docs/project/CREW_GRAPHQL_CATALOG.md).
_ALLOWED = {
    "update_bill",
    "update_bill_reserve_settings",
    "create_autopilot_rule",
    "create_bill",
    "archive_bill",
    "create_subaccount",
    "delete_subaccount",
    "initiate_transfer",
    "create_paycheck_funding_plan",
    "update_paycheck_funding_plan",
    "delete_paycheck_funding_plan",
    "top_up_reserve",
    "delete_rule",
    "create_pocket_reassignment_rule",
    "delete_pocket_reassignment_rule",
    "set_spend_pocket",
    "create_virtual_card",
}

_DEFAULT_BIN = os.environ.get(
    "CREW_WRITE_BIN",
    "/Users/stephenwest/Applications/CrewWorkAssistantOTP/.venv/bin/crew-write",
)


class CrewWriteBlocked(RuntimeError):
    """The write was blocked before reaching Crew (unknown op / invalid input)."""


class CrewWriteUncertain(RuntimeError):
    """The write outcome is unknown; do not retry — verify in Crew."""


def execute_crew_write(
    operation: str,
    input_payload: dict[str, Any],
    *,
    crew_write_bin: str | None = None,
    timeout_seconds: int = 60,
) -> dict[str, Any]:
    """Run one approved Crew write. Returns a sanitized outcome dict.

    Outcomes:
      {"ok": True, "result": {...}, "retry_allowed": False}
      {"ok": False, "error": "rejected"|"blocked"|"uncertain"|"failed", "message": str, ...}
    """
    if operation not in _ALLOWED:
        return {
            "ok": False,
            "error": "blocked",
            "message": f"Unknown Crew write operation: {operation}",
            "retry_allowed": False,
        }
    if not isinstance(input_payload, dict):
        return {
            "ok": False,
            "error": "blocked",
            "message": "Crew write input must be an object",
            "retry_allowed": False,
        }

    command = [crew_write_bin or _DEFAULT_BIN, operation]
    try:
        result = subprocess.run(
            command,
            input=json.dumps({"input": input_payload}),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "error": "uncertain",
            "message": "Crew write timed out; outcome unknown — verify in Crew, do not retry.",
            "retry_allowed": False,
        }
    except OSError as exc:
        return {
            "ok": False,
            "error": "blocked",
            "message": f"Crew write connector unavailable: {exc}",
            "retry_allowed": False,
        }

    try:
        payload = json.loads(result.stdout or "{}")
    except ValueError:
        return {
            "ok": False,
            "error": "uncertain",
            "message": "Crew write connector returned an unreadable response; verify in Crew.",
            "retry_allowed": False,
        }

    if payload.get("ok"):
        return {"ok": True, "result": payload.get("result") or {}, "retry_allowed": False}
    error = payload.get("error") or "failed"
    if error == "uncertain":
        return {
            "ok": False,
            "error": "uncertain",
            "message": payload.get("message") or "Crew write outcome unknown; verify in Crew.",
            "retry_allowed": False,
        }
    return {
        "ok": False,
        "error": "rejected" if error in ("rejected", "blocked") else "failed",
        "message": payload.get("message") or "Crew write was not accepted.",
        "retry_allowed": False,
    }
