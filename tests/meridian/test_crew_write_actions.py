"""Tests for Crew write-back executors plugged into the action pipeline."""

from crew.actions import ActionStore
from crew.executors import ExecutorSpec
from meridian.crew_write import execute_crew_write
from meridian.crew_write_actions import crew_write_executors


def test_executors_register_three_write_types(tmp_path):
    db = str(tmp_path / "m.db")
    specs = crew_write_executors(db)
    assert set(specs) == {
        "update_crew_bill",
        "update_crew_bill_reserve_settings",
        "create_crew_autopilot_rule",
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
    from meridian import crew_write
    from meridian import crew_write_actions

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
