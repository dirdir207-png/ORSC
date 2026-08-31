# Meridian — Codex CLI Completion Handoff

**Consolidated:** 2026-08-30  
**Current checkout:** `ox-alpha/meridian-overhaul` at `a092c4a`  
**Primary implementation branch:** `feat/meridian-implementation` at `49b65f1`  
**Purpose:** finish Meridian without redoing completed slices, preserve financial-safety boundaries, and coordinate independent agents in parallel.

---

## 1. Start here

The previous status material became stale while implementation continued. Git history and the current tree now show:

- Tasks 1–12 are present in `feat/meridian-implementation`.
- The Crew Session Broker is merged into the Meridian baseline.
- `ox-alpha/meridian-overhaul` is 18 commits ahead of `feat/meridian-implementation` and contains Tasks 13–25.
- Task 26 has failing-test scaffolding in the working tree but no implementation files yet.
- Remaining current-program work is **Task 26, release verification, documentation reconciliation, and owner-only live acceptance**.
- The product spec also describes **Connected Billers** as a later final-priority slice, but the 26-task roadmap does not implement it. Treat it as a separate future program unless the owner explicitly expands scope.

Do not restart at Task 13. Unchecked boxes in the historical roadmap are requirements, not current status.

---

## 2. Non-negotiable rules

1. Work on a feature branch or isolated worktree; never work directly on `main`.
2. Preserve unrelated dirty files. Never stage `cookies.txt`, preview scripts, databases, secrets, or user-owned artifacts.
3. Crew credentials, cookies, OTPs, provider tokens, capability values, and encryption keys stay server-side or in approved local secure storage. They never enter browser payloads, AI prompts, logs, fixtures, docs, or source control.
4. Never automatically retry a financial mutation. An uncertain outcome remains `uncertain_write` until reconciled.
5. Models explain; deterministic services calculate balances, forecasts, classifications, and proposal amounts.
6. Creating Commitments, changing rules, switching billers, or moving money requires an explained proposal and explicit owner approval.
7. Migrations remain non-destructive, versioned, idempotent, resumable, and provenance-preserving.
8. Every behavioral change starts with a failing test. Three failed fix attempts trigger architectural review.
9. Do not perform a real financial mutation during testing or acceptance.
10. Stop before interactive Crew login or another owner-only approval and report the exact next action.

---

## 3. Complete source map

### Program bundle

| Source | Use |
|---|---|
| `Meridian Project Documents/README.md` | Program bundle index. |
| `Meridian Project Documents/01 - Product Design Specification.md` | Highest product authority: architecture, UX, safety, evidence graph, Connected Billers, acceptance criteria. |
| `Meridian Project Documents/02 - Implementation Roadmap.md` | Original Tasks 1–26 and slice gates; use requirements, not checkbox status. |
| `Meridian Project Documents/03 - Model and Token Strategy.md` | Risk-based agent routing and quality gates. |
| `Meridian Project Documents/04 - Project Memory.md` | Binding principles and decisions; engineering status stops after Slice 2 and is stale. |
| `Meridian Project Documents/05 - IP and Commercialization Brief.md` | Preserve provenance, human authorship evidence, and disclosure discipline. |
| `Meridian Project Documents/06 - Task 1 Engineering Report.md` | Historical production/CI/Docker/browser evidence. |
| `Meridian Project Documents/07 - Task 2 Engineering Report.md` | Historical atomic-execution and concurrency evidence. |
| `Meridian Project Documents/08 - Task 3 Engineering Report.md` | Historical migration, freshness, provenance, and recovery evidence. |
| `Meridian Project Documents/09 - Meridian Design Atlas.html` | Visual reference for four workspaces, Advisor, Review, Documents, and Connected Billers. |

The paired PDFs in `Meridian Project Documents/` and `output/pdf/` mirror Markdown sources. Use Markdown for implementation and PDFs only for presentation/layout checks.

### Working specifications and operations

| Source | Use |
|---|---|
| `docs/superpowers/specs/2026-08-26-meridian-product-overhaul-design.md` | Canonical working copy of the approved product spec. |
| `docs/superpowers/plans/2026-08-26-meridian-overhaul-implementation.md` | Canonical working plan; Task 26 is active. |
| `docs/superpowers/plans/2026-08-26-meridian-model-and-token-strategy.md` | Sol safety/release review, Terra implementation, Luna bounded inventory/tests when available. |
| `docs/project/PROJECT_INSTRUCTIONS.md` | Branch, safety, TDD, review, and session-close rules. |
| `docs/project/CURRENT_STATUS.md` | Status ledger; correct it from actual evidence after Task 26. |
| `docs/MERIDIAN_MIGRATION.md` | Upgrade, data audit, redirects, and rollback. |
| `docs/REMOTE_ACCESS.md` | Private Tailscale access and credential renewal. |
| `README.md` | Environment/setup context; feature list is partly pre-Meridian. |
| `docs/ASSISTANT.md` | Local assistant and proposal-only safety behavior. |

### Crew and automation history

| Source | Use |
|---|---|
| `docs/designs/2026-08-25-guided-credential-renewal.md` | Original renewal design; broker design supersedes conflicts. |
| `docs/designs/2026-08-25-action-pipeline.md` | Approval-gated action lifecycle. |
| `docs/designs/2026-08-25-action-proposer.md` | Proposers create inert actions only. |
| `docs/designs/2026-08-25-ai-advisor.md` | Original advisor design; Meridian evidence-bound advisor is current. |
| `docs/superpowers/specs/2026-08-28-crew-session-broker-design.md` | Current broker architecture/security authority. |
| `docs/superpowers/plans/2026-08-28-crew-session-broker.md` | Broker implementation and acceptance plan. |
| `docs/project/CREW_SESSION_BROKER_CLI_HANDOFF.md` | Historical handoff; code-remains list is stale, safety/owner acceptance guidance remains useful. |

Also inspect `.github/workflows/meridian-quality.yml`, `.github/workflows/docker-image.yml`, `Dockerfile`, `docker-compose.yml`, `docker-compose.yml.template`, `.dockerignore`, `requirements.txt`, `requirements-dev.txt`, and `ruff.toml` before the release gate.

---

## 4. Repository truth on 2026-08-30

### Branches

- Current checkout: `ox-alpha/meridian-overhaul` at `a092c4a`.
- `feat/meridian-implementation` is an ancestor; current branch is `0 behind / 18 ahead`.
- `main` is at `4110288` and remains protected.
- `.worktrees/meridian` exists. Do not edit the same files from two worktrees concurrently.

### Dirty tree at handoff creation

```text
 M docs/project/CURRENT_STATUS.md
?? cookies.txt
?? docs/project/CODEX_CLI_HANDOFF.md
?? run_preview.py
?? seed_preview.py
?? tests/browser/test_evidence_memory.py
?? tests/meridian/services/test_memory.py
```

- The two memory tests are Task 26 RED scaffolding.
- `CURRENT_STATUS.md` incorrectly listed Tasks 13–25 as pending before this handoff refresh.
- `cookies.txt` is sensitive: do not read it into model context, stage it, log it, or commit it.
- Treat preview scripts as user-owned unless instructed otherwise.
- The tree contains 365 Python test functions, including the untracked Task 26 tests. Rerun verification; do not reuse historical counts as current evidence.

---

## 5. Completed implementation evidence

| Task | Commit evidence | Main implementation |
|---|---|---|
| 13 Provider adapters/reconciliation | `726e00e`, hardened by `658306e`, `09b2bde`, `f924342`, `9b9940c` | `meridian/providers/`, `meridian/reconcile.py`, `meridian/sync.py`, reimbursement audit |
| 14 Deterministic classification | `d36b882` | `meridian/classify.py`, migration 007, classification history |
| 15 AI classification | `84de028` | `meridian/ai/classifier.py`, migration 008, structured/failure-safe integration |
| 16 Review and Patterns | `ea5f8b7` | review API/repository/UI, migration 009, browser tests |
| 17 Explainable scenarios | `062e2a7` | `meridian/beacon.py`, `meridian/scenarios.py`, Today/Plan integration |
| 18 Evidence-bound advisor | `ba5ad41` | `meridian/ai/advisor.py`, contextual API/UI |
| 19 Accounts/parity | `54e8974` | Accounts service/UI and responsive tests |
| 20 Legacy consolidation | `a81dc89` | redirects/removal and migration runbook |
| 21 Evidence storage | `cd091c8` | `meridian/evidence.py`, `meridian/storage.py`, migration 011 |
| 22 Email/document safety | `81e8b5c` | email connector, document safety/extraction |
| 23 Document reconciliation | `7fa4340` | reconciliation service and evidence UI/API |
| 24 Life Context | `6272630` | calendar connector, context repository, migration 012 |
| 25 Asset/Contract Memory | `a092c4a` | assets/contracts repositories, migration 013, boundary tests |

Tasks 1–12 and the Crew Session Broker exist in the baseline branch and are supported by the engineering reports and broker documents.

---

## 6. Remaining implementation — Task 26

### Goal

Integrate asset, contract, warranty, obligation, and evidence memory into Today, Plan, Activity, and Accounts without adding a fifth primary navigation item.

### Existing RED scaffolding

- `tests/meridian/services/test_memory.py`
- `tests/browser/test_evidence_memory.py`

The tests require `meridian.services.memory.build_memory`, Today attention with `why_it_matters` and `evidence_url`, Plan reserves, Accounts asset/contract structure, `static/js/meridian/memory.js`, four workspace regions, exactly four navigation destinations, and mobile-safe integration.

### Files

Create:

- `meridian/services/memory.py`
- `static/js/meridian/memory.js`

Modify only as needed:

- `meridian/services/today.py`
- `meridian/services/plan.py`
- `meridian/services/activity.py`
- `meridian/services/accounts.py`
- `meridian/api.py`
- `templates/meridian/index.html`
- relevant workspace partials and `static/css/meridian/workspaces.css`
- Task 26 tests

### Behavioral contract

1. **Today:** upcoming return, cancellation, renewal, warranty, and maintenance attention ordered by urgency, with financial relevance and evidence links.
2. **Plan:** replacement reserves, deductibles, renewal, and escalation effects appear as explicit scenarios/inputs, never silent mutations.
3. **Activity:** linked receipts/documents and lifecycle events do not duplicate transactions.
4. **Accounts:** assets and contracts appear beneath the existing Accounts workspace.
5. **Evidence:** use authenticated `/api/meridian/evidence/<id>/content`; revoked/expired evidence degrades honestly.
6. **Safety:** preserve source spans and confidence. Insurance, lease, tax, and medical material yields quoted facts/deadlines, not professional determinations.
7. **UX:** reuse Editorial Wealth primitives, inspector patterns, and mobile behavior. No fifth navigation item or separate filing cabinet.
8. **API:** prefer one composed memory payload or additive stable fields on current workspace payloads; failures remain display-safe.

### TDD cycle

1. Review and preserve the intent of the two untracked tests.
2. Run focused tests and record RED from missing memory service/client.
3. Add tests for deadline ordering, past/absent dates, evidence deletion, provenance/confidence, and duplicate suppression.
4. Implement the smallest coherent service and API composition.
5. Add four semantic workspace regions and client rendering.
6. Run focused unit/API/browser tests.
7. Run Meridian tests, then full tests and Ruff.
8. Review 390×844, 430×932, 768×1024, 1024×768, and 1440×900.
9. Commit only Task 26 files as `feat: connect Meridian evidence memory across workspaces`.

---

## 7. Parallel agent execution plan

Use `superpowers:subagent-driven-development` or equivalent. Agents need disjoint write scopes. If routing is unavailable, execute these lanes sequentially and state that parallel review did not occur.

### Wave A — parallel implementation

#### Agent A1 — Memory domain service

**Write scope:** `meridian/services/memory.py`, `tests/meridian/services/test_memory.py`.

Implement deterministic memory composition, deadline ordering, reserve effects, evidence links, provenance/confidence, and edge tests. Do not edit API/UI files.

#### Agent A2 — API/workspace composition

**Write scope:** `meridian/api.py`, existing four service modules, and related API/service tests except `test_memory.py`.

Expose A1 through existing workspace contracts with display-safe failures and no circular imports. Do not edit templates/CSS/JS.

#### Agent A3 — Frontend/responsive integration

**Write scope:** `static/js/meridian/memory.js`, `templates/meridian/index.html`, relevant partials, `static/css/meridian/workspaces.css`, `tests/browser/test_evidence_memory.py`.

Render memory in four workspaces, preserve exactly four navigation destinations, and implement accessible loading/empty/error/populated states. Do not edit Python.

#### Agent A4 — Documentation reconciliation

**Write scope:** `docs/project/CURRENT_STATUS.md`, `Meridian Project Documents/04 - Project Memory.md`, and evidence-based corrections to this handoff.

Update from Git/test evidence without claiming unrun gates. Keep historical reports historical. Do not edit production code.

### Wave B — parallel review after integration

- **B1 Financial/privacy safety:** secrets, write capabilities, proposal boundaries, evidence revocation, advisory boundary, deterministic money, provenance.
- **B2 API/data integrity:** stable JSON, duplicate suppression, ordering, absent dates, database isolation, migrations 001–013.
- **B3 Accessibility/responsive:** four-workspace navigation, keyboard, labels, focus, reduced motion, 44px targets, 200% zoom, safe areas, device matrix.
- **B4 Release evidence:** focused/full tests, Ruff, dependency audit, migration reruns, Docker build, browser suite, secret scan; record exact results.

### Integration order

1. Integrate A1.
2. Integrate A2 against A1's final interface.
3. Integrate A3 against the final API.
4. Run focused Task 26 tests.
5. Integrate A4 from actual evidence.
6. Run Wave B reviews in parallel.
7. Return findings to the owning Wave A agent; do not commission a broad rewrite.
8. Rerun the complete gate after fixes.

---

## 8. Final automated release gate

```bash
ruff check .
pytest -q
pytest -q tests/meridian
pytest -q tests/browser
pip-audit -r requirements.txt
docker build -t meridian:release .
```

Also verify:

- migrations 001–013 apply and rerun on a fresh database and sanitized production-data copy;
- transfers, card payments, refunds, and reimbursements are not double-counted;
- classifications retain assignment, confidence, explanation, and correction path;
- AI failure leaves deterministic sync healthy;
- evidence revocation/deletion does not corrupt financial history;
- email/calendar connectors are read-only and independently revocable;
- asset/contract facts retain source spans and confidence;
- legacy redirects and rollback docs match behavior;
- Docker excludes Playwright/Chromium, databases, `.env`, cookies, capability files, Keychain material, and plaintext credentials;
- desktop/mobile visual and accessibility matrices pass;
- no real financial mutation occurs.

Do not continue if the gate is red. Record unrelated pre-existing failures separately.

---

## 9. Owner-only acceptance

Codex CLI stops before these steps:

1. Stop app/broker and back up SQLite plus `-wal`/`-shm` companions.
2. Start the Mac broker and isolated Docker deployment against a production-data copy.
3. Complete one interactive Crew login without exposing credentials.
4. Confirm broker health is `healthy`.
5. Run read-only account/transaction sync.
6. Compare balances/totals and inspect transfers, card payments, refunds, reimbursements, Commitments, forecasts, evidence, assets, and contracts.
7. Inspect sanitized logs, environment, browser payloads, and APIs for secret leakage.
8. Do not run a real financial mutation.

---

## 10. Separate future program — Connected Billers

The product spec and Design Atlas define staged monitoring, payment-method switching, regulated-partner payment, and optional partner-backed bill accounts. This is not decomposed in Tasks 1–26. Before implementation, create a separate approved design and plan covering credentials, legal/regulatory boundaries, partner integration, mutation idempotency, and uncertain outcomes.

---

## 11. Completion definition

The current program is complete when Task 26 is implemented/reviewed, automated gates pass with recorded evidence, documentation accurately reflects Tasks 13–26, owner read-only acceptance passes on a production-data copy, no secret or real mutation is exposed, and the owner reviews the final branch before merge/deployment.

At every session end, update `docs/project/CURRENT_STATUS.md` with branch, commit IDs, exact verification results, blockers, and next owner action.
