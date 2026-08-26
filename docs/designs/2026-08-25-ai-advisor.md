# Milestone 5 — AI Advisor (Design)

Status: owner direction ("bring in a true AI advisor"). Continues the M3 safety architecture.

## Goal

A conversational advisor inside SimpleCrew that understands your finances, answers questions, and — when you ask for an action — emits a *proposal* into the existing Pending Actions pipeline. It never moves money itself.

## Provider strategy

Provider-agnostic via env vars, OpenAI-compatible chat completions:

- `OPENAI_API_KEY` (or `AI_API_KEY` alias), `OPENAI_BASE_URL` (default `https://api.openai.com/v1`), `OPENAI_MODEL` (default `gpt-4o-mini`)
- Not configured → advisor endpoints return a clear "not configured" state; UI shows setup hint. No crashes, no fake intelligence.

## Architecture

- `crew/advisor.py`
  - `LLMClient` protocol: `complete(system: str, messages: list[dict]) -> str`.
  - `OpenAICompatClient`: thin requests-based implementation; timeouts; errors normalized to `AdvisorUnavailable`; **never logs message bodies or keys**.
  - `FinancialContextBuilder`: builds a display-safe JSON snapshot from existing cached functions (balances, pockets w/ amounts, recent transactions summary). Numbers and names only — no tokens, no credentials, no full account numbers. Cached per-request.
  - `AdvisorService.chat(user_message, history) -> {reply, proposal}`:
    - System prompt: role = cautious financial copilot; tools = propose transfer; MUST emit strict JSON block when proposing (`{"action": "move_money", "params": {...}, "summary": "..."}`); otherwise plain text answer.
    - Parses optional proposal JSON from reply; validates via whitelist + resolver (same rules as local proposer); stores via `ActionStore.propose(..., requested_by='ai-advisor')`; returns sanitized `{id, summary}` stub with the reply.
- Flask
  - `POST /api/advisor/chat` (`{message, history?}`) → `{reply, proposal?}` or 503 not-configured. Login required.
  - `GET /api/advisor/status` → `{configured, model}` (no key material).
- UI: "AI Advisor" card in Account view (chat log, input box, send). Proposal confirmations render as links/notes pointing at Pending Actions.

## Safety constraints

- Advisor output is treated as untrusted text: only whitelisted action types with resolvable params become proposals; everything else is surfaced as chat text.
- Proposal ≠ approval (unchanged): owner clicks Approve in Pending Actions; approvals still expire in 1h.
- Context payloads contain balances/names only; built server-side; LLM responses never persisted to DB beyond the ephemeral chat history in the browser session.
- Key lives in env/server-side only; absent from logs, responses, and repo.

## Testing strategy

Fake LLM clients cover: plain answer passthrough; proposal extraction happy path; malformed proposal JSON → treated as text; unknown action type → rejected as proposal, mentioned in reply; unavailable client → normalized error; context builder redacts and shapes data. Endpoint tests: auth, not-configured path, no token leakage. No real network calls.
