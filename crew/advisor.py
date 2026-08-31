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


class MeridianAdvisorBridge:
    """Expose the contextual Meridian advisor through Crew's global advisor boundary."""

    def __init__(self, contextual_advisor):
        self._contextual_advisor = contextual_advisor

    def ask(self, context, question):
        return self._contextual_advisor.ask(context, question)


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

    @property
    def model(self) -> str:
        return self._model

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
            message = (payload.get("choices") or [{}])[0].get("message") or {}
            content = message.get("content")
            if not content:
                # Some models place output in reasoning/other fields
                content = message.get("reasoning") or "".join(
                    part.get("text", "") for part in (message.get("reasoning_content") or [])
                    if isinstance(part, dict))
            if not content:
                raise AdvisorUnavailable("provider returned an empty response")
            return content
        except requests.HTTPError as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            body_text = ""
            try:
                body_text = exc.response.json().get("error", {}).get("message", "")
            except Exception:
                pass
            detail = {
                401: "authentication rejected",
                402: "out of credits — add billing at the provider",
                429: "rate limited / quota exceeded",
            }.get(status, f"HTTP {status}")
            raise AdvisorUnavailable(f"{detail}{(' — ' + body_text[:120]) if body_text else ''}") from exc
        except requests.RequestException as exc:
            raise AdvisorUnavailable(f"AI provider unreachable: {type(exc).__name__}") from exc
        except (ValueError, KeyError, IndexError) as exc:
            raise AdvisorUnavailable("AI provider returned an unexpected response") from exc


OPENROUTER_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_DEFAULT_MODEL = "stealth/ox-alpha"


class FailoverLLMClient:
    """Tries configured providers in order; surfaces the first success.

    Providers that fail are put on a short cooldown so a dead primary
    doesn't slow every subsequent message.
    """

    COOLDOWN_SECONDS = 300.0

    def __init__(self, providers: List[tuple]):
        self._providers = [(name, client) for name, client in providers if client is not None]
        self._cooldown_until: Dict[str, float] = {}
        self.last_provider: Optional[str] = None

    def __repr__(self) -> str:
        return f"FailoverLLMClient(providers={[name for name, _ in self._providers]})"

    def providers(self) -> List[str]:
        return [name for name, _ in self._providers]

    def complete(self, system: str, messages: List[Dict[str, str]]) -> str:
        import time as _time
        errors: List[str] = []
        now = _time.monotonic()
        tried_any = False
        for name, client in self._providers:
            if self._cooldown_until.get(name, 0) > now:
                errors.append(f"{name}: cooling down after recent failure")
                continue
            tried_any = True
            try:
                reply = client.complete(system, messages)
                self.last_provider = name
                self._cooldown_until.pop(name, None)
                return reply
            except AdvisorUnavailable as exc:
                self._cooldown_until[name] = now + self.COOLDOWN_SECONDS
                errors.append(f"{name}: {exc}")
        self.last_provider = None
        if not self._providers:
            raise AdvisorUnavailable("No AI provider is configured")
        if not tried_any:
            raise AdvisorUnavailable(
                "All AI providers are cooling down after recent failures — try again in a few minutes. "
                + "; ".join(errors))
        raise AdvisorUnavailable("All AI providers failed — " + "; ".join(errors))


def build_llm_chain(session=requests) -> FailoverLLMClient:
    """Provider chain from environment: OpenAI primary, OpenRouter fallback."""
    providers: List[tuple] = []

    openai_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("AI_API_KEY")
    if openai_key:
        providers.append((
            "openai",
            OpenAICompatClient(
                api_key=openai_key,
                base_url=os.environ.get("OPENAI_BASE_URL", DEFAULT_BASE_URL),
                model=os.environ.get("OPENAI_MODEL", DEFAULT_MODEL),
                session=session,
            ),
        ))

    openrouter_key = os.environ.get("OPENROUTER_API_KEY")
    if openrouter_key:
        providers.append((
            "openrouter",
            OpenAICompatClient(
                api_key=openrouter_key,
                base_url=os.environ.get("OPENROUTER_BASE_URL", OPENROUTER_DEFAULT_BASE_URL),
                model=os.environ.get("OPENROUTER_MODEL", OPENROUTER_DEFAULT_MODEL),
                session=session,
            ),
        ))

    return FailoverLLMClient(providers)


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
        if self._client is None:
            raise AdvisorUnavailable(
                "AI advisor is not configured. Set OPENAI_API_KEY (and optionally OPENAI_BASE_URL / OPENAI_MODEL) and restart."
            )
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
