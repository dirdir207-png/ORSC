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


def test_plan_crew_action_forms_present():
    from pathlib import Path
    html = Path("templates/meridian/partials/plan.html").read_text(encoding="utf-8")
    assert 'data-crew-actions' in html
    for marker in ("data-ca-create-pocket", "data-ca-create-bill", "data-ca-top-up"):
        assert marker in html, f"missing {marker}"


def test_plan_js_wires_mutate():
    from pathlib import Path
    js = Path("static/js/meridian/plan.js").read_text(encoding="utf-8")
    assert "meridianMutate" in js
    assert "wireCrewActions" in js
    assert "/api/actions/mutate" in js or 'meridianMutate(' in js


def test_api_js_has_mutate_client():
    from pathlib import Path
    api = Path("static/js/meridian/api.js").read_text(encoding="utf-8")
    assert "meridianMutate" in api
    assert "/api/actions/mutate" in api


def test_autopilot_editor_supports_action_union():
    from pathlib import Path
    js = Path("static/js/meridian/plan.js").read_text(encoding="utf-8")
    for action in ("roundUpTransfer", "targetBalanceTransfer", "internalTransfer",
                   "splitDeposit", "sweepExcess"):
        assert action in js, f"missing action option {action}"
    assert "create_crew_autopilot_rule" in js
    assert "meridianMutate" in js
