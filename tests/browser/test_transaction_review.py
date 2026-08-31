import json
import os

import pytest

APP_URL = os.getenv("APP_URL")
pytestmark = pytest.mark.skipif(not APP_URL, reason="APP_URL is required for browser tests")


def test_review_modes_show_confidence_patterns_and_preserve_inspector(browser):
    from tests.browser.test_transaction_inspector import _authed_page, _fulfill

    context, page = _authed_page(browser)
    transaction = {
        "id": 101,
        "account_id": 11,
        "provider": "crew",
        "amount": -3,
        "currency": "USD",
        "occurred_at": "2026-08-20T18:00:00Z",
        "description": "Coffee",
        "merchant": "Blue Bottle",
        "status": "posted",
        "classification": {"category": "Dining", "kind": "spend", "confidence": 0.49, "evidence": "uncertain merchant"},
    }

    def activity_route(route):
        mode = "patterns" if "mode=patterns" in route.request.url else "review"
        payload = (
            {"patterns": [{"kind": "recurrence", "title": "Monthly coffee", "evidence_ids": [101]}], "data_freshness": {"status": "fresh"}}
            if mode == "patterns"
            else {"transactions": [transaction], "next_cursor": None, "data_freshness": {"status": "fresh"}}
        )
        route.fulfill(content_type="application/json", body=json.dumps(payload))

    page.route("**/api/meridian/activity*", activity_route)
    page.route("**/api/meridian/transactions/101", _fulfill({"transaction": transaction, "data_freshness": {"status": "fresh"}}))
    page.route("**/api/meridian/accounts", _fulfill({"accounts": [], "data_freshness": {"status": "fresh"}}))
    page.goto(f"{APP_URL}/meridian?workspace=activity", wait_until="domcontentloaded")
    page.locator('[data-activity-mode="review"]').click()
    assert "49% confidence" in page.locator("[data-confidence-label]").inner_text()
    page.locator('[data-transaction-id="101"]').click()
    page.locator('[data-activity-mode="patterns"]').click()
    assert page.locator("[data-inspector-rail]").is_visible()
    assert page.locator('[data-pattern-card="recurrence"]').is_visible()
    context.close()
