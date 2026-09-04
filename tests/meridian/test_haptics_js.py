"""Task 9: haptics.js provides a visible close alternative for sheets."""
from pathlib import Path


def test_haptics_js_is_served_and_wired():
    html = Path("templates/meridian/index.html").read_text(encoding="utf-8")
    assert "haptics.js" in html
    js = Path("static/js/meridian/haptics.js").read_text(encoding="utf-8")
    # Must add visible close buttons, never remove gestures.
    assert "m-sheet-haptic-close" in js
    assert "aria-label" in js


def test_haptics_css_present():
    css = Path("static/css/meridian/shell.css").read_text(encoding="utf-8")
    assert ".m-sheet-haptic-close" in css
