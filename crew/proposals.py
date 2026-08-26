"""Proposal builders for local AI/command proposers.

Translates human-phrased intents ("move $50 from Checking to Rent") into
validated, structured action proposals. Resolvers map names to ids using
existing app lookups — this module never talks to Crew itself.
"""

from typing import Any, Callable, Dict, Optional


class ProposalError(ValueError):
    pass


class TransferResolver:
    def resolve(self, name: str) -> Optional[str]:
        raise NotImplementedError


def _resolve(resolver: Callable[[str], Optional[str]], name: str, role: str) -> str:
    target_id = resolver((name or "").strip().lower())
    if not target_id:
        raise ProposalError(f"Could not resolve {role} '{name}' to an account or pocket")
    return target_id


def build_transfer_proposal(
    resolver: Any,
    from_name: str,
    to_name: str,
    amount: Any,
    memo: str = "",
) -> Dict[str, Any]:
    resolve_fn: Callable[[str], Optional[str]] = (
        resolver.resolve if hasattr(resolver, "resolve") else resolver
    )
    try:
        amount_value = float(amount)
    except (TypeError, ValueError):
        raise ProposalError(f"Amount must be a number, got {amount!r}")
    if amount_value <= 0:
        raise ProposalError(f"Amount must be positive, got {amount_value}")

    source_id = _resolve(resolve_fn, from_name, "source")
    destination_id = _resolve(resolve_fn, to_name, "destination")
    if source_id == destination_id:
        raise ProposalError("Source and destination are the same account or pocket")

    summary = f"Move ${amount_value:,.2f} from {(from_name or '').strip().title()} → {(to_name or '').strip().title()}"
    if memo and memo.strip():
        summary += f" (memo: '{memo.strip()}')"

    return {
        "type": "move_money",
        "params": {
            "from_id": source_id,
            "to_id": destination_id,
            "amount": amount_value,
            "memo": (memo or "").strip(),
        },
        "summary": summary,
    }
