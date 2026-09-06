"""Tests for R24 deposit discovery."""

from meridian.deposit_discovery import discover_deposits


def _txn(eid, acct, amount, desc, occurred="2026-09-01"):
    return {"external_id": eid, "account_external_id": acct, "amount": amount, "occurred_at": occurred, "description": desc}


def test_recognizes_payroll_high_confidence():
    txs = (_txn("t1", "a1", 2500.0, "Direct Deposit Payroll"),)
    result = discover_deposits(txs, connected_account_ids=("a1",))
    assert len(result.candidates) == 1
    assert result.candidates[0].confidence == 0.95
    assert result.candidates[0].kind == "recurring_income"
    assert "owner confirmation required" in result.note


def test_owned_transfer_is_low_confidence_not_income():
    txs = (_txn("t2", "a1", 500.0, "Transfer from Chime Savings"),)
    result = discover_deposits(txs, connected_account_ids=("a1",))
    assert result.candidates[0].confidence == 0.30
    assert result.candidates[0].kind == "transfer"


def test_unconnected_accounts_excluded():
    txs = (_txn("t3", "a9", 100.0, "Direct Deposit Payroll"),)
    result = discover_deposits(txs, connected_account_ids=("a1",))
    assert result.candidates == ()


def test_debits_excluded():
    txs = (_txn("t4", "a1", -50.0, "Payment"),)
    result = discover_deposits(txs, connected_account_ids=("a1",))
    assert result.candidates == ()


def test_sorted_by_confidence():
    txs = (
        _txn("t5", "a1", 100.0, "Random deposit"),
        _txn("t6", "a1", 200.0, "Direct Deposit Payroll"),
    )
    result = discover_deposits(txs, connected_account_ids=("a1",))
    assert [c.transaction_external_id for c in result.candidates] == ["t6", "t5"]
