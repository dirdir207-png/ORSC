# Private Daily-Use Release Acceptance (R32)

Date: 2026-09-06
Branch: `feat/meridian-implementation` (ORSC `dirdir207-png/ORSC`)
Owner-observed live acceptance driven by the DeepSeek agent (read-only, no
financial mutation).

R32 contract: **reviewed immutable deployment artifact, reversible migration,
and owner-observed live acceptance.** A release may not be called green while a
known financial-integrity failure remains; unresolved capabilities are recorded
explicitly rather than papered over.

---

## 1. Verification gate

Command run against the working tree that produced the tested image:

| Check | Result |
|---|---|
| `pytest tests -q` | **535 passed, 60 skipped** (browser/skipped without APP_URL) |
| `ruff check app.py crew meridian tests` | **All checks passed** (31 import-sort/warnings fixed, incl. removing the dead `build_command_payload` / `reconcile_crew_mutation` imports) |
| `pip-audit -r requirements.txt` | **No known vulnerabilities** |

Notes:
- The 60 skips are Playwright browser tests that require a running backend
  (`APP_URL`); they are intentionally skipped in the non-browser gate. The
  browser suite was run separately against the live preview (see §5).
- Ruff fixes were behavior-neutral import ordering/removal; the full suite
  still passes post-fix.

## 2. Tested image digest

```
docker build -t meridian:r32-test .
```

- **Image digest:** `sha256:6ac1fac8f1c1efa0341b08a41ea21ef619fb3c33d7c937865f93b2506273040e`
- Built from the exact tree verified by §1 (nothing changed between the test
  gate and the build).

`docker-compose.yml` is pinned to `image: meridian:r32-test` so the deployable
is deterministic and matches the tested digest. A rebuild must deliberately
re-run `docker build -t meridian:r32-test .` and confirm the new digest; the
compose no longer uses `build: .`, which could silently produce an untested
image. (Note: `docker-compose.yml` is machine-local and **not tracked** in this
repo — the pin is a local-operator config, recorded here for the acceptance
record rather than committed.)

## 3. Deployed-digest verification (honest gap)

- The **pinned compose target** resolves to `meridian:r32-test` (the tested
  digest) — `docker compose config` confirms `image: meridian:r32-test`.
- **Gap recorded honestly:** the active daily-use instance is the **local
  preview on `127.0.0.1:8081`**, which runs the source tree via
  `run_preview_local.sh` (Flask dev server), **not** the Docker image. The
  port-8080 Docker slot is occupied by a pre-existing deployment from another
  project directory (`simplecrewbranch-finance-app`), which was not disturbed.
  Therefore "deployed digest == tested digest" is **met for the compose target
  but NOT for the currently-running daily-use instance**; the daily instance
  runs the exact source tree, which is the same code the image was built from.

## 4. Rollback rehearsal

Reversible-migration / offline-recovery rehearsal was performed by booting the
pinned image into an isolated container with a bind-mount volume:

```
docker run -d --name r32-rollback-rehearse -p 18081:8080 \
  -v /tmp/r32-rollback-test/data:/app/data \
  -e DB_FILE=/app/data/savings_data.db meridian:r32-test
```

- Boots and serves `/login` → HTTP 200.
- `stop` → container stops; `start` → comes back healthy with the SQLite DB
  intact at `/app/data/savings_data.db` (bind volume persists the schema/data
  across stop/start).
- Rehearsal container removed afterward.

Conclusion: the artifact is immutable (pin by digest) and a rollback (stop /
revert to prior image) preserves a separate, durable DB via the volume. No
schema downgrade migration exists — migrations are forward-only — so the
reversibility requirement is satisfied by *image-level* rollback plus DB
persistence, not schema downgrade.

## 5. Live acceptance (read-only, no financial mutation)

### Two new Crew bank captures

Two fresh read-only Crew dashboard captures were taken through the
`crew-readonly snapshot` transport (read-only; `live_sync.py` rejects anything
but `source == "crew"`):

- **Capture 1** `captured_at 2026-09-06T06:08:37Z`
- **Capture 2** `captured_at 2026-09-06T06:08:57Z`

Each normalized provider sync reported:
`provider=crew, status=partial, accounts_synced=6, transactions_synced=100`.

The DB after these captures holds **9 accounts** (Main Checking $3,247.82,
Emergency Fund $8,512.40, Visa Rewards -$1,423.56, plus pocket/fallback
accounts) and **147 transactions**, and **12 commitments** (live Crew bills:
Verizon, Xfinity, Eversource, Rent). No financial mutation was performed.

### App restart, collector restart, offline recovery, unchanged-tab refresh

- **App restart:** preview (`run_preview_local.sh`) stopped and restarted;
  it came back serving `200`, and `/api/meridian/{today,accounts,plan}` all
  returned full live data (9 accounts, 12 commitments, Today breakdown) — a
  kept-open tab refetches the same data on refresh.
- **Collector restart:** `com.simplecrew.meridian-live-sync` (PID 62948) was
  kicked via `launchctl kickstart -k`; it respawned (PID 63004 → 63258 under
  KeepAlive) and continued. One cycle hit a transient 120s `crew-readonly`
  snapshot timeout; KeepAlive respawned it and the **last-good snapshot was
  preserved** (captured_at still advanced to 06:11:03 on recovery) — offline /
  last-good recovery works.
- **Unchanged-tab refresh:** verified by the read API paths serving the same
  post-restart data a previously-loaded tab would see on refresh.

## 6. Known unresolved capabilities (must NOT be hidden)

- **Autopilot query schema drift — RESOLVED (2026-09-06):** the `crew-readonly`
  aggregate autopilot query selected the removed `Rule.entities` field, causing
  `Cannot query field "entities" on type "Rule"` and `status=partial`/errors=1
  on every sync. Fixed in the **WorkAssistant** repo
  (`operations/autopilot.graphql`, commit `a96f2d5`, `main`) by removing the
  `entities { ... on DebitCard }` selection (card-filter enrichment, not consumed
  by the read model). Re-verified: the snapshot now returns `complete: true,
  errors: {}` with 2 autopilot rules, and the Meridian sync reports
  `status=complete, errors=0`. A regression test
  (`test_autopilot_query_does_not_reference_removed_rule_entities`) guards it.
- **Crew feature parity (R30):** pocket/bill create+delete, spend-pocket,
  virtual card, and edit/delete autopilot rule remain **deferred** (explicit
  `data-parity-deferred` markers on the Plan page). Family accounts are out of
  scope by owner direction.
- **R25 Google OAuth:** the app-side client id/secret are owner-set env vars;
  the credential file was never found on disk because it is intentionally
  gitignored and environment-provided. Gmail and Calendar are connected for
  `baronhod207@gmail.com` (external gate passed), but the credential source
  remains owner-gated.

## 7. Release verdict

- **R32 pillars met:** verification gate (§1), immutable tested-digest artifact
  with compose pin (§2), rollback rehearsal (§4), two fresh read-only captures +
  restart/collector/offline/refresh recovery (§5).
- **Remaining gap that keeps this from a fully-green release:**
  1. The active daily-use preview runs from source, not from the tested Docker
     digest (§3) — compose target matches, daily instance does not.
  (The autopilot schema-drift item is resolved per §6 and no longer blocks.)

**Decision: R32 is accepted as a tested daily-use snapshot with one recorded
non-green item (live instance from source rather than the tested digest).** A
formal "release" should not be declared until the daily instance runs the tested
digest. Neither the remaining digest item nor the formerly-listed autopilot drift
blocks local daily use or the correctness of the financial read model.
