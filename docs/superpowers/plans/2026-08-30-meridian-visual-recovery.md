# Meridian Visual Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Subagent execution is unavailable in the current session. Steps use checkbox syntax for tracking.

**Goal:** Rebuild Meridian's visible product so every core workspace faithfully reflects the approved Design Atlas while preserving the existing financial behavior and safety boundaries.

**Architecture:** Keep the current Flask, Jinja, CSS, and JavaScript architecture. Establish a small shared visual primitive layer, then recompose each workspace from those primitives without changing domain services unless a UI contract is missing. Gate every workspace with same-state, same-viewport screenshots against the approved atlas.

**Tech Stack:** Flask, Jinja templates, CSS custom properties, ES modules, pytest, Playwright browser tests.

**Spec:** `docs/design-audits/2026-08-30-meridian-atlas-fidelity-audit.md`, grounded by `Meridian Project Documents/01 - Product Design Specification.md` and `Meridian Project Documents/09 - Meridian Design Atlas.html`.

## Global constraints

- Preserve all existing server-side credential and financial-mutation safety boundaries.
- Do not remove a desktop or mobile capability to achieve visual fidelity.
- Use the atlas as a requirement, not loose inspiration.
- Use real application data or explicit honest empty states; never hard-code atlas values into production UI.
- Keep light and dark themes independently designed and test both.
- Use the existing icon library or real source assets; do not use emoji, ASCII, CSS art, or handcrafted SVG placeholders.
- Maintain 44-pixel minimum interactive targets, reduced-motion support, keyboard access, focus restoration, and safe-area behavior.
- Do not modify unrelated legacy surfaces or complete Connected Billers inside this recovery unless separately approved.

---

### Task 1: Lock visual baselines and acceptance gates

**Files:**

- Create: `tests/browser/test_atlas_fidelity.py`
- Create: `tests/browser/visual_baselines/README.md`
- Modify: `tests/browser/conftest.py`
- Modify: `seed_preview.py`

**Deliverable:** Deterministic preview data and repeatable desktop/mobile captures for Today, Plan, Activity, Accounts, transaction inspector, Review, Patterns, advisor, and empty/error states.

- [ ] Add a deterministic clock and stable seeded records so screenshots do not change with the current date.
- [ ] Add capture helpers for 1440×900, 1024×768, 430×932, and 390×844.
- [ ] Save approved atlas crops and current-state baselines with clear names.
- [ ] Assert the expected workspace, theme, selected object, and data state before every screenshot.
- [ ] Add a visual-difference gate plus semantic assertions so a blank but similarly colored page cannot pass.

### Task 2: Rebuild the shell and brand frame

**Files:**

- Modify: `templates/meridian/index.html`
- Modify: `templates/meridian/partials/navigation.html`
- Modify: `static/css/meridian/tokens.css`
- Modify: `static/css/meridian/shell.css`
- Modify: `static/css/meridian/motion.css`
- Modify: `static/js/meridian/shell.js`
- Create: `static/js/meridian/theme.js`
- Test: `tests/browser/test_meridian_shell.py`
- Test: `tests/browser/test_atlas_fidelity.py`

**Deliverable:** Branded desktop rail, broad editorial canvas, optional right rail, intentional mobile top bar/dock, and a persistent light/dark preference.

- [ ] Match the atlas rail proportions, forest treatment, wordmark, active states, profile/freshness footer, and canvas spacing.
- [ ] Add command-header, surface, KPI, chip, evidence, button, and inspector primitives shared by all workspaces.
- [ ] Add an explicit theme control and persist the user's choice without flashing the wrong theme.
- [ ] Refine dark surfaces and borders so hierarchy remains visible without mechanical inversion.
- [ ] Verify keyboard navigation, active announcements, safe areas, reduced motion, and no overflow at every target viewport.

### Task 3: Recompose Today as the command center

**Files:**

- Modify: `templates/meridian/partials/today.html`
- Modify: `static/js/meridian/today.js`
- Modify: `static/css/meridian/workspaces.css`
- Modify when contract gaps exist: `meridian/services/today.py`
- Test: `tests/meridian/services/test_today.py`
- Test: `tests/browser/test_atlas_fidelity.py`

**Deliverable:** Editorial status statement, dominant safe-to-spend figure, forecast chart, Beacon change card, supporting metrics, attention queue, and advisor briefing.

- [ ] Render a useful loading, unavailable, and stale-data composition without collapsing the page.
- [ ] Add the atlas forecast chart using truthful scales, direct labels, and accessible text alternatives.
- [ ] Surface Beacon coverage, runway, anomalies, and recent changes with evidence links.
- [ ] Limit the visible action queue and route deeper review to the correct workspace.
- [ ] Match the approved mobile headline, metric card, Beacon notices, and bottom-dock composition.

### Task 4: Recompose Plan around coverage and next actions

**Files:**

- Modify: `templates/meridian/partials/plan.html`
- Modify: `static/js/meridian/plan.js`
- Modify: `static/css/meridian/plan.css`
- Test: `tests/browser/test_plan.py`
- Test: `tests/browser/test_atlas_fidelity.py`

**Deliverable:** Command header, coverage orbit, next-paycheck allocation summary, compact commitment table, allocation/timeline views, and selected-rule inspector.

- [ ] Replace the repeated full-width card stack with the atlas's summary-first hierarchy.
- [ ] Add the coverage orbit and shortfall treatment with accessible numeric alternatives.
- [ ] Make the next-paycheck schedule a first-class card and preserve all funding controls.
- [ ] Open commitment and rule details in the shared inspector on desktop and a full-height sheet on mobile.
- [ ] Integrate document discrepancies and memory effects without creating unrelated visual islands.

### Task 5: Recompose Activity and transaction intelligence

**Files:**

- Modify: `templates/meridian/partials/activity.html`
- Modify: `templates/meridian/partials/transaction-inspector.html`
- Modify: `static/js/meridian/activity.js`
- Modify: `static/js/meridian/review.js`
- Modify: `static/js/meridian/transaction-inspector.js`
- Modify: `static/css/meridian/workspaces.css`
- Modify: `static/css/meridian/inspector.css`
- Test: `tests/browser/test_activity.py`
- Test: `tests/browser/test_transaction_review.py`
- Test: `tests/browser/test_transaction_inspector.py`
- Test: `tests/browser/test_document_intelligence.py`

**Deliverable:** Concise ledger/detail split, polished Review and Patterns modes, and an evidence-rich inspector matching the atlas.

- [ ] Add the editorial command header and compact filter controls.
- [ ] Preserve selection while switching modes, filtering, or paginating.
- [ ] Make confidence, recurrence, anomalies, corrections, documents, transfers, and forecast impact visually scannable.
- [ ] Design honest missing-evidence states that do not dominate the detail surface.
- [ ] Match the approved mobile selected-transaction summary and full-detail drill-down.

### Task 6: Recompose Accounts as financial structure

**Files:**

- Modify: `templates/meridian/partials/accounts.html`
- Modify: `static/js/meridian/accounts.js`
- Modify: `static/css/meridian/workspaces.css`
- Modify when contract gaps exist: `meridian/services/accounts.py`
- Test: `tests/browser/test_accounts.py`
- Test: `tests/browser/test_responsive_parity.py`
- Test: `tests/browser/test_atlas_fidelity.py`

**Deliverable:** Net-position header, available-cash and liability summaries, account identity rows, provider-neutral grouping, and connection-health inspector.

- [ ] Add the atlas command header and connect-account action.
- [ ] Add meaningful account identity icons from the approved icon system.
- [ ] Show freshness and provenance as secondary information rather than provider-led layouts.
- [ ] Route family, cards, reimbursements, connections, credentials, assets, and contracts through coherent detail sections.
- [ ] Match the approved compact mobile account list and net-position summary.

### Task 7: Replace placeholder advisor presentation

**Files:**

- Modify: `templates/partials/advisor_fab.html`
- Modify: `static/js/ui/advisor_fab.js`
- Modify: `static/css/meridian/inspector.css`
- Test: `tests/browser/test_contextual_advisor.py`
- Test: `tests/browser/test_atlas_fidelity.py`

**Deliverable:** Branded Meridian advisor control and desktop/mobile compositions grounded in visible context and evidence.

- [ ] Replace the emoji control with approved iconography and a clear accessible label.
- [ ] Use the right rail for desktop briefings and a full-height sheet on mobile.
- [ ] Preserve context, evidence references, proposal-only actions, failure states, and conversation history.
- [ ] Verify the advisor never visually competes with primary financial actions.

### Task 8: Finish Task 26 in the recovered visual system

**Files:**

- Create: `meridian/services/memory.py`
- Modify: `meridian/services/today.py`
- Modify: `meridian/services/plan.py`
- Modify: `meridian/services/activity.py`
- Modify: `meridian/services/accounts.py`
- Modify: `meridian/api.py`
- Create: `static/js/meridian/memory.js`
- Modify: the four Meridian workspace templates as needed
- Test: `tests/meridian/services/test_memory.py`
- Test: `tests/browser/test_evidence_memory.py`

**Deliverable:** Return, warranty, renewal, maintenance, contract, and reserve attention integrated into the existing four workspaces without adding a fifth navigation item.

- [ ] Follow the original Task 26 red-green-refactor sequence.
- [ ] Present each memory item with source evidence, financial relevance, confidence, and the correct detail route.
- [ ] Preserve all read-only and proposal-only boundaries.
- [ ] Capture desktop and mobile screenshots for every workspace affected by memory.

### Task 9: Complete accessibility and interaction verification

**Files:**

- Modify: `tests/browser/test_meridian_shell.py`
- Modify: `tests/browser/test_responsive_parity.py`
- Modify: `tests/browser/test_atlas_fidelity.py`
- Create if absent: `static/js/meridian/haptics.js`

**Deliverable:** Verified keyboard, screen-size, motion, contrast, focus, and touch behavior across the reconstructed product.

- [ ] Test complete keyboard journeys through navigation, filters, inspectors, sheets, Review, funding edits, and advisor.
- [ ] Test focus restoration, announcements, error recovery, zoom/reflow, and high-contrast risks.
- [ ] Add visual alternatives for every gesture and haptic response.
- [ ] Verify all chart meanings and state colors remain understandable without color alone.

### Task 10: Run owner-facing visual acceptance

**Files:**

- Update: `docs/design-audits/2026-08-30-meridian-atlas-fidelity-audit.md`
- Update: `docs/project/CURRENT_STATUS.md`
- Save: `artifacts/design-audit-2026-08-30/final/`

**Deliverable:** A signed-off screenshot set and explicit completion record based on evidence rather than task count.

- [ ] Capture approved atlas and implementation at matching states and viewports.
- [ ] Review Today, Plan, Activity, Accounts, inspector, advisor, Review, Patterns, document evidence, and memory side by side.
- [ ] Record remaining differences as accepted, deferred, or blocking.
- [ ] Give the owner a live preview plus before-and-after screenshots at each workspace checkpoint.
- [ ] Do not call the redesign complete until the owner approves the final visual set.

## Explicitly separate follow-on work

Connected Billers remains a separate approved capability beyond the current 26-task completion state. After visual recovery and Task 26, create its own specification-to-implementation plan from the existing atlas screens for monitor, switch, pay, and optional bill-account capabilities.

