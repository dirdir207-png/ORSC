# Task 26 — Meridian Evidence Memory Across Workspaces + Asset/Contract Management — Design

**Date:** 2026-08-31
**Status:** Approved design (brainstorming). Written spec pending review, then `writing-plans`.
**Build:** separate OpenRouter build on `dirdir207-png/ORSC`, branch `feat/meridian-implementation` (commit `0fff5ea` base).

## 1. Context

Task 26 ("Integrate evidence memory into Today, Plan, Activity, and Accounts", roadmap
`Meridian Project Documents/02 - Implementation Roadmap.md:1099`) is the last roadmap task:
asset, contract, warranty, obligation, and evidence memory must appear inside the four
existing workspaces without a fifth navigation item.

A read-only architecture review (2026-08-31) established the true state:

- `meridian/assets.py`, `meridian/contracts.py`, `meridian/evidence.py`,
  `meridian/services/memory.py` (`build_memory`) exist, are unit-tested, and are committed.
- **Missing**: any `/api/meridian/memory/*` route (frontend `static/js/meridian/memory.js`
  fetches `/api/meridian/memory/${workspace}` → 404 at runtime); wiring of memory into the
  four workspace services; a non-empty Activity composition (`"activity": []` placeholder);
  a shape match between `build_memory` (returns `{today, plan, activity, accounts}`) and
  `memory.js` (expects `data.categories[]`).
- `MERIDIAN_EVIDENCE_BLOB_STORE_FACTORY` is never configured in `app.py` →
  `/api/meridian/evidence/<id>/content` returns 503 (blob store exists in `meridian/storage.py`).
- No way to create or manage assets/contracts outside of direct DB writes.

## 2. Goal and Non-Goals

**Goal:** Complete Task 26 functionally: compose asset/contract/evidence memory into the
four workspaces via per-workspace API endpoints, make evidence content resolve end-to-end,
and let the owner manage assets/contracts through the existing propose→approve→execute
pipeline — all on the current visual system.

**Non-goals (deferred, separate tracks):**
- Meridian visual recovery (atlas fidelity rehash) — its own plan; this design targets the
  current visual system and uses honest empty states.
- Payday & Funding plan (2026-08-31) — untouched.
- Connected Billers — separate future program.
- Any change to money-movement, commitment, or funding-rule gating (stays pipeline-gated as today).

## 3. Approved Scope Decisions

1. **Functional Task 26 now; visual recovery separate.**
2. **Evidence content end-to-end**: configure the blob store so evidence links resolve and
   revoked/expired evidence degrades honestly.
3. **Minimal owner management UI**: create/edit/delete assets & contracts (with
   warranties/obligations) from Accounts detail sections.
4. **Pipeline write path**: all asset/contract management writes flow through
   propose→approve→execute (six new action types). No direct writes.
5. **Per-workspace memory API**: `GET /api/meridian/memory/{workspace}`.

## 4. Architecture & Components

### 4.1 Memory composition (refactor `meridian/services/memory.py`)

Replace the single `build_memory` with a per-workspace composer:

```
build_memory(db_path, workspace, as_of=None) -> MemoryWorkspace
MemoryWorkspace = { "workspace": str, "items": [MemoryItem, ...] }
```

`MemoryItem` (frozen, JSON-safe):
- `id` — stable dedup key, e.g. `"asset:12:return_deadline"`, `"contract:7:obligation_due:3"`.
- `kind` — one of `return_deadline | maintenance_due | replacement_reserve |
  warranty_expiration | obligation_due | cancellation_deadline | renewal | escalation_review`.
- `urgency` — `overdue | upcoming | future` (day-of-month heuristic retained from the
  current `_compose_today`; past/absent dates handled per §9).
- `title`, `why_it_matters` — human strings (keep existing wording, fix the
  `escalation_percent`→`"amount"` field semantics: amount is always a money figure or null;
  escalation uses `escalation_percent` in a separate field).
- `amount` — Decimal-compatible money or null.
- `due_on` — ISO date or null.
- `confidence` — 0..1 (from the record).
- `evidence` — list of `{id, span, kind, confidence}` (resolved from `evidence_items` +
  `evidence_links` + the denormalized `evidence_id`/`evidence_span` columns; revoked/expired
  items omitted unless marked inaccessible).

Composition rules per workspace (§7). The four existing workspace services
(`services/today.py`, `services/plan.py`, `services/activity.py`, `services/accounts.py`)
remain the primary data sources; memory regions are additive and fetched through the new
endpoints. Activity memory must not duplicate transactions (§7.3).

### 4.2 Memory API (extend `meridian/api.py`)

Four new `@login_required` routes wrapped in the existing `_safe_read` 503 envelope:

- `GET /api/meridian/memory/today`
- `GET /api/meridian/memory/plan`
- `GET /api/meridian/memory/activity`
- `GET /api/meridian/memory/accounts`

Each returns `MemoryWorkspace`. Unknown workspace → 404 (or 400; pick 404, consistent with
`get_connection_detail`). Empty workspaces return `{"workspace": ..., "items": []}` — never
an error, so the frontend renders honest empty states.

### 4.3 Pipeline management (extend `crew/actions.py` + `crew/executors.py` + `app.py`)

New allowed action types (added to the ActionStore allowlist):

- `create_asset`, `update_asset`, `delete_asset`
- `create_contract`, `update_contract`, `delete_contract`

Proposal payloads carry the complete record: `name, category, purchased_on, purchase_price,
return_until, maintenance_interval_days, replacement_reserve, evidence_id, evidence_span,
confidence` for assets; `provider, terms, start_on, expires_on, auto_renews,
escalation_percent, deductible, evidence_id, evidence_span, confidence` for contracts;
nested `warranties` / `obligations` arrays. `update_*` proposals accept partial fields plus
an explicit `change_reason`. `delete_*` proposals carry the record id and an explicit
`change_reason`.

Executors (registered in the existing `action_executors` registry) call
`AssetRepository`/`ContractRepository` (save/update/delete, with warranties/obligations);
verifiers read back and confirm the write. The existing `asset_correction_proposals`
mechanism folds into `update_asset` proposals (its `proposed` rows become proposals;
approval applies them; the table remains for provenance).

Delete semantics: delete the record and **unlink** evidence (`evidence_links` rows removed
for the target; `evidence_items` never deleted — matches the test-verified invariant that
evidence deletion cannot corrupt financial history).

Approval UI: the existing pending-approval surface renders these kinds alongside money
proposals, with kind-specific labels and diff-style change summary for updates.

### 4.4 Evidence wiring (modify `app.py` + `seed_preview.py`)

- Set `MERIDIAN_EVIDENCE_BLOB_STORE_FACTORY` in `app.py` to build `EncryptedBlobStore`
  (`meridian/storage.py`) with a key provider derived from the app's existing `SECRET_KEY`
  (HKDF-SHA256, domain-separated label `meridian.evidence.v1`) — no new env var, no key in
  git/logs, reuses the existing key-management model.
- `/api/meridian/evidence/<id>/content` then resolves: 404 unknown, 410 revoked/deleted,
  200 with stored content-type.
- `seed_preview.py` gains assets, warranties, contracts, obligations, evidence blobs +
  links so the memory regions render real data in preview (and honest empty states when absent).

### 4.5 Frontend (modify `static/js/meridian/memory.js`, templates, `workspaces.css`)

- Rework `memory.js` to the per-workspace contract (`data.items[]`; drop the
  `data.categories[]` expectation) and fetch the four endpoints.
- Render: Today attention list (urgency-ordered, evidence links); Plan reserve/obligation
  cards with an explicit "Explore scenario" action (never silent mutation); Activity
  lifecycle events clearly separated from transactions; Accounts asset/contract sections
  with detail views (warranties, obligations, evidence, confidence).
- Accounts gains management forms (create/edit/delete asset & contract) that post pipeline
  proposals, and the approval surface renders memory proposal kinds.
- Editorial primitives only: existing tokens/components, 44px targets, keyboard access,
  both themes, no fifth nav item.

## 5. API Contract

| Endpoint | Method | Auth | Success | Errors |
|---|---|---|---|---|
| `/api/meridian/memory/{workspace}` | GET | login | 200 `MemoryWorkspace` | 503 envelope; 404 unknown workspace |
| `/api/meridian/evidence/{id}/content` | GET | login | 200 body | 503; 404 unknown; 410 revoked/deleted |
| `/api/meridian/assets` | POST | login | 202 proposal created | 503; 409/400 pipeline errors |
| `/api/meridian/assets/{id}` | PATCH | login | 202 proposal created | 503; 404; 409/400 |
| `/api/meridian/assets/{id}` | DELETE | login | 202 proposal created | 503; 404; 409/400 |
| `/api/meridian/contracts` | POST | login | 202 proposal created | 503; 404; 409/400 |
| `/api/meridian/contracts/{id}` | PATCH | login | 202 proposal created | 503; 404; 409/400 |
| `/api/meridian/contracts/{id}` | DELETE | login | 202 proposal created | 503; 404; 409/400 |

Management endpoints return the created **proposal** (id + state `proposed`) — approval is
a separate existing call. No secret ever appears in any payload.

## 6. Behavioral Contract Per Workspace

1. **Today**: return/cancellation/renewal/warranty/maintenance attention items ordered by
   urgency, each with financial relevance (`why_it_matters`) and evidence links.
2. **Plan**: replacement reserves, deductibles, renewal, and escalation effects surface as
   explicit, user-initiated scenarios/inputs — never silent mutations.
3. **Activity**: linked receipts/documents and lifecycle events appear without duplicating
   transactions (memory items reference, never re-list, transactions).
4. **Accounts**: assets and contracts live beneath the existing Accounts workspace with
   detail views; management forms live here.
5. **Evidence**: authenticated `/api/meridian/evidence/<id>/content`; revoked/expired
   evidence degrades honestly (hidden or labeled).
6. **Safety**: preserve source spans and confidence; insurance/lease/tax/medical material
   yields quoted facts and deadlines, never professional determinations (existing
   `advisory_boundary` preserved).
7. **UX**: Editorial Wealth primitives; no fifth navigation item; no separate filing cabinet.
8. **API**: per-workspace composed payloads; display-safe failures.

## 7. Data Model & Audit

- **No new migration required**: 013 (`assets`, `warranties`, `contracts`, `obligations`,
  `asset_correction_proposals`) and 011 (`evidence_items`, `evidence_links`) already exist
  and are applied. (If the plan review uncovers a need — e.g., an audit table — a forward-only
  idempotent migration `015_*` may be added; not expected.)
- **Audit**: every management change is recorded by the action pipeline (durable
  `action_requests` history with approval/execution timestamps) — no parallel audit table.
- **Confidence**: owner-created/edited records carry `confidence=1.0` with
  `evidence_span="owner:managed"`; machine-derived values keep their stored confidence.
- **Evidence integrity**: deletes unlink, never remove `evidence_items`; revocation stays
  soft; retention sweep unchanged.

## 8. Error Handling & Empty States

- All new reads wrapped in `_safe_read` (503 envelope; exceptions never leak internals).
- Empty memory workspaces return `items: []` and the frontend renders honest empty states.
- Evidence content: 404 unknown id; 410 revoked/deleted; frontend renders a labeled
  unavailable state (no broken links).
- Pipeline: 409 illegal transition, 400 unknown type/invalid payload, 401 bad local key —
  consistent with existing action endpoints.

## 9. Composer Edge Rules

- Past due dates → `overdue`; missing/absent due dates → **excluded from Today attention**
  (matches the current `_compose_today` behavior) and rendered as **"unscheduled"** in Plan
  reserves and Accounts detail (a reserve without a date is still a plan item, just not an
  attention item).
- Dedup by stable `id` across event derivation and refresh cycles.
- Confidence < 0.7 (consistent with the review-queue threshold): the item renders **with a
  "review" hint**; it is never suppressed from memory surfaces.
- Activity composer must never emit a transaction twice; memory items carry
  `reference_transaction_id` when linked instead of duplicating.

## 10. Testing Plan (TDD Order)

1. **RED** — extend/repair existing memory tests to the per-workspace contract
   (`tests/meridian/services/test_memory.py`, `tests/browser/test_evidence_memory.py`).
2. Composer refactor → GREEN (ordering, past/absent dates, dedup, confidence/provenance,
   evidence deletion/unlink, sensitive-kind wording).
3. API routes + tests (auth, shape, empty, 503, 404) → GREEN.
4. Pipeline: 6 action types — propose/approve/execute/verify, illegal transitions, TTL,
   delete-unlinks-evidence → GREEN (`tests/crew/test_actions.py`, `test_executors.py`, new
   `tests/meridian/test_asset_contract_actions.py`).
5. Evidence wiring + seed + e2e (factory configured, content resolves, revocation) → GREEN.
6. Frontend: memory.js rework, region rendering, management forms, approval UI; browser
   tests for each workspace region + management + approval flow.
7. Full gates (below), `CURRENT_STATUS.md` update, commit
   `feat: connect Meridian evidence memory across workspaces` on `feat/meridian-implementation`.

## 11. Gates & Definition of Done

- `ruff check app.py crew meridian tests` clean.
- `python3 -m pytest tests -q` green (no new skips; record counts in `CURRENT_STATUS.md`).
- `python3 -m pytest tests/meridian -q` green.
- Browser suite against preview (`APP_URL`): device matrix 390×844, 430×932, 768×1024,
  1024×768, 1440×900 for the four memory regions.
- `pip-audit -r requirements.txt` clean; `docker build -t meridian:task26 .` succeeds.
- No real financial mutation exercised; no secret in any payload, log, fixture, or commit.
- Docs (`CURRENT_STATUS.md`) reconciled with actual test counts and this design.
- Stop before interactive Crew login / owner-only live acceptance (owner gate remains).

## 12. Deferred (explicitly out of scope)

- Visual recovery / atlas fidelity (its plan, Task 8, will revisit memory presentation).
- Payday & Funding plan; Connected Billers; evidence ingestion from documents/connectors
  (document intelligence can later populate assets/contracts through the same pipeline).
