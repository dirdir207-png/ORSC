"""Tests for Crew write-back executors plugged into the action pipeline."""

from crew.actions import ActionStore
from crew.executors import ExecutorSpec
from meridian.crew_write_actions import crew_write_executors


def test_executors_register_all_verified_write_types(tmp_path):
    db = str(tmp_path / "m.db")
    specs = crew_write_executors(db)
    assert set(specs) == {
        "update_crew_bill",
        "update_crew_bill_reserve_settings",
        "create_crew_autopilot_rule",
        "create_crew_bill",
        "archive_crew_bill",
        "create_crew_pocket",
        "delete_crew_pocket",
        "crew_initiate_transfer",
        "create_crew_paycheck_funding_plan",
        "update_crew_paycheck_funding_plan",
        "delete_crew_paycheck_funding_plan",
        "top_up_crew_reserve",
        "delete_crew_autopilot_rule",
        "create_crew_pocket_reassignment_rule",
        "delete_crew_pocket_reassignment_rule",
        "set_crew_spend_pocket",
    }
    for spec in specs.values():
        assert callable(spec[0])


def test_propose_approve_execute_roundtrip(tmp_path, monkeypatch):
    db = str(tmp_path / "m.db")
    store = ActionStore(db, allowed_types=set(crew_write_executors(db)))
    executors = {
        key: ExecutorSpec(execute=fn, verifier=vf)
        for key, (fn, vf) in crew_write_executors(db).items()
    }

    # Registry the real execute_crew_write is mocked so the subprocess is safe.
    from meridian import crew_write, crew_write_actions

    def fake(operation, input_payload, **kwargs):
        return {"ok": True, "result": {"id": "bill-1"}, "retry_allowed": False}

    monkeypatch.setattr(crew_write_actions, "execute_crew_write", fake)
    monkeypatch.setattr(crew_write, "execute_crew_write", fake)

    from crew.executors import execute_approved_action

    request = store.propose(
        "update_crew_bill",
        {
            "billId": "QmlsbDox",
            "name": "Verizon",
            "amount": 9500,
            "frequency": "MONTHLY",
            "frequencyInterval": 1,
            "anchorDate": "2026-01-22",
        },
        "Rename/live Crew bill",
        requested_by="owner",
    )
    store.approve(request["id"], decided_by="owner")
    result = execute_approved_action(store, request["id"], executors)
    assert result["state"] in ("executed", "verified")
    assert result.get("result", {}).get("success") is True
    assert result.get("result", {}).get("crew", {}).get("ok") is True


def test_unknown_write_type_rejected_by_store(tmp_path):
    db = str(tmp_path / "m.db")
    store = ActionStore(db, allowed_types=set(crew_write_executors(db)))
    try:
        store.propose("delete_everything", {}, "nope", requested_by="owner")
    except ValueError:
        return
    raise AssertionError("unknown action type must be rejected")


def test_autopilot_rule_executor_enriches_formula_before_write(tmp_path, monkeypatch):
    """The create-autopilot executor must inject real accountId into the action so
    Crew never rejects a null accountId."""
    from meridian import crew_write_actions

    seen = {}
    def fake_execute(operation, input_payload):
        seen["operation"] = operation
        seen["payload"] = input_payload
        return {"ok": True, "result": {}}

    monkeypatch.setattr(crew_write_actions, "execute_crew_write", fake_execute)
    specs = crew_write_actions.crew_write_executors(str(tmp_path / "m.db"))
    executor = specs["create_crew_autopilot_rule"][0]
    executor({
        "name": "Zz Diag",
        "account_id": "Acct:checking",
        "subaccount_id": "Sub:fts",
        "formula": {
            "name": "Zz Diag",
            "triggers": ["ACCOUNT_DEPOSIT_RECEIVED"],
            "actions": [{"roundUpTransfer": {"roundToNearest": 100}}],
        },
    })
    assert seen["operation"] == "create_autopilot_rule"
    formula = seen["payload"]["formula"]
    action = formula["actions"][0]["roundUpTransfer"]
    assert action["accountId"] == "Acct:checking"
    assert action["accountType"] == "ACCOUNT"
    assert action["roundToNearest"] == 100


def test_set_spend_pocket_executor_reaches_write(tmp_path, monkeypatch):
    """set_crew_spend_pocket executor passes user/subaccount ids to the CLI."""
    from meridian import crew_write_actions

    seen = {}
    def fake_execute(operation, input_payload):
        seen["operation"] = operation
        seen["payload"] = input_payload
        return {"ok": True, "result": {}}

    monkeypatch.setattr(crew_write_actions, "execute_crew_write", fake_execute)
    specs = crew_write_actions.crew_write_executors(str(tmp_path / "m.db"))
    executor = specs["set_crew_spend_pocket"][0]
    executor({"user_id": "User:1", "subaccount_id": "Sub:2"})
    assert seen["operation"] == "set_spend_pocket"
    assert seen["payload"]["user_id"] == "User:1"
    assert seen["payload"]["subaccount_id"] == "Sub:2"
