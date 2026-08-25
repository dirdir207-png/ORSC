# Enhanced SimpleCrew — Current Status

Last consolidated: 2026-08-25 (post Milestone 1)

## Canonical sources

- Repository: `dirdir207-png/SimpleCrew`
- Default branch: `main` (protected; do not work directly on it)
- Approved design: bundle artifact `Enhanced_SimpleCrew_Design_Spec` / `2026-08-24-hybrid-gateway-foundation-design.md`
- Approved implementation plan: bundle artifact `Enhanced_SimpleCrew_Implementation_Plan` / `2026-08-24-hybrid-gateway-foundation.md`
- Approved specifications override informal chat history when they conflict.

## Architecture and safety decisions

- Enhanced SimpleCrew runs on the always-on Mac.
- Crew GraphQL is the primary banking-data path.
- Crew credentials and bearer/session tokens remain server-side/local and must never be exposed to browser or Base44 frontend code.
- Tailscale is the intended private remote-access path (`docs/REMOTE_ACCESS.md`).
- Existing SimpleCrew authentication/passkey protection remains in place.
- Financial mutations must never be retried automatically; uncertain transfer outcomes surface as `uncertain_write` / verify-state.

## Milestone status

### Milestone 1 — Hybrid Gateway Foundation: COMPLETE (merged PR #2, 2026-08-25)

Implemented independently and verified; supersedes the unrecoverable prior local commit `32fe0b8`.

- All eight approved TDD tasks executed: credential-provider boundary, `CrewClient`, health classification, Flask/UI wiring, transfer migration, first safe-read migration, Tailscale docs, verification gate.
- Test suite at merge: 21 passed (no test contacts real Crew).
- Live verification performed server-side against real Crew: valid token → `healthy`, junk token → `unauthorized`, blackhole endpoint → `unreachable`.
- Deployment: local Docker build (`docker-compose.yml` switched from `ghcr.io/nerdykidtech/simplecrew:latest` to `build: .`, image `simplecrew-local`), running against a copy of production data; original untouched at `~/Documents/SimpleCrew`.
- Post-merge hardening: stored tokens carrying a literal `Bearer ` prefix are normalized before header injection.

### Review blockers from prior work — REPRODUCED AND REMEDIATED (this branch)

1. Truthy non-string transfer ID mistaken for confirmed success → reproduced by regression test; `move_money` now requires a non-empty string `result.id`.
2. Missing `.dockerignore` → confirmed missing (prior image build could include databases/`.env`/caches); added covering secrets, data, venv, git metadata, caches, docs/tests.

## Prior-work recovery note

The previously reported 103-test result belonged to unrecoverable local commit `32fe0b8`. Recovery is moot for Milestone 1 scope: the milestone was re-implemented from the authoritative bundle and merged. The two review blockers it flagged were reproduced against the new implementation and fixed here.

## Roadmap

1. **Milestone 2 — automatic Crew credential renewal**: implement safe renewal behind the existing `MacCredentialProvider` seam (guided re-authentication with OTP; captured tokens stored server-side only).
2. **Milestone 3 — AI automation foundation**: natural-language money movement gated by preview → explicit approval → execute → verify; Base44/AI consumers use a deliberate application API and never receive Crew credentials directly.

## Current blockers

None.

## Next action

Begin Milestone 2 design + TDD on a feature branch.
