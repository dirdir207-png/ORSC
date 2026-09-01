import json
import os

import pytest

APP_URL = os.getenv("APP_URL")
pytestmark = pytest.mark.skipif(
    not APP_URL, reason="APP_URL is required for browser tests"
)

OWNER_PASSWORD = "meridian-owner-2026"


def _authed_page(browser, viewport):
    from tests.browser.conftest import ensure_owner

    ensure_owner()
    context = browser.new_context(viewport=viewport)
    response = context.request.post(
        f"{APP_URL}/api/auth/login",
        headers={"Content-Type": "application/json"},
        data=json.dumps({"username": "owner", "password": "meridian-owner-2026"}),
    )
    assert response.status == 200
    return context.new_page()


@pytest.mark.parametrize(
    "viewport",
    [
        {"width": 390, "height": 844},
        {"width": 430, "height": 932},
        {"width": 768, "height": 1024},
        {"width": 1024, "height": 768},
        {"width": 1440, "height": 900},
    ],
)
def test_accounts_has_no_horizontal_overflow_and_connections_remain_reachable(
    browser, viewport
):
    page = _authed_page(browser, viewport)
    page.goto(f"{APP_URL}/meridian?workspace=accounts")
    page.wait_for_selector("[data-accounts]")
    page.wait_for_timeout(500)

    assert page.evaluate(
        "() => document.documentElement.scrollWidth <= document.documentElement.clientWidth"
    )
    assert page.locator("[data-connections]").is_visible()
    assert page.locator("[data-account-row]").first.is_visible()
