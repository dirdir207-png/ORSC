# Meridian Settings, Connections, and Payday Funding Design

**Date:** 2026-08-31  
**Status:** Approved visual direction; awaiting written-spec review  
**Visual target:** Hybrid of the approved Editorial Control Room framing and Connection Ledger interaction model, generated in the current Product Design review.

## Purpose

Meridian needs a coherent home for account connections, read-only evidence sources, payday timing, funding schedules, permissions, retention, and personal preferences. These capabilities must be discoverable without turning Settings into a fifth financial workspace or making the primary navigation feel like an administration console.

The design keeps Today, Plan, Activity, and Accounts as Meridian's four financial workspaces. Settings is a profile-level utility. Accounts and Plan retain contextual entry points into the relevant Settings sections.

## Product principles

1. Connections are user-controlled, individually authorized, and individually revocable.
2. Gmail and Calendar remain read-only evidence sources. Meridian may use their evidence to enrich forecasts, explain changes, create scenarios, and draft approval-required proposals. It never sends or deletes email, modifies calendars, or treats an unconfirmed calendar event as a known expense.
3. Financial rules and mutations remain proposal-only. Funding-rule changes and transfers require an explanation and explicit owner approval.
4. Provider names describe provenance, not product architecture. The experience remains Meridian-led and provider-neutral.
5. Connection state must be honest. Pending, stale, degraded, revoked, unsupported, and uncertain states must never appear healthy.
6. Desktop and mobile use the same information model but different compositions.

## Information architecture

### Primary navigation

The forest rail and mobile dock keep four primary destinations:

- Today
- Plan
- Activity
- Accounts

Settings appears beneath the Personal identity and freshness summary on desktop. On mobile, Settings is reached from the top identity utility rather than becoming a fifth equal dock destination.

### Settings sections

The initial Settings scope contains:

- **Connections:** financial providers, Gmail evidence, Calendar context, connection freshness, permissions, retention, and revocation.
- **Payday & Funding:** payday recognition, funding source, cadence, rule summary, next proposed run, and entry into the existing funding-rule editor.
- **Profile:** owner identity and household context already supported by the product.
- **Preferences:** appearance, locale, and time-zone presentation.
- **Notifications:** proposal, stale-data, review, and connection-health preferences.
- **Security & Data:** session protection, evidence retention, export, and deletion controls.

Connections and Payday & Funding ship first. The remaining destinations may initially route to existing surfaces or honest scoped empty states; they must not advertise unimplemented controls.

### Contextual entry points

- Accounts includes **Connect account** and connection-health actions that open Settings > Connections with the relevant source selected.
- Plan includes a **Payday funding schedule** summary and edit action that opens Settings > Payday & Funding.
- Today surfaces only actionable exceptions, such as a stale source or a funding schedule requiring review.
- Activity records authorization, revocation, proposal, approval, and confirmed financial outcomes without exposing credentials.

## Connections experience

### Desktop

Desktop uses the selected hybrid composition:

1. The primary Meridian rail remains 150 pixels wide.
2. A compact secondary Settings navigation sits beside it.
3. The main canvas leads with the editorial statement, “Your financial picture, connected.”
4. A single **Add connection** action anchors the page.
5. Sources appear in a grouped ledger, not a card grid:
   - Money: Crew and other financial providers.
   - Evidence: Gmail and future document sources.
   - Time: Google Calendar and future schedule sources.
6. Each row shows source identity, sanitized account identity when relevant, connection state, read-only status, freshness, and a concise “Meridian uses this for” explanation.
7. Selecting a source opens the persistent right inspector.

The inspector contains:

- source identity and status;
- authorized scope in plain language;
- what Meridian captures and what it cannot do;
- last successful activity and freshness;
- retention policy where applicable;
- explanation of forecast and proposal use;
- recent permission activity;
- revoke or reconnect action;
- a compact safeguards summary.

Revocation is visually distinct but not alarmist. It requires confirmation because it stops future capture and may reduce forecast confidence. Revocation never deletes financial records or audit history implicitly; retention controls describe their separate effect.

### Mobile

Mobile is an intentional 390-by-844 composition, not a collapsed desktop table.

- The identity bar contains the Settings utility.
- The headline and Add connection action remain visible without consuming the full first viewport.
- Connection groups use touch-friendly rows with source, state, freshness, use summary, and chevron.
- Selecting a source opens a full-height detail sheet.
- The detail sheet uses ordered sections for permissions, captured evidence, retention, proposal use, activity, and revoke/reconnect.
- The four-item financial dock remains unchanged.
- Payday & Funding is available as a clear text action after the source ledger and through Settings navigation.

All controls meet the existing 44-pixel minimum target and preserve focus restoration, safe areas, reduced motion, and keyboard access.

## Add-connection flow

Add connection opens a source chooser grouped by purpose rather than partner popularity:

- Financial accounts
- Email and documents
- Calendar and time

Before authorization, Meridian shows:

- the exact read-only scope;
- examples of information used;
- explicit actions Meridian cannot perform;
- retention defaults;
- how evidence may affect forecasts and proposals;
- how to revoke access.

OAuth or partner authorization occurs in the provider-hosted interface. Provider tokens remain server-side and are never returned to browser code, fixtures, logs, or model prompts. A connection is not shown as active until Meridian verifies the granted scope and completes an initial read.

Authorization outcomes:

- **Connected:** scope verified and initial read complete.
- **Pending:** authorization returned but verification or initial read is incomplete.
- **Limited:** provider granted fewer capabilities than requested.
- **Failed:** authorization or verification failed, with a safe recovery action.
- **Revoked:** access ended and no future polling occurs.

## Payday & Funding experience

The page explains the user's income rhythm and how Meridian will propose allocations.

### Summary

- recognized or manually selected payday cadence;
- next expected payday;
- funding source account;
- amount or percentage expected to be allocated;
- number of active funding rules;
- next proposed funding run;
- whether the schedule is current, needs review, or lacks sufficient evidence.

### Editing

Desktop places rule controls beside a live projection. Mobile presents the same schema as ordered steps with a persistent preview summary.

Supported behaviors remain those in the approved product specification:

- fixed amount per paycheck;
- percentage of paycheck;
- calendar cadence;
- even funding by due date;
- priority waterfall;
- contribution limits;
- one-time override, pause, and skip;
- variable-bill buffers.

Saving a rule change creates a proposal. A paycheck trigger may create a scheduled funding proposal. Neither action executes a transfer. Approval, single-attempt execution, and post-action verification remain separate stages.

## Data and service boundaries

### Existing foundations to reuse

- `provider_connections` and account freshness remain the financial-source truth.
- `ReadOnlyMailConnector` retains the Gmail read-only allowlist and lacks send, delete, or modify methods.
- `ReadOnlyCalendarConnector` retains the minimum-field, bounded time window and lacks create, update, or delete methods.
- Evidence retention and revocation continue through the evidence/context repositories.
- Funding rules continue through `FundingRuleRepository`, `project_funding`, and the existing proposal pipeline.

### New read models

Implementation should add narrow Meridian service modules rather than new business logic in `app.py`:

- `meridian/services/settings.py` builds sanitized Settings navigation and preference state.
- `meridian/services/connections.py` combines provider freshness with evidence-connection metadata without exposing external identifiers or tokens.
- `meridian/services/payday.py` presents recognized payday evidence and existing funding-rule summaries.

Recommended API contracts:

- `GET /api/meridian/settings/connections`
- `GET /api/meridian/settings/connections/<public_id>`
- `POST /api/meridian/settings/connections/<kind>/authorize`
- `POST /api/meridian/settings/connections/<public_id>/revoke`
- `GET /api/meridian/settings/payday`

The authorize endpoint returns only a provider-hosted authorization URL or local handoff state. The browser never receives provider credentials. Revocation requires CSRF/session protection and an explicit owner action. Existing funding-rule proposal endpoints remain the mutation boundary for schedule changes.

## State and error handling

- Loading preserves the page structure with reserved rows and truthful status labels.
- A failed single source does not collapse the entire ledger.
- Stale sources show the last trustworthy update and the affected forecast scope.
- Offline state keeps cached metadata visible but clearly marks it as not current.
- Authorization cancellation returns to the prior screen without creating a connection.
- Partial OAuth scope becomes Limited, never Connected.
- Revocation failure leaves the prior state visible with a retryable explanation.
- Uncertain financial writes are never retried automatically and remain pending verification.
- Empty states lead with one useful action and never invent account or evidence data.

## Visual system

The approved hybrid target extends Meridian's Editorial Wealth language:

- forest primary rail;
- warm ivory canvas and softly white surfaces;
- Iowan/Baskerville-style serif display headings with system sans-serif UI text;
- hierarchy created primarily through spacing, alignment, typography, and dividers;
- subdued green wash for selected ledger rows;
- minimal shadows and no decorative gradients;
- real provider marks or the established icon library, never emoji or improvised SVG art;
- no nested-card dashboard treatment.

Dark mode must be designed independently and retain visible separation among canvas, ledger rows, inspector, borders, and selected states.

## Accessibility and privacy

- Connection state is communicated by text and icon, never color alone.
- Source logos have accessible names while redundant decorative marks are hidden.
- Table semantics on desktop become list semantics on mobile without losing field labels.
- Inspector and mobile sheets trap focus only while modal, restore focus to the opener, and close with Escape.
- Destructive and privacy-impacting actions receive explicit confirmation and consequences.
- Provider identifiers, tokens, raw message bodies, and sensitive evidence never appear in DOM data attributes, logs, screenshots, or test fixtures.

## Testing and acceptance

### Service and API tests

- sanitized connection read models expose no credential or external-token material;
- read-only scopes remain exact allowlists;
- Gmail has no send/delete/modify capability;
- Calendar has no create/update/delete capability;
- partial authorization never reports Connected;
- independent revocation stops future capture;
- retention changes preserve required audit and financial records;
- payday summaries remain deterministic across time zones and DST;
- schedule changes create proposals rather than transfers.

### Browser tests

- Settings is reachable as a utility while the four financial workspaces remain unchanged;
- contextual entry points preserve selected source or payday state;
- desktop ledger and inspector work with keyboard and pointer input;
- mobile rows open full-height sheets and restore focus;
- 390×844, 430×932, 1024×768, and 1440×900 have no horizontal overflow;
- stale, pending, limited, failed, revoked, empty, and offline states remain composed;
- light and dark themes pass contrast and hierarchy checks;
- no provider tokens or raw evidence leak into the DOM or console.

### Visual acceptance

Capture the selected hybrid mockup and implementation at matching desktop state, plus the approved connections-led mobile composition. Compare desktop and mobile in the same visual input, fix all P0–P2 differences, and require owner approval before declaring the Settings work complete.

## Scope boundaries

This design does not add email sending, calendar mutation, automatic transfer execution, credential storage in the browser, or Connected Biller switching/payment. It creates the product surfaces and narrow contracts needed to manage existing financial and evidence connections and the already-approved funding-rule system safely.
