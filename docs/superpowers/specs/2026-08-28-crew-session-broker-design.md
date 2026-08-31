# Crew Session Broker Design

**Status:** Approved direction on 2026-08-28

## Problem

SimpleCrew currently authenticates Crew GraphQL requests with a stored bearer token. Crew's current web application authenticates GraphQL through browser-managed session state and configures Apollo with `credentials: "include"`. The existing guided-renewal helper therefore completes login successfully but cannot recover a bearer credential that restores `CrewClient` health.

SimpleCrew runs in Docker, while interactive Crew authentication must remain on the local Mac. Copying browser cookies into Docker would broaden secret exposure and make cookie rotation difficult to control.

## Goal

Restore reliable Crew connectivity through a Mac-local session broker that owns interactive authentication and plaintext Crew session material. The Docker application sends Crew operations to the broker over a loopback-only authenticated channel. The browser UI, Docker environment, logs, API responses, documentation examples, and source control never receive Crew credentials.

## Non-goals

- Fully unattended Crew login or bypassing OTP, passkey, CAPTCHA, or other interactive authentication.
- Storing Crew passwords, OTPs, passkeys, or browser profiles.
- General-purpose HTTP proxying.
- Automatic retry of financial mutations.
- Replacing the existing Tailscale access model or exposing the broker through Tailscale.
- Migrating unrelated SimpleCrew providers or Meridian data models.

## Architecture

The system has three trust zones:

1. **Browser:** The user completes Crew authentication in an ephemeral Playwright browser on the Mac. The browser is never controlled by Docker and never returns credentials to browser-side SimpleCrew JavaScript.
2. **Mac credential broker:** A small local process captures the authenticated Crew session, encrypts persisted session data, decrypts it only when making Crew requests, and exposes a narrow Crew-operation API on loopback.
3. **Docker application:** SimpleCrew submits an allowlisted GraphQL operation name, query, variables, and mutation flag to the broker. It receives only the normalized Crew response or a classified error.

The broker binds to `127.0.0.1` only. Docker reaches it through the host gateway configured for the local deployment. Every request carries a separate broker capability secret. The capability secret authenticates SimpleCrew to the broker; it is not a Crew credential and cannot be used against Crew.

## Credential Model and Storage

### Versioned records

Credential persistence becomes versioned rather than bearer-specific. A record contains:

- credential kind: `bearer_v1` or `session_v1`;
- encrypted payload for `session_v1`;
- AES-GCM nonce;
- schema version;
- creation and update timestamps;
- optional non-secret expiry metadata when Crew supplies it.

Legacy bearer records remain readable during migration. When a healthy `session_v1` record exists, the broker prefers it. Bearer support is retained as a compatibility fallback until a later, separately approved removal.

### Encryption

Session data is serialized in a canonical, versioned structure and encrypted with AES-256-GCM. The ciphertext and nonce are stored in the existing SQLite data volume. The encryption key is a randomly generated 256-bit key stored in macOS Keychain under a service/account name scoped to SimpleCrew and the local installation.

The encryption key is never stored in SQLite, Docker configuration, environment files, logs, or source control. Losing the Keychain item invalidates the encrypted session and requires interactive renewal; it does not fall back to plaintext storage.

### Captured session scope

The broker persists only cookies required for Crew API authentication, restricted to approved Crew domains and paths. It does not persist browsing history, local storage, unrelated cookies, passwords, OTPs, or the complete Playwright profile. Cookie values are never included in `repr`, exception messages, status objects, or test fixtures.

## Mac Credential Broker

### Responsibilities

The broker:

- loads or creates the Keychain encryption key;
- reads and writes encrypted credential records in SQLite;
- opens an ephemeral Playwright context for interactive renewal;
- captures the minimal authenticated Crew cookie set after login;
- validates the captured session with a read-only health query before committing it;
- executes allowlisted Crew GraphQL requests with a cookie-aware `requests.Session`;
- classifies authentication, transport, API, and uncertain-write failures;
- keeps plaintext session material in process memory only as long as needed.

### Narrow API

The broker exposes only:

- `GET /health`: broker availability and credential classification without secret material;
- `POST /renew/start`: begin a single interactive renewal;
- `GET /renew/status/<session_id>`: sanitized renewal status;
- `POST /graphql`: execute a Crew operation through the broker.

The broker does not accept arbitrary destinations. The Crew endpoint is fixed in broker configuration. Operation payloads are size-limited and validated. Responses are normalized JSON and never echo request headers or stored credential fields.

### Broker authentication

A random broker capability secret is generated locally and stored with restrictive filesystem permissions in the mounted SimpleCrew data directory so the Docker application and Mac broker can both read it. Broker requests use a constant-time comparison. Missing or invalid capability credentials return a generic unauthorized response and are not logged verbatim.

The broker listens only on loopback. Startup fails closed if configured to bind to a non-loopback address.

## Docker Integration

`CrewClient` keeps its public `execute(operation_name, query, variables, is_mutation)` contract. Its transport becomes selectable:

- `BrokerCrewTransport` is preferred when the broker is configured and healthy.
- `DirectBearerTransport` preserves existing bearer behavior during migration and tests.

The Docker application never receives decrypted session cookies. It sends the mutation flag to the broker so transport ambiguity is classified correctly. A failed or timed-out mutation produces `CrewUncertainWriteError`; neither Docker nor the broker automatically retries it.

Deployment adds the broker URL and capability-file path, not Crew secrets, to Docker configuration. The broker is started on macOS as a supervised local service. Container health remains separate from broker/Crew health.

## Renewal Flow

1. SimpleCrew health reports that Crew authentication needs attention.
2. The user selects **Reconnect Crew**.
3. Docker requests renewal from the loopback broker.
4. The broker creates a single-flight renewal session and opens an ephemeral Playwright window.
5. The user completes Crew authentication interactively.
6. The broker collects the minimal approved Crew session-cookie set from the Playwright context.
7. The broker runs the read-only `CrewConnectionHealth` query with that session.
8. On success, the broker encrypts and atomically persists `session_v1`, then discards the plaintext capture.
9. SimpleCrew polls sanitized status and refreshes connection health.

Failed validation never replaces the last known credential. Timeout, window closure, missing cookies, Keychain failure, or database failure ends the renewal with a sanitized failure message.

## Health and Error Classification

The application exposes these user-facing states:

- `healthy`: broker and Crew session are valid;
- `unauthorized`: Crew rejected or expired the stored session;
- `broker_unavailable`: the Mac broker cannot be reached or is not running;
- `unreachable`: the broker is available but cannot reach Crew;
- `api_error`: Crew returned an unexpected GraphQL or response error;
- `credential_locked`: encrypted session data exists but Keychain access/decryption failed.

No state includes endpoints, cookies, tokens, capability secrets, raw Crew errors that may contain sensitive material, or stack traces.

## Migration

Migration is additive and reversible:

1. Add the new credential table/fields without deleting `crew_config.bearer_token`.
2. Deploy the broker and broker-aware transport while retaining direct bearer support.
3. Complete one interactive renewal and store `session_v1`.
4. Prefer the validated session broker on subsequent requests.
5. Retain the legacy bearer value until a separate cleanup is approved; do not log, export, or rewrite it during migration.

If the broker is absent before session migration, existing bearer behavior remains unchanged. If a session record exists but the broker is unavailable, the system reports `broker_unavailable`; it does not silently copy or decrypt cookies inside Docker.

## Security Constraints

- Crew session cookies, bearer tokens, OTPs, passwords, and Keychain keys remain Mac-local and server-side.
- The broker cannot bind beyond loopback and is never exposed through public ingress or Tailscale Funnel.
- The Docker application never receives plaintext session cookies.
- The SimpleCrew browser never receives any Crew credential material.
- Logs use operation names, timing, status class, and request identifiers only.
- Financial mutations are never automatically retried.
- An uncertain mutation response always requires state reconciliation before another attempt.
- Test fixtures use obvious synthetic values and never read production Keychain or database records.

## Testing Strategy

All implementation follows test-first development.

### Unit tests

- AES-GCM round trip, nonce uniqueness, tamper rejection, wrong-key rejection, and no plaintext persistence.
- Versioned credential serialization and legacy bearer compatibility.
- Keychain adapter success, missing item, denied access, and command failure using an injected command boundary.
- Cookie filtering by exact approved domain/path and exclusion of unrelated browser state.
- Broker capability validation and loopback-only binding enforcement.
- Health-state mapping and sanitized errors.
- Mutation timeouts produce `CrewUncertainWriteError` and exactly one outbound attempt.

### Integration tests

- Broker with a temporary SQLite database and fake Crew server validates, encrypts, reloads, and uses a session.
- Docker-side transport communicates with a local test broker without observing cookies.
- Legacy direct bearer transport continues to pass existing client tests.
- Renewal status payloads contain only allowlisted fields.

### Manual acceptance gate

1. Start the Mac broker and Docker application against a backup/copy of production data.
2. Invalidate or isolate the legacy bearer credential without deleting the original.
3. Select **Reconnect Crew** and complete one interactive Crew login.
4. Confirm the renewal reports `healthy` without displaying or copying credentials.
5. Run read-only account and transaction synchronization.
6. Confirm logs, Docker environment, browser responses, and status payloads contain no Crew secret material.
7. Do not exercise a real financial mutation as part of the acceptance gate.

## Operational Recovery

- If the broker is stopped, restart the supervised Mac service; no credential migration occurs.
- If Keychain access fails, report `credential_locked` and preserve ciphertext unchanged.
- If encrypted data is corrupt or the Keychain key is lost, require interactive renewal and replace the record only after successful health validation.
- Backups may contain ciphertext but not the Keychain key. Restoring to a different Mac therefore requires a new interactive Crew login.

## Acceptance Criteria

1. One interactive Crew login restores `healthy` using session-cookie authentication.
2. Docker and browser code never receive plaintext Crew cookies.
3. Session data at rest is AES-256-GCM ciphertext whose key exists only in macOS Keychain.
4. The broker rejects non-loopback binding and unauthenticated requests.
5. Read-only Crew operations work through the broker with normalized error classification.
6. Financial mutations remain single-attempt and uncertain outcomes require reconciliation.
7. Existing bearer installations continue to function until session migration succeeds.
8. Automated tests never contact Crew or access production secrets.
