"""AI advisor: conversational copilot that can only PROPOSE actions.

The LLM receives a display-safe financial snapshot and may answer questions
freely, but any action it suggests becomes a pending proposal through the same
whitelisted pipeline as every other proposer. Approval stays with the owner.
"""

import json
import os
import re
from typing import Any, Callable, Dict, List, Optional

import requests

from .actions import ActionStore, UnknownActionTypeError
from .proposals import ProposalError, build_transfer_proposal


class AdvisorUnavailable(RuntimeError):
    pass


DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-4o-mini"
LLM_TIMEOUT_SECONDS = 30

_JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def llm_configured() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY") or os.environ.get("AI_API_KEY"))


def llm_model() -> str:
    return os.environ.get("OPENAI_MODEL", DEFAULT_MODEL)


class OpenAICompatClient:
    """Minimal OpenAI-compatible chat-completions client."""

    def __repr__(self) -> str:
        return "OpenAICompatClient()"

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        session=requests,
    ):
        self._api_key = api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("AI_API_KEY")
        self._base_url = (base_url or os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
        self._model = model or llm_model()
        self._session = session
        if not self._api_key:
            raise AdvisorUnavailable("AI provider is not configured (set OPENAI_API_KEY)")

    def complete(self, system: str, messages: List[Dict[str, str]]) -> str:
        try:
            response = self._session.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                json={
                    "model": self._model,
                    "messages": [{"role": "system", "content": system}] + list(messages),
                    "temperature": 0.3,
                },
                timeout=LLM_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
            return (payload.get("choices") or [{}])[0].get("message", {}).get("content", "")
        except requests.RequestException as exc:
            raise AdvisorUnavailable(f"AI provider unreachable: {type(exc).__name__}") from exc
        except (ValueError, KeyError, IndexError) as exc:
            raise AdvisorUnavailable("AI provider returned an unexpected response") from exc


def build_system_prompt(snapshot: Dict[str, Any]) -> str:
    return (
        "You are SimpleCrew's cautious financial copilot for a Crew banking dashboard.\n"
        "Current financial snapshot (JSON):\n" + json.dumps(snapshot) + "\n\n"
        "Rules:\n"
        "- Answer questions directly and briefly using the snapshot when relevant.\n"
        "- To suggest moving money between accounts/pockets, reply with normal text plus ONE "
        "json code block exactly like: ```json {\"action\": \"move_money\", \"params\": "
        "{\"from_name\": \"Checking\", \"to_name\": \"<pocket>\", \"amount\": 50, \"memo\": \"...\"}, "
        "\"summary\": \"Move $50.00 from Checking → <pocket>\"}```. Use names from the snapshot only.\n"
        "- Never claim an action was performed. Proposals require explicit owner approval.\n"
        "- Never invent balances; if unknown, say so.\n"
        "- Never include credentials, tokens, or account numbers."
    )


class FinancialContextBuilder:
    def __init__(self, snapshot_fn: Callable[[], Dict[str, Any]]):
        self._snapshot_fn = snapshot_fn

    def __repr__(self) -> str:
        return "FinancialContextBuilder()"

    def build(self) -> Dict[str, Any]:
        raw = self._snapshot_fn() or {}

        checking = raw.get("checking") or {}
        pockets = [
            {"name": p.get("name"), "balance": p.get("balance")}
            for p in (raw.get("pockets") or [])
            if isinstance(p, dict)
        ]
        snapshot: Dict[str, Any] = {
            "safe_to_spend": raw.get("safe_to_spend"),
            "accounts": [
                {"id": checking.get("id"), "name": checking.get("name"), "balance": checking.get("balance")}
            ] if checking else [],
            "pockets": pockets,
        }
        return snapshot


class AdvisorService:
    def __init__(
        self,
        llm_client: Any,
        context_builder: FinancialContextBuilder,
        store: ActionStore,
        resolver: Callable[[str], Optional[str]],
    ):
        self._client = llm_client
        self._context = context_builder
        self._store = store
        self._resolver = resolver

    def __repr__(self) -> str:
        return "AdvisorService()"

    def chat(self, user_message: str, history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
        snapshot = self._context.build()
        system = build_system_prompt(snapshot)
        messages = list(history or [])[-10:] + [{"role": "user", "content": user_message}]

        try:
            reply = self._client.complete(system, messages)
        except AdvisorUnavailable:
            raise
        except Exception as exc:
            raise AdvisorUnavailable(f"Advisor failed: {type(exc).__name__}") from exc

        result: Dict[str, Any] = {"reply": reply}
        proposal_stub = self._extract_proposal(reply)
        if proposal_stub is not None:
            cleaned_reply = _JSON_BLOCK.sub("", reply).strip()
            created = self._create_proposal(proposal_stub)
            if created is not None:
                result["reply"] = cleaned_reply or "Proposal ready for your review."
                result["proposal"] = created
            else:
                result["reply"] = (
                    (cleaned_reply + "\n\n" if cleaned_reply else "")
                    + "(I couldn't turn that into a valid proposal — adjust and try again.)"
                )
        return result

    def _extract_proposal(self, reply: str) -> Optional[Dict[str, Any]]:
        for match in _JSON_BLOCK.finditer(reply or ""):
            try:
                candidate = json.loads(match.group(1))
            except ValueError:
                continue
            if isinstance(candidate, dict) and "action" in candidate:
                return candidate
        return None

    def _create_proposal(self, candidate: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        action = candidate.get("action")
        params = candidate.get("params") or {}
        if action != "move_money":
            return None
        try:
            built = build_transfer_proposal(
                self._resolver,
                params.get("from_name"),
                params.get("to_name"),
                params.get("amount"),
                params.get("memo", ""),
            )
        except (ProposalError, TypeError):
            return None
        summary = candidate.get("summary") or built["summary"]
        try:
            created = self._store.propose(built["type"], built["params"], summary, requested_by="ai-advisor")
        except UnknownActionTypeError:
            return None
        return {"id": created["id"], "summary": summary, "state": created["state"]}
