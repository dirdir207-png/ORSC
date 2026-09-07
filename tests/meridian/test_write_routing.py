"""Write-routing classifier tests: owner-direct vs proposal decision table."""
from meridian.write_routing import Provenance, classify_action


def test_owner_direct_fully_specified_executes_without_proposal():
    d = classify_action(
        Provenance.OWNER_DIRECT.value, "update_crew_bill",
        {"amount": 1500.0, "deterministic": True},
    )
    assert d.requires_proposal is False
    assert "owner-direct" in d.reason


def test_ai_interpreted_requires_proposal():
    d = classify_action(
        Provenance.AI_INTERPRETED.value, "update_crew_bill", {"amount": 1500.0}
    )
    assert d.requires_proposal is True
    assert "interpretation" in d.reason


def test_composed_multi_op_requires_proposal():
    d = classify_action(
        Provenance.AI_COMPOSED.value, "cancel_income_source",
        {"amount": 30.0, "ops": ["cancel_income", "move_money"]},
    )
    assert d.requires_proposal is True
    assert "multi-action" in d.reason or "composed" in d.reason


def test_low_confidence_requires_proposal_even_for_owner_direct():
    d = classify_action(
        Provenance.OWNER_DIRECT.value, "update_crew_bill",
        {"amount": 1500.0}, low_confidence=True,
    )
    assert d.requires_proposal is True
    assert "low-confidence" in d.reason


def test_under_specified_requires_proposal():
    d = classify_action(
        Provenance.OWNER_DIRECT.value, "update_crew_bill",
        {"needs_amount": True, "amount": None},
    )
    assert d.requires_proposal is True
    assert "under-specified" in d.reason


def test_plan_level_budget_change_requires_proposal():
    d = classify_action(
        Provenance.OWNER_DIRECT.value, "update_autopilot_settings", {"optimize": True}
    )
    assert d.requires_proposal is True
    assert "plan-level" in d.reason


def test_plan_level_budget_type_always_proposal_regardless_of_provenance():
    # reallocate_budget is plan-level: it must be a proposal for any provenance.
    for prov in (Provenance.OWNER_DIRECT.value, Provenance.SCHEDULED.value, Provenance.AI_INTERPRETED.value):
        d = classify_action(prov, "reallocate_budget", {"amount": 100.0})
        assert d.requires_proposal is True
        assert "plan-level" in d.reason or "require confirmation" in d.reason


def test_explicit_confidence_below_threshold_requires_proposal():
    d = classify_action(
        Provenance.OWNER_DIRECT.value, "update_crew_bill",
        {"amount": 100.0, "confidence": 0.5},
    )
    assert d.requires_proposal is True


def test_unknown_provenance_defaults_to_proposal():
    d = classify_action("from_the_void", "update_crew_bill", {"amount": 1.0})
    assert d.requires_proposal is True


def test_fund_transfer_between_pockets_is_plan_level():
    d = classify_action(
        Provenance.OWNER_DIRECT.value, "move_money_between_pockets", {"amount": 30.0}
    )
    assert d.requires_proposal is True


def test_route_mutation_direct_vs_proposal_paths():
    """Owner-direct fully-specified routes direct; AI-composed routes to a proposal."""
    import tempfile

    from crew.actions import ActionStore
    from meridian.write_routing import route_mutation

    db = tempfile.mktemp(suffix=".db")
    store = ActionStore(db, allowed_types=("update_crew_bill", "move_money_between_pockets"))

    # Direct: owner sets Rent exactly -> should NOT require proposal, and should
    # attempt execution (no executor registered -> the direct path still returns
    # an action; here we only assert the routing decision + proposal gate).
    direct = route_mutation(
        store, {}, action_type="update_crew_bill",
        params={"amount": 1500.0, "deterministic": True},
        rationale="set rent", requested_by="owner",
        provenance="owner_direct",
    )
    assert direct["routing_direct"] is True
    assert direct["routing"].requires_proposal is False

    # AI-composed multi-op -> proposal (action stays PROPOSED, no auto-execute).
    prop = route_mutation(
        store, {}, action_type="move_money_between_pockets",
        params={"amount": 30.0, "ops": ["a", "b"]},
        rationale="ai interpreted cancel+move", requested_by="owner",
        provenance="ai_composed",
    )
    assert prop["routing_direct"] is False
    assert prop["routing"].requires_proposal is True
    assert prop["action"]["state"] == "proposed"


def test_direct_mutation_runs_executor_proposal_does_not(monkeypatch):
    """Owner-direct must attempt the executor; AI-interpreted must only propose."""
    import tempfile

    from crew.actions import ActionStore
    from crew.executors import ExecutorSpec
    from meridian.write_routing import route_mutation

    db = tempfile.mktemp(suffix=".db")
    store = ActionStore(db, allowed_types=("create_crew_pocket",))
    calls = []

    def fake_create(params):
        calls.append(params)
        return {"success": True, "crew": {"ok": True}}

    executors = {"create_crew_pocket": ExecutorSpec(execute=fake_create, verifier=None)}

    # Owner-direct, fully-specified -> executes (fake called).
    direct = route_mutation(
        store, executors, action_type="create_crew_pocket",
        params={"account_id": "Acct:1", "name": "Savings", "type": "SAVINGS"},
        rationale="set pocket", requested_by="owner", provenance="owner_direct",
    )
    assert direct["routing_direct"] is True
    assert direct["action"]["state"] == "verified"   # executor ran + verified
    assert calls, "owner-direct mutation should have reached the executor"

    # AI-interpreted -> proposal only, executor never called.
    calls.clear()
    prop = route_mutation(
        store, executors, action_type="create_crew_pocket",
        params={"account_id": "Acct:1", "name": "Savings", "type": "SAVINGS"},
        rationale="ai interpreted", requested_by="owner", provenance="ai_interpreted",
    )
    assert prop["routing_direct"] is False
    assert prop["action"]["state"] == "proposed"
    assert calls == [], "AI-interpreted mutation must NOT reach the executor until approved"
