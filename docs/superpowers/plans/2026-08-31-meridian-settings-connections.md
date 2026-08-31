# Meridian Settings and Connections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the approved premium Settings > Connections experience with sanitized provider/evidence state, read-only authorization boundaries, desktop inspection, and an intentional mobile flow.

**Architecture:** Add a focused connection-authorization repository and sanitized service read model behind the existing authenticated Meridian blueprint. Render Settings as a utility surface outside the four financial workspaces, reuse the existing shell and inspector primitives, and keep OAuth tokens and external identifiers server-side.

**Tech Stack:** Flask, SQLite migrations, Python dataclasses, Jinja, ES modules, CSS custom properties, pytest, Playwright.

**Spec:** `docs/superpowers/specs/2026-08-31-meridian-settings-connections-design.md`

## Global Constraints

- Today, Plan, Activity, and Accounts remain the only four primary financial workspaces.
- Gmail and Calendar use exact read-only scopes and expose no mutation methods.
- External identifiers, provider tokens, raw message bodies, and sensitive evidence never enter browser payloads, DOM attributes, logs, screenshots, or fixtures.
- Connection state is one of `connected`, `pending`, `limited`, `failed`, or `revoked`; incomplete verification never appears connected.
- Financial changes remain proposal-only and require explicit approval.
- Desktop and mobile use the same read model but distinct compositions.
- All controls meet the existing 44-pixel minimum target and preserve reduced motion, safe areas, keyboard access, and focus restoration.

---

### Task 1: Persist sanitized evidence-connection metadata

**Files:**
- Create: `meridian/migrations/014_connection_authorizations.sql`
- Create: `meridian/connections.py`
- Create: `tests/meridian/test_connections.py`
- Modify: `tests/meridian/test_migrations.py`

**Interfaces:**
- Consumes: `meridian.db.run_migrations(db_path)`.
- Produces: `ConnectionRepository`, `ConnectionRecord`, `ConnectionState`, and `public_connection_id(kind: str, record_id: int) -> str`.

- [ ] **Step 1: Write failing migration and repository tests**

```python
def test_connection_repository_never_returns_provider_secrets(tmp_path):
    repository = ConnectionRepository(str(tmp_path / "connections.db"))
    saved = repository.upsert(
        kind="gmail",
        display_name="Gmail",
        state=ConnectionState.PENDING,
        granted_scopes=(READ_ONLY_GMAIL_SCOPE,),
        last_successful_at=None,
        retention_days=365,
    )
    assert saved.public_id.startswith("gmail_")
    assert not hasattr(saved, "access_token")
    assert repository.get(saved.public_id) == saved
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `pytest tests/meridian/test_connections.py tests/meridian/test_migrations.py -q`  
Expected: FAIL because migration 014 and `meridian.connections` do not exist.

- [ ] **Step 3: Add the narrow schema and repository**

```sql
CREATE TABLE connection_authorizations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    public_id TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    display_name TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('connected','pending','limited','failed','revoked')),
    granted_scopes TEXT NOT NULL DEFAULT '[]',
    last_successful_at TEXT,
    retention_days INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

Implement `ConnectionRepository.upsert`, `get`, `list_all`, `mark_state`, and `revoke`. Store scope names only; token persistence remains the owning provider adapter's responsibility.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `pytest tests/meridian/test_connections.py tests/meridian/test_migrations.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add meridian/migrations/014_connection_authorizations.sql meridian/connections.py tests/meridian/test_connections.py tests/meridian/test_migrations.py
git commit -m "feat: persist sanitized connection metadata"
```

### Task 2: Build the sanitized Connections read model

**Files:**
- Create: `meridian/services/connections.py`
- Create: `tests/meridian/services/test_connections.py`

**Interfaces:**
- Consumes: `FinancialRepository.list_connection_freshness()` and `ConnectionRepository.list_all()`.
- Produces: `build_connections(graph, authorizations, *, selected_id=None) -> dict[str, object]` and `get_connection_detail(authorizations, public_id) -> dict[str, object] | None`.

- [ ] **Step 1: Write failing service tests with literal expected payloads**

```python
def test_connections_group_money_evidence_and_time_without_secret_fields(graph, authorizations):
    payload = build_connections(graph, authorizations, selected_id="gmail_2")
    assert [group["kind"] for group in payload["groups"]] == ["money", "evidence", "time"]
    assert payload["selected"]["public_id"] == "gmail_2"
    assert payload["selected"]["permissions"] == ["Read bills, statements, and receipts"]
    serialized = json.dumps(payload)
    assert "token" not in serialized.lower()
    assert "external_id" not in serialized
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `pytest tests/meridian/services/test_connections.py -q`  
Expected: FAIL because the service module does not exist.

- [ ] **Step 3: Implement explicit provider presentation maps**

```python
USES = {
    "crew": ("Balances", "Transactions", "Income", "Cash flow"),
    "gmail": ("Bills", "Statements", "Receipts"),
    "calendar": ("Paydays", "Due dates", "Events"),
}
GROUP = {"crew": "money", "simplefin": "money", "gmail": "evidence", "calendar": "time"}
```

Return sanitized public IDs, display names, state, freshness, uses, read-only label, retention, and plain-language safeguards. Raise no provider-specific exception into the API layer.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `pytest tests/meridian/services/test_connections.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add meridian/services/connections.py tests/meridian/services/test_connections.py
git commit -m "feat: add sanitized connection read model"
```

### Task 3: Expose authenticated connection APIs

**Files:**
- Modify: `meridian/api.py`
- Modify: `app.py`
- Modify: `tests/meridian/test_api.py`

**Interfaces:**
- Consumes: `build_connections`, `get_connection_detail`, and `ConnectionRepository` from Tasks 1–2.
- Produces: `GET /api/meridian/settings/connections`, `GET /api/meridian/settings/connections/<public_id>`, `POST /api/meridian/settings/connections/<kind>/authorize`, and `POST /api/meridian/settings/connections/<public_id>/revoke`.

- [ ] **Step 1: Write failing API contract tests**

```python
def test_connection_api_requires_login_and_never_serializes_secrets(api_client, monkeypatch):
    client, _graph = api_client
    monkeypatch.setenv("GMAIL_ACCESS_TOKEN", "secret-sentinel")
    response = client.get("/api/meridian/settings/connections")
    assert response.status_code == 200
    assert "secret-sentinel" not in response.get_data(as_text=True)
    assert simplecrew.app.test_client().get("/api/meridian/settings/connections").status_code == 302

def test_revoke_requires_explicit_post_and_marks_only_the_selected_source(api_client):
    client, _graph = api_client
    response = client.post("/api/meridian/settings/connections/gmail_2/revoke")
    assert response.status_code == 200
    assert response.get_json()["state"] == "revoked"

def test_authorize_returns_only_provider_handoff_state(api_client, monkeypatch):
    client, _graph = api_client
    monkeypatch.setitem(
        simplecrew.app.config,
        "MERIDIAN_CONNECTION_AUTHORIZERS",
        {"gmail": lambda: {"authorization_url": "https://accounts.google.test/oauth"}},
    )
    response = client.post("/api/meridian/settings/connections/gmail/authorize")
    assert response.status_code == 200
    assert response.get_json() == {
        "state": "pending",
        "authorization_url": "https://accounts.google.test/oauth",
    }
```

- [ ] **Step 2: Run the API tests and verify RED**

Run: `pytest tests/meridian/test_api.py -q`  
Expected: FAIL with 404 for the new endpoints.

- [ ] **Step 3: Register the repository factory and endpoints**

Add `MERIDIAN_CONNECTIONS_FACTORY` and `MERIDIAN_CONNECTION_AUTHORIZERS` beside the existing Meridian factories. Apply `@login_required`; use `_safe_read` only for GET routes. Authorization accepts only allowlisted kinds, records `pending`, and returns a provider-hosted URL without token material. The callback verifies granted scope and initial read before marking `connected`; a partial scope becomes `limited`. The revoke route calls the owning read-only connector's `revoke()` through a server-side factory, then marks metadata revoked. It returns no token or raw provider response.

- [ ] **Step 4: Run API and connector safety tests**

Run: `pytest tests/meridian/test_api.py tests/meridian/connectors/test_email.py tests/meridian/connectors/test_calendar.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add meridian/api.py app.py tests/meridian/test_api.py
git commit -m "feat: expose authenticated connection settings APIs"
```

### Task 4: Add the Settings utility shell and desktop Connections ledger

**Files:**
- Create: `templates/meridian/settings.html`
- Create: `templates/meridian/partials/settings-navigation.html`
- Create: `templates/meridian/partials/connections.html`
- Create: `static/js/meridian/connections.js`
- Create: `static/css/meridian/settings.css`
- Modify: `templates/meridian/partials/navigation.html`
- Modify: `app.py`
- Create: `tests/browser/test_settings_connections.py`

**Interfaces:**
- Consumes: connection API contracts from Task 3.
- Produces: authenticated `/meridian/settings?section=connections&selected=<public_id>` and `window.MeridianConnections.load()`.

- [ ] **Step 1: Write failing browser tests for utility navigation and ledger behavior**

```python
def test_settings_is_a_utility_and_preserves_four_financial_destinations(page):
    page.goto(f"{APP_URL}/meridian/settings?section=connections")
    assert page.locator('[data-workspace]').count() == 4
    assert page.locator('[data-settings-link]').is_visible()
    assert page.locator('[data-connection-group]').count() == 3
    page.locator('[data-connection-id="gmail_2"]').click()
    assert page.locator('[data-connection-inspector]').is_visible()
```

- [ ] **Step 2: Run the browser test and verify RED**

Run: `APP_URL=http://127.0.0.1:8081 pytest tests/browser/test_settings_connections.py -q`  
Expected: FAIL because `/meridian/settings` does not exist.

- [ ] **Step 3: Implement the selected hybrid desktop composition**

Use the 150-pixel forest rail, compact secondary Settings navigation, grouped ledger, selected-row green wash, and persistent right inspector from the approved target. Render all API text with `textContent`; never interpolate provider payload into HTML.

- [ ] **Step 4: Run browser tests and verify GREEN**

Run: `APP_URL=http://127.0.0.1:8081 pytest tests/browser/test_settings_connections.py tests/browser/test_meridian_shell.py -q`  
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add templates/meridian/settings.html templates/meridian/partials/settings-navigation.html templates/meridian/partials/connections.html static/js/meridian/connections.js static/css/meridian/settings.css templates/meridian/partials/navigation.html app.py tests/browser/test_settings_connections.py
git commit -m "feat: build Meridian connection settings"
```

### Task 5: Implement mobile sheets, failure states, and visual acceptance

**Files:**
- Modify: `templates/meridian/partials/connections.html`
- Modify: `static/js/meridian/connections.js`
- Modify: `static/css/meridian/settings.css`
- Modify: `tests/browser/test_settings_connections.py`
- Modify: `tests/browser/test_responsive_parity.py`
- Create: `artifacts/design-audit-2026-08-31/settings-connections/README.md`

**Interfaces:**
- Consumes: desktop Settings UI from Task 4.
- Produces: mobile full-height detail sheet, focus restoration, and deterministic screenshot states.

- [ ] **Step 1: Add failing tests for mobile and degraded states**

```python
@pytest.mark.parametrize("viewport", [{"width": 390, "height": 844}, {"width": 430, "height": 932}])
def test_mobile_connection_detail_is_a_sheet_without_overflow(page, viewport):
    page.set_viewport_size(viewport)
    page.goto(f"{APP_URL}/meridian/settings?section=connections")
    opener = page.locator('[data-connection-id="gmail_2"]')
    opener.click()
    assert page.locator('[data-connection-sheet]').is_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    page.get_by_role("button", name="Close connection details").click()
    assert opener.evaluate("node => node === document.activeElement")
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `APP_URL=http://127.0.0.1:8081 pytest tests/browser/test_settings_connections.py tests/browser/test_responsive_parity.py -q`  
Expected: FAIL because mobile sheet behavior is absent.

- [ ] **Step 3: Implement mobile composition and explicit states**

Add 390/430 layouts, full-height sheet behavior, Escape/close handling, background inertness, and honest pending/limited/failed/revoked/offline rows. Keep the four-item financial dock unchanged.

- [ ] **Step 4: Run functional, accessibility, and screenshot gates**

Run: `APP_URL=http://127.0.0.1:8081 pytest tests/browser/test_settings_connections.py tests/browser/test_responsive_parity.py tests/browser/test_meridian_shell.py -q`  
Expected: PASS with no console errors or overflow.

Capture 1440×900 and 390×844 against the approved hybrid desktop and mobile references. Save `design-qa.md`, fix every P0–P2 difference, and require `final result: passed`.

- [ ] **Step 5: Commit**

```bash
git add templates/meridian/partials/connections.html static/js/meridian/connections.js static/css/meridian/settings.css tests/browser/test_settings_connections.py tests/browser/test_responsive_parity.py artifacts/design-audit-2026-08-31/settings-connections design-qa.md
git commit -m "feat: finish responsive connection settings"
```
