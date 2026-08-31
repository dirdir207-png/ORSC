# Meridian Payday and Funding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a trustworthy Payday & Funding Settings surface that explains recognized income rhythm, previews existing funding rules, and creates approval-gated schedule proposals.

**Architecture:** Build a deterministic payday read model from normalized income transactions and existing funding rules, expose it through the Meridian blueprint, and add a Settings section that reuses the current proposal-only funding endpoint. Recognition never mutates rules; saving changes creates a proposal and never executes a transfer.

**Tech Stack:** Python, Flask, existing funding engine and repositories, Jinja, ES modules, CSS, pytest, Playwright.

**Spec:** `docs/superpowers/specs/2026-08-31-meridian-settings-connections-design.md`

## Global Constraints

- Payday recognition is evidence, not financial truth; users can correct it.
- Calendar events alone never create income or expense amounts.
- Funding-rule changes create proposals and never transfer money.
- Financial writes execute once only after explicit approval and are never retried automatically when uncertain.
- Desktop uses controls beside a live preview; mobile uses ordered steps and a persistent preview summary.
- Dates and cadence calculations remain deterministic across time zones and DST.

---

### Task 1: Build deterministic payday recognition

**Files:**
- Create: `meridian/payday.py`
- Create: `tests/meridian/test_payday.py`

**Interfaces:**
- Consumes: normalized positive income transactions with `occurred_at`, `amount`, `account_id`, and classification.
- Produces: `PaydayPattern(cadence, next_date, typical_amount, confidence, evidence_ids)` and `recognize_payday(transactions, *, as_of: date) -> PaydayPattern | None`.

- [ ] **Step 1: Write failing table-driven recognition tests**

```python
@pytest.mark.parametrize(
    ("dates", "cadence", "next_date"),
    [
        (["2026-07-10", "2026-07-24", "2026-08-07", "2026-08-21"], "biweekly", date(2026, 9, 4)),
        (["2026-06-30", "2026-07-31", "2026-08-31"], "monthly", date(2026, 9, 30)),
    ],
)
def test_recognize_payday_uses_literal_date_sequences(dates, cadence, next_date):
    pattern = recognize_payday(income_transactions(dates), as_of=date(2026, 8, 31))
    assert pattern.cadence == cadence
    assert pattern.next_date == next_date
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `pytest tests/meridian/test_payday.py -q`  
Expected: FAIL because `meridian.payday` does not exist.

- [ ] **Step 3: Implement conservative recognition**

Recognize only monthly, semimonthly, biweekly, and weekly patterns with at least three intervals. Use median interval and median amount, lower confidence for stale or irregular evidence, and return `None` rather than inventing a cadence.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `pytest tests/meridian/test_payday.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add meridian/payday.py tests/meridian/test_payday.py
git commit -m "feat: recognize payday cadence"
```

### Task 2: Build the Payday & Funding read model and API

**Files:**
- Create: `meridian/services/payday.py`
- Create: `tests/meridian/services/test_payday.py`
- Modify: `meridian/api.py`
- Modify: `tests/meridian/test_api.py`

**Interfaces:**
- Consumes: `recognize_payday`, `FundingRuleRepository.list_all()`, `CommitmentRepository.list_active()`, and `project_funding`.
- Produces: `build_payday_settings(graph, commitments, rules, *, as_of: date) -> dict[str, object]` and `GET /api/meridian/settings/payday?as_of=YYYY-MM-DD`.

- [ ] **Step 1: Write failing service and API tests**

```python
def test_payday_settings_explain_next_proposal_without_executing(graph, commitments, rules):
    payload = build_payday_settings(graph, commitments, rules, as_of=date(2026, 8, 31))
    assert payload["pattern"]["cadence"] == "biweekly"
    assert payload["next_run"]["date"] == "2026-09-04"
    assert payload["next_run"]["kind"] == "proposal"
    assert "transfer_id" not in json.dumps(payload)
```

- [ ] **Step 2: Run focused tests and verify RED**

Run: `pytest tests/meridian/services/test_payday.py tests/meridian/test_api.py -q`  
Expected: FAIL because the service and route are absent.

- [ ] **Step 3: Implement the read model and validated date route**

Return recognized/manual status, cadence, next payday, typical amount, confidence, evidence count, funding source, active rule summaries, next projected contributions, shortfall, and freshness. Reuse the existing ISO-date validation pattern from `/plan`.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `pytest tests/meridian/services/test_payday.py tests/meridian/test_api.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add meridian/services/payday.py tests/meridian/services/test_payday.py meridian/api.py tests/meridian/test_api.py
git commit -m "feat: expose payday funding summary"
```

### Task 3: Build desktop and mobile Payday & Funding settings

**Files:**
- Create: `templates/meridian/partials/payday-funding.html`
- Create: `static/js/meridian/payday.js`
- Modify: `templates/meridian/settings.html`
- Modify: `templates/meridian/partials/settings-navigation.html`
- Modify: `static/css/meridian/settings.css`
- Create: `tests/browser/test_payday_settings.py`

**Interfaces:**
- Consumes: `GET /api/meridian/settings/payday` and existing `meridianPropose('/api/meridian/funding-rules/propose', payload)`.
- Produces: `/meridian/settings?section=payday` with proposal-only editor and responsive live preview.

- [ ] **Step 1: Write failing browser tests**

```python
def test_payday_editor_explains_recognition_and_only_creates_a_proposal(page):
    captured = []
    def capture_proposal(route):
        captured.append(route.request.post_data_json)
        route.fulfill(
            status=201,
            content_type="application/json",
            body='{"proposal":{"id":41,"status":"pending"}}',
        )
    page.route("**/api/meridian/funding-rules/propose", capture_proposal)
    page.goto(f"{APP_URL}/meridian/settings?section=payday")
    assert "Biweekly" in page.locator('[data-payday-pattern]').inner_text()
    page.get_by_role("button", name="Review schedule change").click()
    assert len(captured) == 1
    assert captured[0]["kind"] == "fixed_per_paycheck"
    assert page.get_by_text("Proposal created for your approval").is_visible()
```

- [ ] **Step 2: Run the browser test and verify RED**

Run: `APP_URL=http://127.0.0.1:8081 pytest tests/browser/test_payday_settings.py -q`  
Expected: FAIL because the section does not exist.

- [ ] **Step 3: Implement the shared-schema editor**

Desktop places cadence, source, contribution mode, limits, pause/skip, and one-time override controls beside the projected timeline. Mobile orders the same controls into steps and keeps next-run, total allocation, and shortfall in a sticky summary. The submit action calls `meridianPropose`; no direct mutation fetch is permitted.

- [ ] **Step 4: Run browser and proposal tests**

Run: `APP_URL=http://127.0.0.1:8081 pytest tests/browser/test_payday_settings.py tests/browser/test_plan.py tests/meridian/test_funding_proposals.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add templates/meridian/partials/payday-funding.html static/js/meridian/payday.js templates/meridian/settings.html templates/meridian/partials/settings-navigation.html static/css/meridian/settings.css tests/browser/test_payday_settings.py
git commit -m "feat: add payday funding settings"
```

### Task 4: Add contextual entry points and acceptance gates

**Files:**
- Modify: `templates/meridian/partials/plan.html`
- Modify: `static/js/meridian/plan.js`
- Modify: `templates/meridian/partials/today.html`
- Modify: `static/js/meridian/today.js`
- Modify: `tests/browser/test_plan.py`
- Modify: `tests/browser/test_activity.py`
- Modify: `tests/browser/test_responsive_parity.py`

**Interfaces:**
- Consumes: Payday Settings route from Task 3.
- Produces: Plan schedule summary, relevant Today exceptions, and responsive screenshot evidence.

- [ ] **Step 1: Write failing contextual-navigation tests**

```python
def test_plan_opens_payday_settings_with_current_schedule_context(page):
    page.goto(f"{APP_URL}/meridian?workspace=plan")
    page.get_by_role("link", name="Manage payday funding schedule").click()
    assert "/meridian/settings?section=payday" in page.url

def test_today_only_surfaces_payday_when_review_is_required(page):
    page.route(
        "**/api/meridian/today",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body='{"safe_to_spend":{"amount":684,"currency":"USD","inputs":{}},"upcoming_events":[],"data_freshness":{"status":"fresh","last_updated_at":"2026-08-31T08:00:00Z"},"payday":{"state":"needs_review","message":"Funding schedule needs review"}}',
        ),
    )
    page.goto(f"{APP_URL}/meridian?workspace=today")
    assert page.locator('[data-payday-exception]').is_visible()
    assert "needs review" in page.locator('[data-payday-exception]').inner_text().lower()
```

- [ ] **Step 2: Run tests and verify RED**

Run: `APP_URL=http://127.0.0.1:8081 pytest tests/browser/test_plan.py tests/browser/test_activity.py -q`  
Expected: FAIL because contextual entry points are absent.

- [ ] **Step 3: Implement narrow entry points**

Add one schedule row to Plan and render a Today notice only for `needs_review`, `stale`, or `unavailable` payday state. Do not add Settings to the four-workspace dock.

- [ ] **Step 4: Run release and visual gates**

Run: `pytest tests/meridian/test_payday.py tests/meridian/services/test_payday.py tests/meridian/test_funding.py tests/meridian/test_funding_proposals.py -q`  
Run: `APP_URL=http://127.0.0.1:8081 pytest tests/browser/test_payday_settings.py tests/browser/test_plan.py tests/browser/test_activity.py tests/browser/test_responsive_parity.py -q`  
Expected: PASS.

Capture 1440×900 and 390×844 Payday & Funding states, compare them in the same QA input, fix P0–P2 findings, and record `final result: passed` in `design-qa.md`.

- [ ] **Step 5: Commit**

```bash
git add templates/meridian/partials/plan.html static/js/meridian/plan.js templates/meridian/partials/today.html static/js/meridian/today.js tests/browser/test_plan.py tests/browser/test_activity.py tests/browser/test_responsive_parity.py design-qa.md
git commit -m "feat: connect payday settings to Meridian workspaces"
```
