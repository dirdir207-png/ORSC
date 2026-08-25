# Enhanced SimpleCrew — Current Status

Last consolidated: 2026-08-25

## Canonical sources

- Repository: `dirdir207-png/SimpleCrew`
- Default branch: `main` (protected; do not work directly on it)
- Approved design: `Enhanced_SimpleCrew_Design_Spec`
- Approved implementation plan: `Enhanced_SimpleCrew_Implementation_Plan`
- Approved specifications override informal chat history when they conflict.

## Architecture and safety decisions

- Enhanced SimpleCrew runs on the always-on Mac.
- Crew GraphQL is the primary banking-data path.
- Crew credentials and bearer/session tokens remain server-side/local and must never be exposed to browser or Base44 frontend code.
- Tailscale is the intended private remote-access path.
- Existing SimpleCrew authentication/passkey protection remains in place.
- Financial mutations must never be retried automatically.
- Base44 may receive display-safe snapshots and synchronization requests, but no credential capable of moving money.

## Implementation evidence recovered from prior work

A previous coding session reported:

- Local feature commit: `32fe0b8`
- Verification: 103 tests passed
- Compilation and diff checks: clean
- `main`: untouched

That commit is not currently resolvable in GitHub, and the available local checkout contains no commits. Treat the implementation as recoverable prior work, not as published repository state, until its patch or checkout is recovered and independently verified.

The approved implementation plan covers eight TDD tasks:

1. Credential-provider boundary
2. `CrewClient`
3. Credential-health classification
4. Flask and UI wiring
5. Transfer migration
6. First safe-read migration
7. Tailscale and Mac deployment
8. Final verification gate

Reported remaining review blockers:

- A truthy non-string transfer ID may be mistaken for confirmed success.
- A `.dockerignore` is needed to prevent databases, tokens, `.env` files, caches, and Git metadata from entering image layers.

These findings must be reproduced against the recovered branch before remediation. Do not restart the full implementation from scratch unless recovery is conclusively impossible.

## Related work to retain as project context

ChatGPT chats:

- `GitHub connection check`
- `Check GitHub Access`
- `GitHub Access Watch`
- `Inspect Crew API Docs`

Codex tasks:

- `Check Crew connector health`
- `Run CrewWorkAssistantOTP setup`
- `Continue connector setup`
- `Refresh Crew token and test`
- `Install Docker and SimpleCrew`

## Current blockers

- The prior local implementation commit/patch must be recovered before engineering continues.

## Next safe actions

1. Create or open the ChatGPT Project `Enhanced SimpleCrew` and move the related chats into it.
2. Upload the approved design-spec and implementation-plan PDFs.
3. Apply the concise project instructions from `PROJECT_INSTRUCTIONS.md`.
4. Recover the checkout or patch containing local commit `32fe0b8`.
5. Reproduce the 103-test result, verify the two reported blockers, and continue through the Superpowers workflow.
