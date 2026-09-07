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


def test_plan_js_has_delete_bill_control():
    from pathlib import Path
    js = Path("static/js/meridian/plan.js").read_text(encoding="utf-8")
    assert 'archive_crew_bill' in js
    assert 'Delete bill' in js or '"Delete"' in js
    assert 'meridianMutate' in js


def test_plan_css_has_integrated_action_styles():
    from pathlib import Path
    css = Path("static/css/meridian/plan.css").read_text(encoding="utf-8")
    # Destructive delete + routed action-note feedback must be styled so the
    # action cell reads as an integrated row (not unstyled text bleeding over).
    assert ".m-button--danger" in css
    assert "color: var(--m-risk" in css or "color: var(--m-risk" in css
    assert ".m-action-note" in css
    assert '.m-action-note[data-state="ok"]' in css
    assert '.m-action-note[data-state="error"]' in css
    # Action buttons flow as a row, note wraps under them.
    assert ".m-plan-cell-action .m-action-note" in css


def test_plan_js_builds_cohesive_commitment_action_cell():
    from pathlib import Path
    js = Path("static/js/meridian/plan.js").read_text(encoding="utf-8")
    assert 'm-plan-cell-action' in js
    assert 'Edit funding' in js
    assert 'Save to Crew' in js
    assert 'm-button--danger' in js
    assert 'Delete' in js
    assert 'archive_crew_bill' in js


def test_shared_buttons_have_snappy_transitions():
    from pathlib import Path
    # Motion primitives live centrally in motion.css under reduced-motion guard.
    motion = Path("static/css/meridian/motion.css").read_text(encoding="utf-8")
    assert "prefers-reduced-motion: no-preference" in motion
    assert ".m-button," in motion
    assert ".m-primary-button," in motion
    assert "var(--m-motion-fast)" in motion
    assert "var(--m-ease-out)" in motion
    # Base button rules stay (sans transition) in workspaces.css.
    workspaces = Path("static/css/meridian/workspaces.css").read_text(encoding="utf-8")
    assert ".m-button {" in workspaces
    assert "cursor: pointer;" in workspaces


def test_plan_summary_cards_have_hover_lift():
    from pathlib import Path
    css = Path("static/css/meridian/plan.css").read_text(encoding="utf-8")
    assert ".m-plan-coverage-card:hover," in css
    assert "var(--m-elevation-2)" in css


def test_build_crew_catalog_helpers(tmp_path):
    """Catalog builder parses contracts + tracks capture status correctly."""
    import sys
    sys.path.insert(0, "scripts")
    import build_crew_catalog as bc

    # catalog_contracts parses documented mutations from the real doc.
    contracts = bc.catalog_contracts()
    assert "TopUpReserve" in contracts
    assert "CreateBill" in contracts
    assert "billReserveId" in contracts["TopUpReserve"]

    # parse_mitm_log dedups + records variables from a small log.
    log = tmp_path / "capture.log"
    log.write_text("\n".join([
        '{"operation":"TopUpReserve","kind":"mutation","variables":{"input":{"billReserveId":"BR1"}}}',
        '{"operation":"TopUpReserve","kind":"mutation","variables":{"input":{"billReserveId":"BR1"}}}',
    ]))
    ops = bc.parse_mitm_log(log)
    assert "TopUpReserve" in ops
    assert len(ops["TopUpReserve"]["variables"]) == 1


def test_plan_js_loads_capture_status():
    from pathlib import Path
    js = Path("static/js/meridian/plan.js").read_text(encoding="utf-8")
    assert "loadCaptureStatus" in js
    assert "/api/meridian/crew/mutations-status" in js
    assert "data-capture-status" in js


def test_plan_html_has_capture_status_panel():
    from pathlib import Path
    html = Path("templates/meridian/partials/plan.html").read_text(encoding="utf-8")
    assert "data-capture-status" in html
    assert "data-capture-track" in html
    assert "data-capture-note" in html


def test_plan_js_wires_delete_autopilot_rule():
    from pathlib import Path
    js = Path("static/js/meridian/plan.js").read_text(encoding="utf-8")
    assert "delete_crew_autopilot_rule" in js
    assert "data-ca-delete-rule" in js
    assert "crew_ids" in js and ".rules" in js


def test_plan_html_has_delete_rule_picker():
    from pathlib import Path
    html = Path("templates/meridian/partials/plan.html").read_text(encoding="utf-8")
    assert "data-ca-delete-rule" in html
    assert 'name="rule_id"' in html


def test_plan_js_wires_set_spend_pocket():
    from pathlib import Path
    js = Path("static/js/meridian/plan.js").read_text(encoding="utf-8")
    assert "set_crew_spend_pocket" in js
    assert "data-ca-set-spend" in js
    assert "populatePocketPicker" in js


def test_plan_html_has_set_spend_pocket_picker():
    from pathlib import Path
    html = Path("templates/meridian/partials/plan.html").read_text(encoding="utf-8")
    assert "data-ca-set-spend" in html
    assert 'name="subaccount_id"' in html


def test_plan_js_wires_delete_pocket():
    from pathlib import Path
    js = Path("static/js/meridian/plan.js").read_text(encoding="utf-8")
    assert "delete_crew_pocket" in js
    assert "data-ca-delete-pocket" in js
    assert "populatePocketPicker(delPocket, true)" in js or "populatePocketPicker(" in js


def test_plan_js_populate_pocket_picker_handles_all_flag():
    from pathlib import Path
    js = Path("static/js/meridian/plan.js").read_text(encoding="utf-8")
    assert "function populatePocketPicker(form, all = false)" in js
    assert "crew.subaccounts" in js


def test_plan_actions_panel_cards_are_styled():
    from pathlib import Path
    css = Path("static/css/meridian/plan.css").read_text(encoding="utf-8")
    assert ".m-plan-actions" in css
    assert ".m-action-form" in css
    assert "border-radius: var(--m-radius-lg)" in css


def test_mobile_main_clears_floating_advisor():
    from pathlib import Path
    css = Path("static/css/meridian/shell.css").read_text(encoding="utf-8")
    assert "env(safe-area-inset-bottom)" in css
    assert "m-space-7" in css  # extra bottom clearance so cards scroll clear of the FAB
