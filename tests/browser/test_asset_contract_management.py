import os

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("APP_URL"), reason="APP_URL required")

PLAYWRIGHT = pytest.importorskip("playwright.sync_api")


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        yield browser
        browser.close()


def _login(page):
    import requests

    url = os.environ["APP_URL"]
    requests.post(f"{url}/api/auth/login",
                  json={"username": "owner", "password": "meridian-owner-2026"}, timeout=10)
    # session cookie is set on the requests session, not the browser; use the
    # browser login page instead when the fixture user exists:
    page.goto(f"{url}/login")
    page.fill('input[name="username"]', "owner")
    page.fill('input[name="password"]', "meridian-owner-2026")
    page.click('button[type="submit"]')
    page.wait_for_url(f"{url}/meridian*")


def test_asset_management_flow(browser):
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    _login(page)
    page.goto(f"{os.environ['APP_URL']}/meridian?workspace=accounts")
    page.click("[data-testid=add-asset]")
    page.fill("[data-testid=asset-name]", "Test Asset")
    page.select_option("[data-testid=asset-category]", "electronics")
    page.click("[data-testid=submit-asset]")
    page.wait_for_selector("text=proposal created")
    # pending approval surface lists it
    page.goto(f"{os.environ['APP_URL']}/meridian?workspace=activity")
    page.wait_for_selector("[data-testid=pending-memory-proposals]")
    page.click("[data-testid=approve-proposal]")
    page.click("[data-testid=execute-proposal]")
    page.goto(f"{os.environ['APP_URL']}/meridian?workspace=accounts")
    page.wait_for_selector("text=Test Asset")
    page.close()
