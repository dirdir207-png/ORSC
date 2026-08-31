# Meridian Atlas Fidelity Audit

**Date:** 2026-08-30

**Audit mode:** Combined visual, UX, and screenshot-based accessibility review

**Grounding sources:**

- `Meridian Project Documents/01 - Product Design Specification.md`
- `Meridian Project Documents/09 - Meridian Design Atlas.html`
- `docs/superpowers/specs/2026-08-26-meridian-product-overhaul-design.md`
- `docs/superpowers/plans/2026-08-26-meridian-overhaul-implementation.md`
- Current `/meridian` implementation rendered with synthetic preview data

## Overall verdict

The current application preserves a meaningful portion of Meridian's information architecture and safety model, but it does not faithfully implement the approved visual product. The four-workspace shell exists, core data surfaces exist, and the responsive/navigation foundations are present. The visible experience is nevertheless closer to a minimally styled engineering interface than the premium Editorial Wealth product shown in the atlas.

This is a system-level fidelity failure, not a small polish gap. The visual hierarchy, page composition, content density, brand presence, primary metrics, charting, side-rail use, mobile composition, and evidence presentation all diverge materially from the approved target.

## Completion truth

The repository status does not support the claim that all 26 roadmap tasks are complete. `docs/project/CURRENT_STATUS.md` records Task 25 as complete and Task 26 as still in progress. The current code search also finds no Connected Billers frontend surface and no asset/contract memory presentation in the four workspaces.

## Evidence set

Current implementation screenshots:

- `artifacts/design-audit-2026-08-30/current/today-desktop.png`
- `artifacts/design-audit-2026-08-30/current/plan-desktop.png`
- `artifacts/design-audit-2026-08-30/current/activity-desktop.png`
- `artifacts/design-audit-2026-08-30/current/accounts-desktop.png`
- `artifacts/design-audit-2026-08-30/current/transaction-inspector-desktop.png`
- Compact-screen captures for all four workspaces in the same folder

Approved atlas screenshots:

- `artifacts/design-audit-2026-08-30/atlas/today-desktop.png`
- `artifacts/design-audit-2026-08-30/atlas/plan-desktop.png`
- `artifacts/design-audit-2026-08-30/atlas/activity-desktop.png`
- `artifacts/design-audit-2026-08-30/atlas/accounts-desktop.png`
- Matching mobile references in the same folder

## Step-by-step audit

### 1. Application shell — poor

The implementation has four primary destinations and the correct desktop/mobile navigation switch. It does not match the atlas's branded 150-pixel forest rail, editorial canvas, or always-useful right rail. The 72-pixel icon-only rail technically satisfies the implementation roadmap but loses the atlas's premium brand presence and contextual profile/freshness summary.

The main canvas is visually under-composed. Large regions are empty while content remains narrow and utilitarian. The floating advisor control is an emoji-based bubble, which conflicts with the premium visual language and the Product Design asset rules.

### 2. Today — critical

The atlas centers Today on a clear editorial statement, a dominant safe-to-spend figure, a forecast chart, a Beacon insight card, three supporting financial metrics, and an advisor briefing rail. The current page shows an unavailable value, one cash line, and an empty upcoming-events state. Even allowing for incomplete synthetic data, the composition has no premium hierarchy or meaningful visual fallback.

The page does not visibly expose Beacon coverage, runway, anomalies, recent changes, or an action queue as required by the approved product specification.

### 3. Plan — poor

The current Plan workspace exposes commitments, totals, an allocation bar, upcoming contributions, and funding controls. This is the strongest functional workspace. It still diverges from the atlas in its command header, coverage orbit, next-paycheck card, compact commitment table, selected-rule inspector, and editorial pacing.

The current page becomes a long vertical stack of nearly identical cards. That makes the app feel operational rather than premium and forces users to scan repeated borders instead of following a deliberate financial story.

### 4. Activity — poor

Timeline, Review, and Patterns modes exist, as do account filtering and transaction selection. The visible timeline is excessively long and dense, with weak date hierarchy and no default split between ledger and selected detail. The atlas intentionally pairs a concise ledger with a transaction summary and an explanation rail.

The current transaction inspector is structurally capable, but its typography and data blocks remain utilitarian. Empty evidence and classification states dominate the visual result instead of gracefully explaining what is known, unknown, and actionable.

### 5. Accounts — critical

The current Accounts screen is a flat categorized list with a connection row. The atlas requires an editorial command header, available-cash and liability summaries, account identity tiles, subordinate provider provenance, a clear net position, and a connection-health inspector.

The present surface does not communicate financial structure at a glance and does not feel like a unified premium system.

### 6. Mobile parity — needs redesign

The bottom dock, safe-area handling, and touch-target foundations exist. The compact-screen composition largely collapses desktop content rather than reproducing the intentional phone layouts in the atlas. The approved mobile designs use stronger headlines, sticky summaries, compact cards, and deliberate drill-down patterns.

Exact 390-by-844 capture could not be forced through the in-app browser in this run; compact-screen evidence was captured at the available narrow viewport. Responsive behavior still requires automated 390-by-844 and 430-by-932 verification during implementation.

### 7. Design system — partial

The token file contains the intended warm neutrals, serif/sans split, restrained state colors, spacing, radii, motion timing, and independent dark palette. The component implementation does not consistently turn those tokens into the richer atlas primitives: command headers, surfaces, KPI grids, chart frames, evidence blocks, or inspector compositions.

The dark theme is technically coherent but visually too close in value across canvas, surfaces, borders, and text. This flattens hierarchy and makes full-page screenshots appear nearly black. The atlas is primarily demonstrated in a warm light treatment; the current browser default obscures the intended brand.

### 8. Evidence, memory, and Connected Billers — incomplete

Document evidence hooks exist in the transaction inspector and Plan discrepancy area. Asset/contract memory is not yet composed into Today, Plan, Activity, and Accounts. Connected Billers has an approved atlas design but no implementation surface. These features therefore cannot be considered visually faithful or complete.

## Why this happened

The implementation plan's browser tests mostly validate structure: elements exist, workspaces are reachable, URLs update, touch targets are large enough, overflow is absent, and controls remain accessible. Those checks are useful but do not compare rendered output against the atlas.

There is no enforced same-viewport reference comparison, no screenshot-diff threshold, no design-token-to-component acceptance matrix, and no owner checkpoint after each major workspace. Functional completion was allowed to stand in for design completion.

## Accessibility evidence limits

The current code includes semantic regions, keyboard focus management, focus restoration, minimum target-size tests, reduced-motion handling, and contrast tests for a token pair. Screenshots alone cannot verify complete keyboard order, screen-reader announcements, zoom behavior, high-contrast mode, error recovery, or the accessibility of every dynamic state. Those require interactive testing after the visual reconstruction.

## Highest-impact corrections

1. Rebuild the shared shell and component grammar directly from the atlas before adjusting individual screens.
2. Restore the warm Editorial Wealth light experience as a first-class, user-selectable theme and refine dark mode independently.
3. Recompose Today, Plan, Activity, and Accounts from their approved atlas layouts using live data and honest empty states.
4. Replace the emoji advisor control and other placeholder-like visual treatments with consistent iconography and branded surfaces.
5. Add same-viewport atlas comparisons and owner screenshot checkpoints as release gates.
6. Complete Task 26 and explicitly scope Connected Billers as unfinished rather than implying all roadmap work is complete.

