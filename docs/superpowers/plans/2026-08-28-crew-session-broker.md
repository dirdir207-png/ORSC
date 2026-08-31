# Crew Session Broker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Authenticate SimpleCrew through an encrypted Mac-local Crew session broker while preserving legacy bearer compatibility and single-attempt mutation safety.

**Architecture:** A Mac-only broker owns Playwright renewal, Keychain-backed AES-GCM encryption, and cookie-aware Crew HTTP requests. Docker keeps the existing `CrewClient.execute` contract and talks to the broker through a loopback-only capability-authenticated API; a direct bearer transport remains available during migration.

**Tech Stack:** Python 3.12, Flask, requests, Playwright, SQLite, macOS `security`, AES-GCM from `cryptography`, pytest, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-08-28-crew-session-broker-design.md`

## Global Constraints

- Crew credentials, cookies, OTPs, passwords, and encryption keys never enter browser JavaScript, logs, API responses, documentation examples, source control, or Docker plaintext configuration.
- Broker binding is loopback-only and every request requires a capability secret checked in constant time.
- Crew destinations and operations are allowlisted; the broker is not a general HTTP proxy.
- Financial mutations receive exactly one outbound attempt; transport ambiguity raises `CrewUncertainWriteError`.
- Legacy bearer authentication remains functional until a validated session credential exists.
- Automated tests use temporary databases and synthetic secrets and never contact Crew or production Keychain.

---

### Task 1: Versioned Encrypted Credential Store

**Files:**
- Create: `crew/session_credentials.py`
- Create: `tests/crew/test_session_credentials.py`
- Modify: `requirements.txt`

**Interfaces:**
- Produces: `SessionCredential(cookies, expires_at=None)`, `SessionCipher.encrypt/decrypt`, `SessionCredentialStore.save/load`, and `KeyProvider.get_or_create_key()`.
- Consumes: SQLite path and an injected KeyProvider.

- [ ] Write failing tests for AES-GCM round trip, unique nonces, tamper/wrong-key rejection, canonical cookie serialization, SQLite ciphertext without plaintext, and legacy-empty state.
- [ ] Run `pytest -q tests/crew/test_session_credentials.py` and verify failures are caused by missing production interfaces.
- [ ] Implement the minimal versioned serializer, AES-GCM cipher, and atomic SQLite store. Add `cryptography` to `requirements.txt`.
- [ ] Run `pytest -q tests/crew/test_session_credentials.py` and verify all tests pass.
- [ ] Commit `crew/session_credentials.py`, its tests, and dependency change.

### Task 2: macOS Keychain and Capability Secret

**Files:**
- Create: `crew/mac_secrets.py`
- Create: `tests/crew/test_mac_secrets.py`

**Interfaces:**
- Produces: `MacKeychainKeyProvider.get_or_create_key() -> bytes` and `load_or_create_capability(path) -> str`.
- Consumes: injected subprocess runner for Keychain operations and explicit data-directory paths.

- [ ] Write failing tests for existing/missing Keychain items, key creation, denied access, malformed keys, restrictive capability-file permissions, stable reload, and no secret text in errors or reprs.
- [ ] Run `pytest -q tests/crew/test_mac_secrets.py` and confirm expected failures.
- [ ] Implement minimal `security find-generic-password` / `add-generic-password` adapter and atomic capability creation with mode `0600`.
- [ ] Run the focused tests and verify all pass.
- [ ] Commit the adapter and tests.

### Task 3: Session Capture and Filtering

**Files:**
- Modify: `crew/browser_capture.py`
- Modify: `tests/crew/test_browser_capture.py`

**Interfaces:**
- Produces: `PlaywrightSessionCapturer.capture(timeout_seconds) -> SessionCredential | None`.
- Consumes: Playwright context cookies and approved domains `api.trycrew.com` and `app.trycrew.com`.

- [ ] Replace speculative header-capture regressions with failing tests proving exact-domain cookie filtering, exclusion of unrelated cookies/local storage, expiry preservation, timeout, and no secret-bearing repr/status output.
- [ ] Run `pytest -q tests/crew/test_browser_capture.py` and verify the new tests fail for missing session capture.
- [ ] Implement context-cookie capture after authenticated Crew API activity while retaining the old authorization capturer only for legacy compatibility.
- [ ] Run the focused tests and verify all pass.
- [ ] Commit capture changes and tests.

### Task 4: Cookie-Aware Crew Transport

**Files:**
- Create: `crew/transports.py`
- Modify: `crew/client.py`
- Modify: `tests/crew/test_client.py`
- Create: `tests/crew/test_transports.py`

**Interfaces:**
- Produces: `DirectBearerTransport.execute(...)`, `SessionCookieTransport.execute(...)`, and transport-injected `CrewClient` preserving its current public method.
- Consumes: `SessionCredential`, fixed Crew endpoint, and injected requests session.

- [ ] Write failing tests for cookie injection without header leakage, 401/403 classification, GraphQL errors, invalid JSON, read transport failure, and exactly-one mutation attempt with uncertain-write classification.
- [ ] Run focused client/transport tests and verify expected failures.
- [ ] Extract direct bearer behavior into a transport and implement cookie-aware transport without changing caller behavior.
- [ ] Run `pytest -q tests/crew/test_client.py tests/crew/test_transports.py` and verify all pass.
- [ ] Commit transport changes and tests.

### Task 5: Loopback Broker API

**Files:**
- Create: `crew/broker.py`
- Create: `tests/crew/test_broker.py`

**Interfaces:**
- Produces: `create_broker_app(config)`, `BrokerConfig`, `/health`, `/renew/start`, `/renew/status/<id>`, and `/graphql`.
- Consumes: credential store, session capturer factory, Crew transport, capability secret, and fixed endpoint.

- [ ] Write failing Flask tests for capability rejection, constant-shape unauthorized response, payload size/field validation, operation allowlist, loopback bind validation, sanitized health/status, single-flight renewal, validated-before-save behavior, and mutation flag propagation.
- [ ] Run `pytest -q tests/crew/test_broker.py` and confirm failures.
- [ ] Implement the narrow broker app and configuration with no arbitrary URL support.
- [ ] Run broker tests and verify all pass.
- [ ] Commit broker code and tests.

### Task 6: Docker-Side Broker Transport and Health

**Files:**
- Modify: `crew/transports.py`
- Modify: `crew/health.py`
- Modify: `crew/__init__.py`
- Modify: `app.py`
- Modify: `tests/crew/test_health.py`
- Modify: `tests/test_app_crew_integration.py`

**Interfaces:**
- Produces: `BrokerCrewTransport`, new health states `broker_unavailable` and `credential_locked`, and broker-aware app wiring.
- Consumes: broker base URL and capability file; preserves `crew_client.execute` for all existing application call sites.

- [ ] Write failing tests for broker request shape, response/error mapping, capability non-disclosure, health states, bearer fallback before session migration, and broker preference after session validation.
- [ ] Run focused tests and confirm expected failures.
- [ ] Implement broker transport, health mapping, and app wiring without touching money-movement call sites.
- [ ] Run focused tests and verify all pass.
- [ ] Commit integration changes and tests.

### Task 7: Mac Service and Deployment Configuration

**Files:**
- Create: `crew_broker.py`
- Create: `scripts/install_crew_broker_launchagent.sh`
- Create: `config/com.simplecrew.crew-broker.plist.template`
- Modify: `docker-compose.yml.template`
- Modify: `Dockerfile`
- Modify: `.dockerignore`
- Create: `tests/crew/test_broker_entrypoint.py`

**Interfaces:**
- Produces: Mac broker CLI with explicit loopback host/port/data paths and a LaunchAgent template.
- Consumes: Keychain, data volume, capability file, and approved broker configuration.

- [ ] Write failing tests for loopback-only CLI validation, deterministic defaults, no secret command-line arguments, and install-template rendering into a temporary directory.
- [ ] Run focused tests and confirm expected failures.
- [ ] Implement entrypoint/service templates and Docker host-gateway broker configuration. Ensure Playwright remains outside the Docker production image.
- [ ] Run focused tests plus `docker compose config` against a temporary deployment configuration.
- [ ] Commit deployment artifacts and tests.

### Task 8: UI Renewal Compatibility and Documentation

**Files:**
- Modify: `static/js/api/account.js`
- Modify: `templates/partials/views/account.html`
- Modify: `docs/REMOTE_ACCESS.md`
- Modify: `docs/project/CURRENT_STATUS.md`
- Modify: `tests/test_app_crew_integration.py`

**Interfaces:**
- Produces: existing Reconnect UI backed by broker renewal and user-facing broker/session health messages.
- Consumes: sanitized application endpoints only.

- [ ] Write failing endpoint/UI tests for `broker_unavailable`, `credential_locked`, broker renewal polling, and absence of credential fields in HTML/JSON.
- [ ] Run focused tests and verify failures.
- [ ] Update UI copy and routes to proxy renewal safely; document Mac broker installation, recovery, and backup semantics.
- [ ] Run focused tests and verify all pass.
- [ ] Update current status with branch, commits, verification, blockers, and next action; commit.

### Task 9: Verification and Read-Only Acceptance

**Files:**
- Modify only if a failing verification reveals an in-scope defect, using a new failing regression test first.

**Interfaces:**
- Consumes all prior tasks; produces verification evidence.

- [ ] Run `pytest -q tests/crew tests/test_app_crew_integration.py`.
- [ ] Run the full `pytest -q` suite and classify any unrelated pre-existing failures explicitly.
- [ ] Run `ruff check crew crew_broker.py tests/crew tests/test_app_crew_integration.py`.
- [ ] Run `pip-audit -r requirements.txt` and record findings without speculative dependency changes.
- [ ] Build the Docker image and verify Playwright/Chromium and plaintext Crew credentials are absent.
- [ ] Start the Mac broker and isolated Docker deployment against a copy of production data.
- [ ] Complete one interactive Crew login, verify `healthy`, and run read-only account/transaction synchronization.
- [ ] Inspect sanitized logs, environment, and API responses for secret leakage without printing secret values.
- [ ] Do not run a real financial mutation.
- [ ] Update `docs/project/CURRENT_STATUS.md` and commit final verification evidence.
