# Enhanced SimpleCrew — Current Status

Last consolidated: 2026-08-31 (OpenRouter/ORSC build handoff)

## Canonical sources

> This copy of the project is the **separate OpenRouter build** living on
> `dirdir207-png/ORSC`. It does not touch the preexisting SimpleCrew repository
> (`dirdir207-png/SimpleCrew`), its branches, or the upstream project, which
> continue independently. All work here stays on ORSC.

- Repository: `dirdir207-png/ORSC` (separate Meridian build)
- Default branch: `main` (unchanged; this build is developed on a branch)
- Implementation branch: `feat/meridian-implementation` (on ORSC)
- SimpleCrew-side branches (`ox-alpha/meridian-overhaul` and others) are owned by the other project and are not used by this build
- Approved design: `docs/superpowers/specs/2026-08-26-meridian-product-overhaul-design.md`
- Implementation plan: `docs/superpowers/plans/2026-08-26-meridian-overhaul-implementation.md`
- Model strategy: `docs/superpowers/plans/2026-08-26-meridian-model-and-token-strategy.md`
- Codex CLI handoff: `docs/project/CODEX_CLI_HANDOFF.md`
- Approved specifications override informal chat history when they conflict.

## Architecture and safety decisions

- Enhanced SimpleCrew runs on the always-on Mac.
- Crew GraphQL is the primary banking-data path.
- Crew credentials and bearer/session tokens remain server-side/local and must never be exposed to browser or Base44 frontend code.
- Tailscale is the intended private remote-access path (`docs/REMOTE_ACCESS.md`).
- Existing SimpleCrew authentication/passkey protection remains in place.
- Financial mutations must never be retried automatically; uncertain transfer outcomes surface as `uncertain_write` / verify-state.

## Milestone status

### Slice 1 — Trustworthy foundation and shell: COMPLETE ✅

Tasks 1–8 fully implemented, tested, and pushed to `feat/meridian-implementation`:
- Production config, CI, Docker, browser-smoke gates (Task 1)
- Atomic/idempotent action execution with EXECUTING claim state (Task 2)
- Versioned migrations (001–004), normalized financial read model (Task 3)
- Crew data adapter → Meridian graph (Task 4)
- `/api/meridian/*` read APIs (Task 5)
- Editorial Wealth design tokens, responsive shell (Task 6)
- Today workspace, Activity ledger with cursor pagination (Task 7)
- Transaction inspector (Task 8)
- **Slice 1 Docker gate passed: 204 tests, Ruff clean, meridian:slice1 image verified**

### Slice 2 — Commitments and funding: COMPLETE ✅

Tasks 9–12 fully implemented, tested, and pushed to `feat/meridian-implementation`:
- Unified Meridian Commitments with dataclass + repository (Task 9)
- Funding calculus with 7 rule kinds, DST-immune, carry-forward (Task 10)
- Idempotent scheduled funding proposals with dedup (Task 11)
- Plan workspace: service, API, UI (Task 12)
- **Slice 2 Docker gate passed: 259 tests + 28 browser skips, Ruff clean, meridian:slice2 image verified**

### Crew Session Broker — COMPLETE ✅ (merged to main)

- AES-256-GCM encrypted credential storage, macOS Keychain adapter
- Loopback broker API with capability authentication
- Cookie-aware transport, Docker-side broker transport
- Renewal endpoints, LaunchAgent installer, Docker Compose template
- **150 broker-focused tests passing** (2 pre-existing Meridian advisor failures unrelated)

### Slice 3 — Unified providers and transaction intelligence: COMPLETE IN CURRENT BRANCH ✅

- Tasks 13–16 (providers, reconciliation hardening) are consolidated in the ORSC `feat/meridian-implementation` branch.

### Slice 4 — Advanced intelligence and consolidation: COMPLETE IN CURRENT BRANCH ✅

- Tasks 17–20 are consolidated in the ORSC `feat/meridian-implementation` branch.

### Slice 5 — Document Intelligence: COMPLETE IN CURRENT BRANCH ✅

- Tasks 21–23 are consolidated in the ORSC `feat/meridian-implementation` branch.

### Slice 6 — Life Context: COMPLETE IN CURRENT BRANCH ✅

- Task 24 is consolidated in the ORSC `feat/meridian-implementation` branch.

### Slice 7 — Asset and Contract Memory: IN PROGRESS

- Task 25 is consolidated in the ORSC `feat/meridian-implementation` branch.
- Task 26 has untracked RED test scaffolding but no memory service or frontend implementation yet.

> Historical per-task commit SHAs (`726e00e`…`a092c4a`) were local-only and never
> existed on GitHub; this build tracks the ORSC branch tip instead.
- Task 26 has untracked RED test scaffolding but no memory service or frontend implementation yet.

## Current test suite

- The repository currently contains 365 Python test functions, including untracked Task 26 tests.
- Historical Slice 2 evidence remains 259 unit tests plus 28 browser skips with Ruff and Docker gates passing.
- A fresh full-suite, Ruff, browser, audit, and Docker release gate is required before reporting current pass counts.

## Current blockers

- TokenX routing unavailable: sub-agent spawning is blocked in this session, so parallel execution must occur in a verified Codex CLI environment or run sequentially in the parent.
- AI providers: owner's OpenAI key has no credits (429); OpenRouter free-tier quota tight
- Verification workflow: Playwright screenshot harness against isolated instance gates all UI changes

## Codex CLI handoff

A corrected handoff document has been created at `docs/project/CODEX_CLI_HANDOFF.md` containing:
- All project document references
- Current repository state
- Git evidence that Tasks 13–25 are implemented
- Task 26 scope and file locations
- Parallel agent lanes with disjoint write scopes
- TDD workflow requirements
- Model routing strategy
- Safety rules and commit conventions
- Final automated and owner-only acceptance gates

## Next action

Launch the Codex CLI coding task using the handoff document. The task should:
1. Read `docs/project/CODEX_CLI_HANDOFF.md`
2. Complete Task 26 following TDD
3. Run the final release gate and reconcile documentation from actual evidence
4. Stop before browser login / live acceptance

Remaining gate (desktop / owner): start the Mac broker and an isolated Docker deployment, complete one interactive Crew login, confirm `healthy`, and run read-only sync while verifying no secret leakage.
