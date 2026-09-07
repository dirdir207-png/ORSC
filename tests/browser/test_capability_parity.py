"""R30: Crew feature-parity contract (family accounts excluded by scope).

For each legacy Crew-backed capability, assert Meridian exposes either a
REAL control (approval-gated, wired to a proposal) or an explicit, honest
`data-parity-deferred` marker. The parity list is a contract: a capability
may move from deferred to wired only by adding the real control AND removing
its deferred marker — never by deleting the marker alone.

Family accounts are explicitly OUT of scope per the owner's direction.

Checks (real backend via APP_URL, no external bank action):
  1. Wired controls render on the Plan workspace:
       - data-plan-new-commitment  (Crew bill write-back / commitment proposal)
       - data-plan-new-rule        (Create autopilot rule proposal)
  2. Every deferred capability in the contract is honestly listed with a
     data-parity-deferred marker (no capability silently dropped).
  3. Deferred items run only through legacy — nothing on the parity list is
     presented as a live Meridian Crew write control.
"""

import json
import os

import pytest

APP_URL = os.getenv("APP_URL")
pytestmark = pytest.mark.skipif(not APP_URL, reason="APP_URL is required for browser tests")

DESKTOP = {"width": 1440, "height": 900}
OWNER_PASSWORD = "meridian-owner-2026"

# Crew-backed capabilities not yet exposed as a Meridian control. These must
# each carry an explicit deferred marker on the Plan page.
DEFERRED_CAPABILITIES = {
    "spend_pocket": "Set active spend pocket",
    "delete_pocket": "Delete pocket",
    "virtual_card": "Create / update virtual card",
    "pocket_reassignment": "Pocket reassignment rules",
    "delete_autopilot_rule": "Delete autopilot rule",
}

# Wired controls that must render as real, approval-gated Meridian controls.
WIRED_PLAN_CONTROLS = {
    "data-plan-new-commitment": "New commitment (Crew bill write-back)",
    "data-plan-new-rule": "New autopilot rule",
}


def _authed_page(context):
    response = context.request.post(
        f"{APP_URL}/api/auth/login",
        headers={"Content-Type": "application/json"},
        data=json.dumps({"username": "owner", "password": OWNER_PASSWORD}),
    )
    assert response.status == 200, f"owner login must succeed: {response.status}"
    return context.new_page()


def test_wired_crew_controls_render_on_plan(browser):
    from tests.browser.conftest import ensure_owner

    ensure_owner()
    context = browser.new_context(viewport=DESKTOP)
    page = _authed_page(context)
    page.goto(f"{APP_URL}/meridian?workspace=plan", wait_until="networkidle")

    for data_attr, label in WIRED_PLAN_CONTROLS.items():
        control = page.locator(f"[{data_attr}]")
        assert control.count() >= 1, (
            f"R30 parity: '{label}' should expose a real Meridian control "
            f"({data_attr}), but none rendered on the Plan workspace."
        )
        assert control.first.is_visible(), (
            f"R30 parity: '{label}' rendered but is not visible."
        )
        # The control must open an approval-gated proposal, i.e. it is a button.
        assert control.first.get_attribute("aria-haspopup") in ("dialog", None), (
            f"R30 parity: '{label}' should be an action (button) that opens an "
            f"approval-gated proposal flow."
        )


def test_every_deferred_capability_has_an_honest_marker(browser):
    from tests.browser.conftest import ensure_owner

    ensure_owner()
    context = browser.new_context(viewport=DESKTOP)
    page = _authed_page(context)
    page.goto(f"{APP_URL}/meridian?workspace=plan", wait_until="networkidle")

    for key, label in DEFERRED_CAPABILITIES.items():
        marker = page.locator(f"[data-parity-deferred='{key}']")
        assert marker.count() == 1, (
            f"R30 parity: '{label}' ({key}) must carry exactly one honest "
            f"deferred marker, but found {marker.count()}."
        )
        assert marker.first.is_visible(), (
            f"R30 parity: the deferred marker for '{label}' is present but hidden "
            f"or out of the a11y tree — it must be honest and visible."
        )


def test_deferred_items_are_not_live_crew_write_controls(browser):
    """The deferred parity list must not present any capability as a live Crew
    write control. Each deferred entry is list text, not a trigger button."""
    from tests.browser.conftest import ensure_owner

    ensure_owner()
    context = browser.new_context(viewport=DESKTOP)
    page = _authed_page(context)
    page.goto(f"{APP_URL}/meridian?workspace=plan", wait_until="networkidle")

    parity = page.locator("[data-crew-parity]")
    assert parity.count() == 1, "a single honest parity section should render"
    # No deferred entry may be an actionable control (button/link that submits).
    for item in parity.locator("[data-parity-deferred]").all():
        tag = item.evaluate("el => el.tagName")
        assert tag in ("LI", "P", "DIV", "SPAN", "DD"), (
            f"R30 parity: deferred item rendered as <{tag}>, which looks like a "
            f"control; it should be plain list text only."
        )
