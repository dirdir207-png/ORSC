"""Tests for the Crew write-back executor (personal-use bill/rule writes)."""

import json
import subprocess

from meridian.crew_write import (
    CrewWriteBlocked,
    CrewWriteUncertain,
    execute_crew_write,
)


def _fake_run(returncode, stdout, stderr=""):
    class Result:
        def __init__(self):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    return Result()


def test_success_result_maps_ok_and_returns_payload(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda cmd, timeout=None, capture_output=True, **kwargs: _fake_run(
            0, json.dumps({"ok": True, "result": {"id": "bill-1"}})
        ),
    )
    outcome = execute_crew_write(
        "update_bill",
        {"input": {"billId": "b1"}},
        crew_write_bin="crew-write",
    )
    assert outcome["ok"] is True
    assert outcome["result"]["id"] == "bill-1"
    assert outcome["retry_allowed"] is False


def test_rejected_maps_to_blocked(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda cmd, timeout=None, capture_output=True, **kwargs: _fake_run(
            3, json.dumps({"ok": False, "error": "rejected", "message": "no"})
        ),
    )
    outcome = execute_crew_write("update_bill", {"input": {"billId": "b1"}})
    assert outcome["ok"] is False
    assert outcome["error"] in ("rejected", "blocked")
    assert outcome["retry_allowed"] is False


def test_uncertain_never_retries(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda cmd, timeout=None, capture_output=True, **kwargs: _fake_run(
            4, json.dumps({"ok": False, "error": "uncertain", "message": "verify in Crew"})
        ),
    )
    outcome = execute_crew_write("update_bill", {"input": {"billId": "b1"}})
    assert outcome["ok"] is False
    assert outcome["error"] == "uncertain"
    assert outcome["retry_allowed"] is False


def test_unknown_operation_is_blocked_before_subprocess(monkeypatch):
    def should_not_run(*args, **kwargs):
        raise AssertionError("must not shell out for unknown ops")

    monkeypatch.setattr(subprocess, "run", should_not_run)
    outcome = execute_crew_write("delete_everything", {})
    assert outcome["ok"] is False
    assert outcome["error"] == "blocked"


def test_crewwrite_binary_required(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda cmd, timeout=None, capture_output=True, **kwargs: _fake_run(1, ""),
    )
    outcome = execute_crew_write("update_bill", {"input": {"billId": "b1"}})
    assert outcome["ok"] is False
