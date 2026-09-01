import json
import os

import pytest

APP_URL = os.getenv("APP_URL")
pytestmark = pytest.mark.skipif(
    not APP_URL, reason="APP_URL is required for browser tests"
)
OWNER_PASSWORD = "meridian-owner-2026"
DESKTOP_VIEWPORT = {"width": 1440, "height": 900}


@pytest.fixture()
def authed_page(browser):
    from tests.browser.conftest import ensure_owner

    ensure_owner()
    context = browser.new_context(viewport=DESKTOP_VIEWPORT)
    response = context.request.post(
        f"{APP_URL}/api/auth/login",
        headers={"Content-Type": "application/json"},
        data=json.dumps({"username": "owner", "password": OWNER_PASSWORD}),
    )
    assert response.status == 200
    yield context.new_page()


def test_accounts_workspace_uses_financial_roles_not_provider_workspaces(authed_page):
    authed_page.goto(f"{APP_URL}/meridian?workspace=accounts")
    authed_page.wait_for_selector("[data-accounts-group]")

    roles = authed_page.locator("[data-accounts-group]").evaluate_all(
        "nodes => nodes.map(node => node.dataset.accountsGroup)"
    )
    assert "cash" in roles
    assert authed_page.locator("[data-provider-workspace]").count() == 0
    assert authed_page.locator("[data-connections]").count() == 1


def test_accounts_rows_keep_provider_marks_secondary(authed_page):
    authed_page.goto(f"{APP_URL}/meridian?workspace=accounts")
    authed_page.wait_for_selector("[data-account-row]")

    row = authed_page.locator("[data-account-row]").first
    assert row.locator("[data-account-name]").is_visible()
    assert row.locator("[data-account-source]").count() == 1
    assert row.locator("[data-account-source]").evaluate(
        "node => parseFloat(getComputedStyle(node).fontSize)"
    ) < row.locator("[data-account-name]").evaluate(
        "node => parseFloat(getComputedStyle(node).fontSize)"
    )
