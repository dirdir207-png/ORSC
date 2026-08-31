import os

import pytest

APP_URL = os.getenv("APP_URL")
pytestmark = pytest.mark.skipif(
    not APP_URL, reason="APP_URL is required for browser tests"
)


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
    page, viewport
):
    page.set_viewport_size(viewport)
    page.goto(f"{APP_URL}/meridian?workspace=accounts")
    page.wait_for_selector("[data-accounts]")

    assert page.evaluate(
        "() => document.documentElement.scrollWidth <= document.documentElement.clientWidth"
    )
    assert page.locator("[data-connections]").is_visible()
    assert page.locator("[data-account-row]").first.is_visible()
