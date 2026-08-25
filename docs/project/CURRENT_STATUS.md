# Enhanced SimpleCrew — Current Status

Last consolidated: 2026-08-25 (Milestone 2 implementation)

## Canonical sources

- Repository: `dirdir207-png/SimpleCrew`
- Default branch: `main` (protected; do not work directly on it)
- Approved design: bundle artifact `Enhanced_SimpleCrew_Design_Spec` / `2026-08-24-hybrid-gateway-foundation-design.md`
- Milestone 2 design: `docs/designs/2026-08-25-guided-credential-renewal.md`
- Approved specifications override informal chat history when they conflict.

## Architecture and safety decisions

- Enhanced SimpleCrew runs on the always-on Mac.
- Crew GraphQL is the primary banking-data path.
- Crew credentials and bearer/session tokens remain server-side/local and must never be exposed to browser or Base44 frontend code.
- Tailscale is the intended private remote-access path (`docs/REMOTE_ACCESS.md`).
- Existing SimpleCrew authentication/passkey protection remains in place.
- Financial mutations must never be retried automatically; uncertain transfer outcomes surface as `uncertain_write` / verify-state.

## Milestone status

### Milestone 1 — Hybrid Gateway Foundation: COMPLETE (merged PR #2, hardening PR #3)

- All eight approved TDD tasks executed: credential-provider boundary, `CrewClient`, health classification, Flask/UI wiring, transfer migration, first safe-read migration, Tailscale docs, verification gate.
- Live verification server-side against real Crew: valid token → `healthy`, junk token → `unauthorized`, blackhole endpoint → `unreachable`.
- Deployment: local Docker build (`build: .`, image `simplecrew-local`) running against a copy of production data; original untouched at `~/Documents/SimpleCrew`.
- Stored tokens with literal `Bearer ` prefix are normalized before header injection.

### Milestone 2 — Guided credential renewal: IMPLEMENTED (branch `feat/guided-credential-renewal`, pending owner verification)

- Design: `docs/designs/2026-08-25-guided-credential-renewal.md`.
- `crew/renewal.py` `GuidedRenewalService`: single-flight sessions, uuid ids, deadline expiry, late-capture discard, sanitized status payloads (whitelisted fields; health reduced to state/message).
- `crew/browser_capture.py`: Playwright Chromium capturer listening for the first `authorization` header sent to `api.trycrew.com`; lazy import with actionable install guidance when absent.
- Flask: `POST /api/account/crew/reconnect/start`, `GET /api/account/crew/reconnect/status/<id>` (login required, 404 on unknown id, route-level whitelist sanitization); renewed credentials stored via the same path as manual saves.
- UI: **Reconnect Crew** button appears when health is `unauthorized`; polls status and re-checks health after capture.
- Test suite on branch: 41 passing (renewal lifecycle 8, capturer 4, endpoints/UI regressions included). No test opens a browser or contacts Crew.
- Pending manual gate: end-to-end renewal with real Crew login (requires Playwright install + invalid-token simulation).

### Review blockers from prior work — REPRODUCED AND REMEDIATED (merged PR #3)

1. Truthy non-string transfer ID mistaken for confirmed success → reproduced by regression test; `move_money` now requires a non-empty string `result.id`.
2. Missing `.dockerignore` → confirmed missing (prior image build could include databases/`.env`/caches); added covering secrets, data, venv, git metadata, caches, docs/tests.

## Prior-work recovery note

The previously reported 103-test result belonged to unrecoverable local commit `32fe0b8`. Recovery is moot for Milestone 1 scope: the milestone was re-implemented from the authoritative bundle and merged. The two review blockers it flagged were reproduced against the new implementation and fixed here.

## Roadmap

1. ~~Milestone 2 — automatic Crew credential renewal~~ (implemented, pending owner verification)
2. **Milestone 3 — AI automation foundation**: natural-language money movement gated by preview → explicit approval → execute → verify; Base44/AI consumers use a deliberate application API and never receive Crew credentials directly.

## Current blockers

None.

## Next action

Owner manual gate for Milestone 2: install Playwright helper, simulate an invalid token, complete one guided renewal against real Crew, confirm `healthy` — then merge and begin Milestone 3.
