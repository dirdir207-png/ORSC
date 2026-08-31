import os

import pytest

APP_URL = os.getenv("APP_URL")
pytestmark = pytest.mark.skipif(
    not APP_URL, reason="APP_URL is required for browser tests"
)


def test_accounts_workspace_uses_financial_roles_not_provider_workspaces(page):
    page.goto(f"{APP_URL}/meridian?workspace=accounts")
    page.wait_for_selector("[data-accounts-group]")

    roles = page.locator("[data-accounts-group]").evaluate_all(
        "nodes => nodes.map(node => node.dataset.accountsGroup)"
    )
    assert "cash" in roles
    assert page.locator("[data-provider-workspace]").count() == 0
    assert page.locator("[data-connections]").count() == 1


def test_accounts_rows_keep_provider_marks_secondary(page):
    page.goto(f"{APP_URL}/meridian?workspace=accounts")
    page.wait_for_selector("[data-account-row]")

    row = page.locator("[data-account-row]").first
    assert row.locator("[data-account-name]").is_visible()
    assert row.locator("[data-account-source]").count() == 1
    assert row.locator("[data-account-source]").evaluate(
        "node => parseFloat(getComputedStyle(node).fontSize)"
    ) < row.locator("[data-account-name]").evaluate(
        "node => parseFloat(getComputedStyle(node).fontSize)"
    )
