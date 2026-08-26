# Milestone 2 — Guided Crew Credential Renewal (Design)

Status: Approved direction per owner ("auto token renewal, followed by AI automation"). This document defines Milestone 2 scope and safety rules.

## Problem

When the stored Crew bearer token expires, `CredentialHealthService` reports `unauthorized` and the only recovery is a manual DevTools hunt: log into Crew, open Network tab, copy an `authorization` header, paste it into Account Settings. This is error-prone and blocks non-technical usage.

## Goal

Reduce renewal to one button and one interactive login. The user never sees, copies, or pastes the token.

## Non-goals (explicitly deferred)

- Fully unattended login automation. Crew OTP (SMS/email) exists deliberately; the user completes authentication interactively.
- Storing Crew passwords anywhere.
- Any renewal logic in Docker/cloud contexts; renewal runs on the Mac only.
- AI-triggered anything (Milestone 3).

## Mechanism

1. Connection Health reports `unauthorized` → UI offers **Reconnect Crew**.
2. Button calls `POST /api/account/crew/reconnect/start`. Server creates a single-flight renewal session and spawns a background thread that launches a local Playwright-driven Chromium window at the Crew web app.
3. The user logs in interactively (credentials + OTP happen entirely inside that local browser window).
4. The capturer listens for the first outgoing request to `api.trycrew.com` carrying an `authorization` header and captures its full value.
5. The captured value is written through the existing server-side storage path (same DB table as manual save), then a health check runs immediately.
6. UI polls session status: `waiting_for_user → captured → health: healthy` (or failure states). The token value is NEVER included in any status payload, log line, or exception text.

## Components

- `crew/renewal.py`
  - `RenewalStatus` enum: `pending`, `waiting_for_user`, `captured`, `failed`, `expired`.
  - `GuidedRenewalService`: owns session lifecycle — single-flight guard, random session ids, timeout expiry, injected collaborators:
    - `capturer_factory`: zero-arg callable returning a context-manager object exposing `.capture(timeout_seconds) -> Optional[str]`.
    - `storer(value)`: persists the credential (existing crew-config storage path).
    - `health_checker() -> CrewHealth`: re-checks after storage.
  - Status payloads are sanitized by construction: `{status, message}` plus optional sanitized `health` block after capture.
- `crew/browser_capture.py` — Playwright implementation of the capturer protocol.
  - Lazy import: if Playwright/browsers are not installed on this machine, factory raises `CapturerUnavailable` and the API returns actionable guidance instead of failing opaquely.
  - Persistent-ish ephemeral profile; window closes automatically after capture or timeout.
  - Never logs URL fragments, headers, or token material.
- Flask endpoints (`app.py`):
  - `POST /api/account/crew/reconnect/start` → `{session_id}` or guidance error; rejects concurrent sessions.
  - `GET /api/account/crew/reconnect/status/<session_id>` → sanitized status; unknown id → 404.
- UI: Reconnect button appears when health state is `unauthorized`; polls status; renders state transitions.

## Safety constraints (inherited from PROJECT_INSTRUCTIONS.md)

- Captured tokens are stored server-side only; never exposed to browser JS, logs, docs, or source control.
- Session ids are `uuid4`; status responses contain no credential material; `repr()` of any renewal object leaks nothing.
- Single renewal session at a time; hard timeout (default 300s) marks the session `expired`.
- Renewal writes go through the same validation/storage path as manual saves; no new secret-bearing tables.
- Docker image does not gain Playwright; dependency is documented as a Mac-local extra.

## Testing strategy

All service logic TDD with fake capturers/storers/checkers:

- happy path: start → waiting_for_user → captured → storer called once with captured value → health checked
- capture returns None → `failed`, storer never called
- capturer unavailable → `failed` with guidance message
- timeout → `expired`
- second `start()` while active → rejected
- unknown/expired session id status → safe 404/sanitized response
- no status payload or repr ever contains the captured token value

Browser capturer itself gets a thin integration test marked to skip unless Playwright is present; end-to-end verification is a manual gate with the real Crew login.

## Acceptance criteria

1. With an invalid stored token, clicking **Reconnect Crew** and completing login in the opened window restores `healthy` without the user handling the token.
2. No renewal code path logs or exposes credential values.
3. Only one renewal session can run at a time; abandoned sessions expire cleanly.
4. Machines without Playwright get clear guidance; Docker image size unchanged.
5. All service behavior covered by tests that never open a browser.
