# Crew Session Broker — Codex CLI Handoff

## Objective

Finish the approved test-driven Crew session broker implementation and read-only live acceptance without disturbing unrelated Meridian work.

## Authoritative documents

- `docs/project/PROJECT_INSTRUCTIONS.md`
- `docs/project/CURRENT_STATUS.md`
- `docs/superpowers/specs/2026-08-28-crew-session-broker-design.md`
- `docs/superpowers/plans/2026-08-28-crew-session-broker.md`

## Repository state

- Branch: `ox-alpha/meridian-overhaul`
- Latest broker integration commit: `17ab76a`
- Existing uncommitted Meridian changes predate this broker task. Preserve them exactly; do not stage or rewrite unrelated files.
- Broker commits: `f866291`, `e0cb17c`, `4ca0a70`, `bdf39c9`, `17ab76a`.

## Completed

- Versioned AES-GCM session credential storage backed by SQLite ciphertext.
- macOS Keychain encryption-key adapter and private broker capability file.
- Playwright Crew session-cookie filtering/capture foundation.
- Cookie-aware Crew transport.
- Loopback broker API with capability authentication.
- Docker-side broker transport and health classifications.
- Mac broker CLI, LaunchAgent installer/template, and Docker Compose template wiring.
- Security fixes for shared HTTP sessions, mutation ambiguity, GraphQL query-kind mismatch, and insecure existing capability files.

## Current verification

- `pytest -q tests/crew tests/test_app_crew_integration.py`: 150 passed, 1 skipped, 2 failed.
- Both failures are pre-existing Meridian advisor failures: tests monkeypatch `app.llm_configured`, which the current dirty Meridian `app.py` no longer exports.
- Focused broker integration set passed: 34 tests.

## Remaining work

1. Complete broker renewal endpoints: `/renew/start` and `/renew/status/<id>` with validated-before-save session renewal and sanitized status.
2. Update Docker Flask renewal routes to proxy to the broker when configured while retaining legacy bearer renewal fallback.
3. Address remaining security-review gaps with failing tests first:
   - replace loose operation-name/query-kind checks with broker-owned exact operation documents or equivalent exact mapping;
   - ensure mutation 5xx/429/malformed responses remain uncertain;
   - restrict captured cookies by required name/domain/path after observing the real Crew cookie set safely;
   - avoid placing the Keychain encryption key in process argv and handle concurrent key creation;
   - enforce loopback validation at the production runner boundary.
4. Update UI messages and `docs/REMOTE_ACCESS.md`.
5. Update `docs/project/CURRENT_STATUS.md` with commits, tests, decisions, blockers, and next action.
6. Run full tests, Ruff, dependency audit, Docker build, and secret-leak checks.
7. Stop before browser login/live acceptance and report exactly what the desktop task must do. Do not request, display, copy, log, or transmit real cookies/tokens.

## Safety rules

- Never expose Crew credentials, cookies, OTPs, passwords, capability values, or Keychain keys in output, logs, browser JS, source control, docs examples, or test fixtures.
- Never automatically retry a financial mutation. Any ambiguous mutation outcome is `CrewUncertainWriteError` and requires reconciliation.
- Do not execute a real financial mutation during acceptance.
- Do not push, merge, or publish.
- Follow TDD: observe each new regression test fail for the intended reason before implementation.
- Commit only broker-task files; preserve all unrelated dirty work.

## CLI stopping point

Continue autonomously through code, tests, documentation, and local non-browser verification. Stop only when interactive Crew login or another desktop-only approval is genuinely required, then write a concise status and exact next browser action.
