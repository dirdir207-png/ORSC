# Meridian Visual Recovery — Owner Acceptance Record

**Date:** 2026-09-02
**Branch:** `feat/meridian-implementation` (tip `94cfb2d`)
**Preview:** http://127.0.0.1:8081 (owner / meridian-owner-2026) — live Crew data auto-syncing every 15s
**Design Atlas target:** `Meridian Project Documents/09 - Meridian Design Atlas.html` (Editorial-Wealth)
**Fidelity gate:** `tests/browser/test_atlas_fidelity.py` — 8/8 passed (desktop 1440 + mobile-s 390, 4 workspaces)

## What was accepted

All four core workspaces match the atlas composition, hierarchy, typography,
spacing, rail treatment, dark-mode, and mobile collapse. Live data renders
through the recovered visual system (no hardcoded atlas sample values; honest
empty/stale states per the plan).

### Today
- Editorial command header (serif headline + subline + Ask Meridian)
- Safe-to-spend dominant figure + forecast with truthful scales/labels
- Beacon change card + evidence button
- Support metrics grid (coming in / committed / runway) with live values
- Right-rail Advisor / Morning brief
- Clean mobile collapse + bottom dock

### Plan
- "Every dollar has a next job." summary-first header
- Coverage orbit (75%) + shortfall projection
- Next-paycheck / funding-schedule card
- Compact commitment table (Commitment | Funded | Next) + footer
- Selected-rule inspector (desktop) + funding controls preserved
- Allocation bar, next-30-days, document discrepancies, memory regions

### Activity
- "One financial timeline." command header + compact filters
- Segmented Timeline / Review / Patterns modes (selection preserved)
- Date-grouped ledger with clean merchant labels (live: Cumberland Farms, Apple - PayPal, CVS, Walmart, Shell …)
- Evidence/confidence scannable; load-more pagination; mobile drill-down

### Accounts
- "Structure without provider clutter." header + Connect account
- Net-position cards (available cash / liabilities) with live figures
- Provider-neutral identity rows (icons, secondary source marks)
- Connection-health rail with current status + **Refresh now** trigger
- Assets & Contracts (memory management) + mobile compact list

## Accepted / deferred differences (honest record)

| Item | Classification | Notes |
|---|---|---|
| Live data values differ from atlas sample numbers | **Accepted** | Atlas sample figures are illustrative; product uses live data |
| "Safe to spend unavailable" / "Commitments not yet in normalized graph" | **Accepted** | Honest state per plan; commitments feed not yet mapped to live graph |
| Plan commitments show $0 funded for seeded commitments | **Deferred** | Requires wiring snapshot `expenses.bills` + `autopilot.rules` → commitments/funding; separate focused task |
| Old Playwright full-suite asyncio-loop isolation | **Known (pre-existing)** | Tests pass individually; combined runs hit pytest-asyncio loop conflict — not a product defect |
| CrewWorkAssistant is the live source | **Accepted** | Uses Crew-supported mobile/API auth (JWT + Stytch in Keychain); no browser-cookie anti-fraud loop. Mac session broker = fallback |
| Base44 / SimpleFin / LunchFlow / Splitwise | **Out** | Not part of the live bank-data path (older iteration / not bank connections) |

## Live-data findings
- Live provider: `meridian/providers/crewwork.py` (CrewWorkAssistant snapshot adapter)
- Sync every 15s via `MeridianRefreshService`; on-demand `GET /api/meridian/sync` + in-app Refresh now
- Verified: 6 accounts, 86 transactions, `status=complete`, `errors=0`; freshness "Updated … just now"

## Status
Owner-facing acceptance reviewed. Visual set approved on the live-data preview.
Deferred item (Plan funded-linkage wiring) is tracked for a focused follow-up.

## Task 9 (a11y) completion note — 2026-09-05 (post-acceptance)

Verified accessibility/interaction status (evidence-based, not task-count):

| Area | Status | Evidence |
|---|---|---|
| Keyboard journeys (nav/filters/inspectors/sheets/Review/funding/advisor) | ✅ covered | `tests/browser/test_meridian_shell.py` — keyboard workspace change + focus/announcement; modal-sheet inert + focus restore |
| Focus restoration + announcements | ✅ covered | same shell tests |
| Gesture alternatives | ✅ **added** | `static/js/meridian/haptics.js` — visible "Close" affordance for any sheet missing one; wired into `index.html`; test `tests/meridian/test_haptics_js.py` |
| Motion/contrast risk | ✅ reviewed | Editorial-Wealth tokens (motion/contrast in tokens.css); fidelity gate 8/8 |
| Chart meanings without color | ⚠️ confirmed pattern | state colors + labels; documented in fidelity audit |

Known pre-existing limitation (NOT a product bug): full-suite Playwright runs hang on
"Playwright Sync API inside the asyncio loop" (state-isolation); tests pass
individually — recorded in the plan notes.
