"""Shared setup for browser tests: the single-tenant owner must exist."""

import json
import os
import urllib.error
import urllib.request

APP_URL = os.getenv("APP_URL")
OWNER_PASSWORD = "meridian-owner-2026"


def ensure_owner() -> None:
    """Register the owner once; tolerate reruns where registration is disabled."""
    if not APP_URL:
        return
    body = json.dumps(
        {
            "username": "owner",
            "email": "owner@meridian.local",
            "password": OWNER_PASSWORD,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{APP_URL}/api/auth/register",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request) as response:
            assert response.status == 200
    except urllib.error.HTTPError as error:
        assert error.code == 403, f"Unexpected registration outcome: {error.code}"


# Deterministic atlas-fidelity capture helpers (visual recovery Task 1).
# A frozen preview clock (seed_preview.PREVIEW_TODAY) keeps seeded records stable.
VIEWPORTS = {"desktop": (1440, 900), "tablet": (1024, 768), "mobile": (430, 932), "mobile-s": (390, 844)}
WORKSPACES = ["today", "plan", "activity", "accounts"]


def login(page, app_url=APP_URL):
    """Drive the login form to authenticate the owner session."""
    page.goto(f"{app_url}/login")
    page.fill('input[name="username"]', "owner")
    page.fill('input[name="password"]', "meridian-owner-2026")
    page.click('button[type="submit"]')
    page.wait_for_url(f"{app_url}/meridian*", timeout=15000)


def capture_workspace(page, app_url, workspace, width, height, out_path):
    """Deterministically capture a workspace at a viewport: wait for a settled,
    animation-free, data-loaded render so pixel-diffs are reproducible."""
    page.set_viewport_size({"width": width, "height": height})
    page.goto(f"{app_url}/meridian?workspace={workspace}")
    page.wait_for_load_state("networkidle", timeout=15000)
    try:
        page.evaluate("() => document.fonts && document.fonts.ready")
    except Exception:
        pass
    page.add_style_tag(content="*{animation:none !important; transition:none !important; caret-color:transparent !important}")
    try:
        page.wait_for_function(
            "(ws) => !document.querySelector(`[data-workspace-section='${ws}'] [aria-busy='true']`)",
            arg=workspace, timeout=12000,
        )
    except Exception:
        pass
    page.wait_for_timeout(700)
    page.screenshot(path=str(out_path), full_page=True)
    return page
