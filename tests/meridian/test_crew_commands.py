import pytest

from meridian.crew_commands import build_command_payload, command_spec


def test_create_pocket_command_builds_cents_payload_without_secrets():
    operation, query, variables = build_command_payload(
        "create_pocket",
        {
            "account_id": "checking-1",
            "name": "Emergency Fund",
            "target_amount": 10000.0,
            "initial_amount": 200.0,
            "note": "Build a safety buffer",
        },
    )

    assert operation == "CreateSubaccount"
    assert query.startswith("mutation CreateSubaccount")
    assert variables == {
        "input": {
            "type": "SAVINGS",
            "piggyBanked": False,
            "accountId": "checking-1",
            "name": "Emergency Fund",
            "targetAmount": 1000000,
            "initialTransferAmount": 20000,
            "note": "Build a safety buffer",
        }
    }
    assert "token" not in str(variables).lower()


def test_delete_pocket_command_requires_a_sanitized_crew_id():
    operation, query, variables = build_command_payload(
        "delete_pocket", {"subaccount_id": "pocket-7"}
    )

    assert operation == "DeleteSubaccount"
    assert query.startswith("mutation DeleteSubaccount")
    assert variables == {"id": "pocket-7"}


def test_create_bill_command_builds_reviewable_cents_payload():
    operation, query, variables = build_command_payload(
        "create_bill",
        {
            "account_id": "checking-1",
            "name": "Internet",
            "amount": 89.99,
            "anchor_date": "2026-09-28",
            "frequency": "MONTHLY",
            "frequency_interval": 1,
            "auto_adjust_amount": True,
        },
    )

    assert operation == "CreateBill"
    assert query.startswith("mutation CreateBill")
    assert variables["input"] == {
        "accountId": "checking-1",
        "amount": 8999,
        "anchorDate": "2026-09-28",
        "frequency": "MONTHLY",
        "frequencyInterval": 1,
        "autoAdjustAmount": True,
        "paused": False,
        "name": "Internet",
    }


def test_delete_bill_command_requires_a_bill_id():
    operation, query, variables = build_command_payload(
        "delete_bill", {"bill_id": "bill-4"}
    )

    assert operation == "DeleteBill"
    assert query.startswith("mutation DeleteBill")
    assert variables == {"id": "bill-4"}


def test_create_autopilot_rule_builds_deposit_trigger_formula():
    operation, query, variables = build_command_payload(
        "create_autopilot_rule",
        {
            "name": "Sweep deposits",
            "account_id": "account-1",
            "subaccount_id": "pocket-2",
            "round_to_nearest": 100,
        },
    )

    assert operation == "CreateRoundUpRule"
    assert query.startswith("mutation CreateRoundUpRule")
    assert variables == {
        "input": {
            "name": "Sweep deposits",
            "formula": {
                "name": "Sweep deposits",
                "description": "Round up transactions to the nearest dollar",
                "triggers": ["CASH_TRANSACTION_OCCURRED"],
                "actions": [
                    {
                        "roundUpTransfer": {
                            "accountId": "account-1",
                            "roundToNearest": 100,
                            "accountType": "ACCOUNT",
                            "subaccountId": "pocket-2",
                        }
                    }
                ],
            },
        }
    }


def test_edit_autopilot_rule_requires_rule_id_and_supports_card_filters():
    operation, query, variables = build_command_payload(
        "edit_autopilot_rule",
        {
            "rule_id": "rule-7",
            "name": "Card roundups",
            "account_id": "account-1",
            "card_ids": ["card-1", "card-2"],
            "enabled": False,
            "round_to_nearest": 100,
        },
    )

    assert operation == "EditRoundUpRule"
    assert query.startswith("mutation EditRoundUpRule")
    assert variables["input"]["ruleId"] == "rule-7"
    assert variables["input"]["enabled"] is False
    assert variables["input"]["formula"]["triggers"] == ["DEBIT_CARD_TRANSACTION"]
    assert variables["input"]["formula"]["conditions"] == {
        "or": {
            "conditions": [
                {"idMatch": {"entityId": "card-1", "entitySchema": "DEBIT_CARDS"}},
                {"idMatch": {"entityId": "card-2", "entitySchema": "DEBIT_CARDS"}},
            ]
        }
    }


def test_delete_autopilot_rule_command_requires_rule_id():
    operation, query, variables = build_command_payload(
        "delete_autopilot_rule", {"rule_id": "rule-9"}
    )
    assert operation == "DeleteRule"
    assert query.startswith("mutation DeleteRule")
    assert variables == {"input": {"ruleId": "rule-9"}}


def test_set_spend_pocket_command_builds_account_scoped_payload():
    operation, query, variables = build_command_payload(
        "set_spend_pocket",
        {"user_id": "user-1", "subaccount_id": "pocket-2"},
    )
    assert operation == "SetActiveSpendPocketScottie"
    assert query.startswith("mutation SetActiveSpendPocketScottie")
    assert variables == {
        "input": {
            "userId": "user-1",
            "selectedSpendSubaccountId": "pocket-2",
        }
    }


def test_update_virtual_card_command_builds_card_scoped_payload():
    operation, query, variables = build_command_payload(
        "update_virtual_card",
        {"debit_card_id": "card-1", "subaccount_id": "pocket-2"},
    )
    assert operation == "UpdateVirtualDebitCard"
    assert query.startswith("mutation UpdateVirtualDebitCard")
    assert variables == {
        "input": {"debitCardId": "card-1", "subaccountId": "pocket-2"}
    }


@pytest.mark.parametrize(
    "kind, params",
    [
        ("create_pocket", {"name": "Missing account"}),
        ("create_pocket", {"account_id": "a", "name": "", "initial_amount": 1}),
        ("delete_pocket", {}),
        ("create_bill", {"name": "Missing amount"}),
        ("delete_bill", {}),
        ("set_spend_pocket", {}),
        ("update_virtual_card", {}),
        ("unknown", {}),
    ],
)
def test_crew_command_payload_rejects_incomplete_or_unknown_commands(kind, params):
    with pytest.raises(ValueError):
        build_command_payload(kind, params)


def test_command_spec_is_mutation_and_has_a_readback_key():
    spec = command_spec("create_pocket")
    assert spec.operation_name == "CreateSubaccount"
    assert spec.is_mutation is True
    assert spec.readback_key == "createSubaccount"
