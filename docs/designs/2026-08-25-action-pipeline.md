# Milestone 3 — AI Automation Foundation: Action Pipeline (Design)

Status: Approved direction per owner ("auto token renewal, followed by AI automation"). This document defines the foundation milestone.

## Problem

The project's destination is an AI assistant that can *do things* to Crew — move money, manage pockets, configure Autopilot. The safety rule from every approved artifact is absolute: **AI never executes money movement directly.** Every consequential action must pass preview → explicit approval → execute → verify.

## Goal

Build the execution rails first, before any AI exists to ride them:

1. **Proposals** — a typed `ActionRequest` with whitelisted action types and structured params.
2. **Durable store** — proposals survive restarts; audit trail of who/when/what.
3. **Human approval** — only the logged-in owner can approve/reject, via UI or API.
4. **Vetted executors** — each approved action type maps to exactly one existing, tested function (e.g., `move_money`). No executor may construct raw Crew traffic itself.
5. **Verification** — after execution, a typed verifier confirms the outcome (e.g., re-read state) before an action is marked done; otherwise it lands in a `failed`/unverified state for human review.

Natural-language understanding comes later as just another *proposer* — it can create requests, nothing more. It never receives Crew credentials and never bypasses approval.

## Non-goals (this milestone)

- No natural-language parsing / no LLM integration yet.
- No scheduled/unattended approvals. Approval is always a live human click.
- No new Crew operations; executors wrap existing vetted functions only.

## Action lifecycle

```
PROPOSED ──approve──> APPROVED ──execute──> EXECUTED ──verify──> VERIFIED
    │                                                 │
    └──reject──> REJECTED                             └──failure──> FAILED
              (terminal)                    APPROVED not executed within TTL ──> EXPIRED
```

Rules:
- State transitions are one-way and enforced by the store; illegal transitions raise.
- `params` and `result` are stored as JSON snapshots (audit/replay-free forensics).
- Approval records `decided_by` + timestamp; execution records outcome snapshot.

## Components

- `crew/actions.py` — `ActionState`, `ActionRequest`, `ActionStore` (SQLite, same DB), transition enforcement, whitelist validation.
- `crew/executors.py` — registry mapping action type → executor callable + verifier callable. Executors return result dicts in the same shape as their wrapped functions (`move_money`'s error contract).
- Flask API (`app.py`):
  - `GET /api/actions/pending`, `POST /api/actions/<id>/approve`, `POST /api/actions/<id>/reject`
  - `POST /api/actions/propose` — authenticated app users now; later exposed deliberately to local AI consumers (they authenticate as the user; they still cannot self-approve).
- UI: pending-actions card in Account settings (later moved into its own view if it grows).

## Safety constraints

- Proposing ≠ approving: even the owner's own proposals require an explicit approve click.
- Executors reuse vetted functions — transfer semantics (`uncertain_write`, no-retry) inherit automatically.
- Verification failures are loud: action stays visible in `FAILED` until dismissed by the owner.
- All payloads sanitized like the rest of the app; no credential material ever enters action records.

## Testing strategy

TDD with temp SQLite stores and stub executors: lifecycle legality, whitelist rejection, JSON round-trips, expiry, executor success/failure mapping, verification gating. No Crew contact.

## Acceptance criteria

1. A proposal can only reach `VERIFIED` through approve → execute → verify with recorded actor/timestamps at each step.
2. Unknown action types cannot be proposed.
3. An expired approval can no longer execute.
4. Executor failure leaves a visible FAILED record with the normalized error contract.
5. Full suite passes without contacting Crew.
