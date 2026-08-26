"""Local assistant: plain-English transfer intents -> loopback proposals.

Deterministic rule-based parsing (no LLM, no network beyond localhost).
An AI layer can later replace parse_transfer_intent behind the same contract:
intent dict in, proposal out, approval stays with the owner.
"""

import re
from typing import Any, Dict

import requests

DEFAULT_BASE_URL = "http://127.0.0.1:8080"
PROPOSE_TIMEOUT_SECONDS = 15

_INTENT_PATTERN = re.compile(
    r"""^\s*
        (?P<verb>move|transfer|send)\s+
        \$?(?P<amount>\d+(?:\.\d{1,2})?)\s*(?:dollars?|usd|bucks)?\s+
        from\s+(?P<from>.+?)\s+
        to\s+(?P<to>.+?)
        (?:\s+for\s+(?P<memo>.+?))?
        \s*$""",
    re.IGNORECASE | re.VERBOSE,
)


class IntentParseError(ValueError):
    pass


def parse_transfer_intent(text: str) -> Dict[str, Any]:
    match = _INTENT_PATTERN.match((text or "").strip())
    if not match:
        raise IntentParseError(
            "Could not understand that. Try: move $50 from checking to rent for october"
        )
    parts = match.groupdict()
    return {
        "kind": "transfer",
        "amount": float(parts["amount"]),
        "from": parts["from"].strip().strip("'\""),
        "to": parts["to"].strip().strip("'\""),
        "memo": (parts.get("memo") or "").strip().strip("'\""),
    }


def propose_intent(
    text: str,
    base_url: str = DEFAULT_BASE_URL,
    local_key: str = "",
) -> Dict[str, Any]:
    intent = parse_transfer_intent(text)
    try:
        response = requests.post(
            f"{base_url.rstrip('/')}/api/actions/propose/local",
            json=intent,
            headers={"X-Local-Key": local_key},
            timeout=PROPOSE_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise IntentParseError(
            f"Could not reach SimpleCrew at {base_url} — is the app running? ({exc})"
        ) from exc
    if response.status_code != 200:
        try:
            message = response.json().get("error", "")
        except ValueError:
            message = ""
        raise IntentParseError(message or f"Proposal rejected (HTTP {response.status_code})")
    return response.json()
