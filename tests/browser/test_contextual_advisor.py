import os

import pytest

APP_URL = os.getenv("APP_URL")
pytestmark = pytest.mark.skipif(not APP_URL, reason="APP_URL is required for browser tests")


def test_advisor_uses_selected_transaction_context(browser):
    from tests.browser.test_transaction_inspector import _authed_page, _install_routes

    context, page = _authed_page(browser)
    _install_routes(page)
    captured = []

    def advisor(route):
        captured.append(route.request.post_data_json)
        route.fulfill(
            content_type="application/json",
            body='{"answer":"Evidence-bound answer","evidence":["transaction:101"],"proposals":[],"provider":"test","model":"test","usage":{}}',
        )

    page.route("**/api/meridian/advisor", advisor)
    page.goto(f"{APP_URL}/meridian?workspace=activity", wait_until="domcontentloaded")
    page.locator('[data-transaction-id="101"]').click()
    page.locator("#advisor-fab").click()
    page.locator("#advisor-fab-input").fill("What happened?")
    page.locator("#advisor-fab-send").click()
    page.wait_for_timeout(150)

    assert captured[0]["context"]["kind"] == "transaction"
    assert captured[0]["context"]["object_id"] == "101"
    assert "Evidence-bound answer" in page.locator("#advisor-fab-log").inner_text()
    context.close()
