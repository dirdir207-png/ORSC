import json
import os

import pytest

APP_URL = os.getenv("APP_URL")
pytestmark = pytest.mark.skipif(not APP_URL, reason="APP_URL is required")

DESKTOP = {"width": 1440, "height": 900}
OWNER_PASSWORD = "meridian-owner-2026"


def _page(browser, viewport=DESKTOP):
    from tests.browser.conftest import ensure_owner

    ensure_owner()
    context = browser.new_context(viewport=viewport, color_scheme="light")
    response = context.request.post(
        f"{APP_URL}/api/auth/login",
        headers={"Content-Type": "application/json"},
        data=json.dumps({"username": "owner", "password": OWNER_PASSWORD}),
    )
    assert response.status == 200
    return context, context.new_page()


def _payload():
    return {
        "groups": [
            {
                "kind": "money",
                "label": "Money",
                "connections": [
                    {
                        "public_id": "crew_1",
                        "kind": "crew",
                        "display_name": "Crew",
                        "group": "money",
                        "state": "connected",
                        "freshness": "2026-08-31T08:12:00Z",
                        "uses": ["Balances", "Transactions", "Income", "Cash flow"],
                        "read_only": True,
                    }
                ],
            },
            {
                "kind": "evidence",
                "label": "Evidence",
                "connections": [
                    {
                        "public_id": "gmail_2",
                        "kind": "gmail",
                        "display_name": "Gmail",
                        "group": "evidence",
                        "state": "connected",
                        "freshness": "2026-08-31T07:47:00Z",
                        "uses": ["Bills", "Statements", "Receipts"],
                        "read_only": True,
                    }
                ],
            },
            {
                "kind": "time",
                "label": "Time",
                "connections": [
                    {
                        "public_id": "calendar_3",
                        "kind": "calendar",
                        "display_name": "Google Calendar",
                        "group": "time",
                        "state": "connected",
                        "freshness": "2026-08-31T07:52:00Z",
                        "uses": ["Paydays", "Due dates", "Events"],
                        "read_only": True,
                    }
                ],
            },
        ],
        "selected": None,
        "safeguards": {
            "read_only": True,
            "individually_revocable": True,
            "proposal_only_financial_changes": True,
        },
    }


def _fulfill(payload):
    def handler(route):
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(payload),
        )

    return handler


def test_settings_is_a_utility_and_preserves_four_financial_destinations():
    with pytest.importorskip("playwright.sync_api").sync_playwright() as pw:
        browser = pw.chromium.launch()
        context, page = _page(browser)
        page.route("**/api/meridian/settings/connections*", _fulfill(_payload()))

        page.goto(
            f"{APP_URL}/meridian/settings?section=connections",
            wait_until="domcontentloaded",
        )

        assert page.locator('[data-workspace]').count() == 4
        assert page.locator('[data-settings-link][aria-current="page"]').is_visible()
        assert page.locator('[data-connection-group]').count() == 3
        selected = page.locator('[data-connection-id="gmail_2"]')
        selected.click()
        assert selected.get_attribute("aria-pressed") == "true"
        assert page.locator('[data-connection-inspector]').is_visible()
        assert "Gmail" in page.locator('[data-connection-inspector]').inner_text()
        browser.close()


@pytest.mark.parametrize(
    "viewport",
    [{"width": 390, "height": 844}, {"width": 430, "height": 932}],
)
def test_mobile_connection_detail_is_a_modal_sheet_without_overflow(viewport):
    with pytest.importorskip("playwright.sync_api").sync_playwright() as pw:
        browser = pw.chromium.launch()
        context, page = _page(browser, viewport)
        page.route("**/api/meridian/settings/connections*", _fulfill(_payload()))
        page.goto(
            f"{APP_URL}/meridian/settings?section=connections",
            wait_until="domcontentloaded",
        )

        opener = page.locator('[data-connection-id="gmail_2"]')
        opener.click()
        sheet = page.locator('[data-connection-sheet]')
        assert sheet.is_visible()
        assert sheet.get_attribute("role") == "dialog"
        assert sheet.get_attribute("aria-modal") == "true"
        assert page.evaluate(
            "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
        )

        page.get_by_role("button", name="Close connection details").click()
        assert opener.evaluate("node => node === document.activeElement")
        browser.close()
