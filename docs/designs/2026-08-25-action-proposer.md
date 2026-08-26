# Milestone 3b — Action Proposer Interface (Design)

Status: continuation of `2026-08-25-action-pipeline.md` per owner direction.

## Problem

The action pipeline exists, but the only proposer is the authenticated web session. A future AI/voice/command layer running on this Mac needs a deliberate way to create proposals — without ever receiving Crew credentials and without weakening approval.

## Goal

A localhost-only proposal endpoint plus a name-resolution helper, so a local assistant can say "move $50 from Checking to Rent" as structured JSON that lands in the owner's Pending Actions card.

## Boundary model

| Actor | Can | Cannot |
|---|---|---|
| Local assistant (127.0.0.1) | POST proposals via `/api/actions/propose/local` | approve, execute, read tokens |
| Owner (browser session) | everything: propose/approve/reject/execute | — |
| Remote devices (Tailscale) | full UI incl. approvals (session-gated) | reach local-only endpoint |

Proposals are inert by construction; spamming them cannot move money. The one-way door remains the owner's approval click.

## Components

- `crew/proposals.py`
  - `TransferResolver` protocol: `resolve(name) -> Optional[id]` for accounts/pockets.
  - `build_transfer_proposal(resolver, from_name, to_name, amount, memo)` → validated `{type, params, summary}` where summary is a human-readable sentence ("Move $50.00 from Checking → Rent (memo: 'October')"). Raises `ProposalError` on unresolvable names / non-positive amount.
- Flask wiring
  - Real resolver adapter over existing lookups (primary account + pockets).
  - `POST /api/actions/propose/local` — **restricted to loopback** (`request.remote_addr`), no session needed, accepts `{kind: "transfer", from, to, amount, memo}`; responds with the created request including its id so the assistant can reference it.
  - Existing session propose route unchanged.
- UI: pending card shows `summary` when present.

## Safety constraints

- Loopback check happens before any processing; non-loopback → 403.
- Resolver failures produce explicit errors, never guessed IDs.
- Amount stored as given (dollars); conversion stays inside the vetted `move_money` adapter.
- No new secrets; no credential material near this path.

## Testing strategy

Pure-unit tests for the builder/resolver contract; endpoint tests asserting loopback enforcement (`remote_addr` spoofed via test client environ), resolution errors, and end-to-end proposal→pending-card payload. No Crew contact.
