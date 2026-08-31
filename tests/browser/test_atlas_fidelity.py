# Atlas-fidelity gate (visual recovery Task 1).
# Captures each workspace at reference viewports and compares against the saved
# "current" baseline. Pass an APP_URL (running preview) to enable; set
# UPDATE_BASELINES=1 to refresh baselines deliberately after an approved change.

import os
from pathlib import Path

import pytest

from tests.browser.conftest import WORKSPACES, capture_workspace, login  # noqa: F401

pytestmark = pytest.mark.skipif(not os.environ.get("APP_URL"), reason="APP_URL required")

APP_URL = os.environ.get("APP_URL")
UPDATE = os.environ.get("UPDATE_BASELINES") == "1"
BASELINE_DIR = Path(__file__).parent / "visual_baselines" / "current"
DIFF_THRESHOLD = float(os.environ.get("ATLAS_DIFF_THRESHOLD", "0.015"))  # 1.5% of pixels

pytest.importorskip("PIL")
from PIL import Image as _Image, ImageChops as _ImageChops  # noqa: E402


def _compare(path, baseline):
    """Return (diff_ratio, same_dimensions)."""
    a = _Image.open(path).convert("RGB")
    b = _Image.open(baseline).convert("RGB")
    if a.size != b.size:
        return 1.0, False
    diff = _ImageChops.difference(a, b).convert("L")
    hist = diff.histogram()
    changed = sum(hist[1:])
    return changed / (a.size[0] * a.size[1]), True


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture()
def authed_page(browser):
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    login(page, APP_URL)
    return page


def _assert_semantics(page, workspace):
    state = page.evaluate(
        """(ws) => {
            const sec = document.querySelector(`[data-workspace-section="${ws}"]`);
            const html = document.documentElement;
            return {
                visible: !!sec && !sec.hidden && sec.offsetParent !== null,
                noOverflow: html.scrollWidth <= html.clientWidth + 1,
                heading: !!(sec && sec.querySelector(
                    'h1,h2,h3,.m-command-header,.m-editorial-headline,.m-workspace-heading'
                )),
                textLen: (sec && sec.innerText ? sec.innerText.trim().length : 0),
            };
        }""",
        workspace,
    )
    assert state["visible"], f"{workspace} workspace section is not visible"
    assert state["noOverflow"], f"{workspace} has horizontal overflow"
    assert state["heading"], f"{workspace} has no command header/heading"
    assert state["textLen"] > 40, f"{workspace} section looks blank"


@pytest.mark.parametrize("workspace", WORKSPACES)
@pytest.mark.parametrize("name,size", [("desktop", (1440, 900)), ("mobile-s", (390, 844))])
def test_workspace_matches_baseline(authed_page, workspace, name, size, tmp_path):
    out = tmp_path / f"{workspace}-{name}.png"
    capture_workspace(authed_page, APP_URL, workspace, size[0], size[1], out)
    _assert_semantics(authed_page, workspace)

    baseline = BASELINE_DIR / f"{workspace}-{name}.png"
    if UPDATE:
        BASELINE_DIR.mkdir(parents=True, exist_ok=True)
        baseline.write_bytes(out.read_bytes())
        return

    assert baseline.exists(), (
        f"baseline {baseline.name} missing — run with UPDATE_BASELINES=1 to create it"
    )
    ratio, same = _compare(out, baseline)
    assert same, f"baseline and capture differ in size ({workspace}-{name})"
    assert ratio <= DIFF_THRESHOLD, (
        f"{workspace}-{name} drifted ({ratio:.1%} of pixels differ > {DIFF_THRESHOLD:.1%})"
    )
