from meridian.mutations import reconcile_crew_mutation


def test_confirmed_crew_mutation_is_marked_reconciled_after_successful_readback():
    calls = []

    def refresh():
        calls.append(True)
        return {"status": "complete", "accounts_synced": 2, "transactions_synced": 1}

    result = reconcile_crew_mutation(
        {"success": True, "result": {"id": "transfer-1"}}, refresh
    )

    assert calls == [True]
    assert result["reconciliation"] == {
        "state": "reconciled",
        "transfer_id": "transfer-1",
        "accounts_synced": 2,
        "transactions_synced": 1,
    }


def test_confirmed_crew_mutation_stays_pending_when_readback_fails_without_retry():
    calls = []

    def refresh():
        calls.append(True)
        raise OSError("Crew read unavailable")

    result = reconcile_crew_mutation(
        {"success": True, "result": {"id": "transfer-2"}}, refresh
    )

    assert calls == [True]
    assert result["reconciliation"] == {
        "state": "pending_reconciliation",
        "transfer_id": "transfer-2",
        "verify_state": True,
    }
    assert result["success"] is True


def test_failed_or_unconfirmed_mutation_never_triggers_readback():
    calls = []

    def refresh():
        calls.append(True)
        return {"status": "complete"}

    assert reconcile_crew_mutation({"error_code": "uncertain_write"}, refresh) == {
        "error_code": "uncertain_write"
    }
    assert reconcile_crew_mutation(
        {"success": True, "result": {"id": ""}}, refresh
    ) == {"success": True, "result": {"id": ""}}
    assert calls == []
