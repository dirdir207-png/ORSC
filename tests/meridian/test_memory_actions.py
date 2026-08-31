from crew.actions import ActionStore
from crew.executors import ExecutorSpec, execute_approved_action
from meridian.evidence import EvidenceRepository
from meridian.memory_actions import (
    MEMORY_ACTION_TYPES,
    asset_executors,
    contract_executors,
)


def _store_and_executors(db_path):
    store = ActionStore(db_path, allowed_types=MEMORY_ACTION_TYPES)
    executors = {
        **asset_executors(db_path),
        **contract_executors(db_path),
    }
    wrapped = {key: ExecutorSpec(execute=fn, verifier=vf) for key, (fn, vf) in executors.items()}
    return store, wrapped


def test_create_asset_propose_approve_execute_verify(tmp_path):
    db_path = str(tmp_path / "a.db")
    store, executors = _store_and_executors(db_path)
    request = store.propose(
        "create_asset",
        {"name": "Laptop", "category": "electronics", "purchase_price": 1500.0,
         "replacement_reserve": 1200.0, "evidence_span": "owner", "confidence": 1.0},
        "Owner records laptop",
        requested_by="owner",
    )
    store.approve(request["id"], decided_by="owner")
    result = execute_approved_action(store, request["id"], executors)
    assert result["state"] == "verified"
    assert result["result"]["asset_id"]
    from meridian.assets import AssetRepository
    assert AssetRepository(db_path).get_asset(result["result"]["asset_id"]).name == "Laptop"


def test_update_asset_changes_fields(tmp_path):
    from meridian.assets import Asset, AssetRepository

    db_path = str(tmp_path / "u.db")
    repo = AssetRepository(db_path)
    saved = repo.save_asset(Asset(
        id=None, name="Laptop", category="electronics", purchased_on=None,
        purchase_price=1500.0, return_until=None, maintenance_interval_days=None,
        replacement_reserve=1200.0, evidence_id=None, evidence_span="owner", confidence=1.0,
    ))
    store, executors = _store_and_executors(db_path)
    request = store.propose(
        "update_asset",
        {"record_id": saved.id, "name": "Laptop Pro", "category": "electronics",
         "purchase_price": 1400.0, "evidence_span": "owner", "confidence": 1.0,
         "change_reason": "price corrected"},
        "Owner corrects price",
        requested_by="owner",
    )
    store.approve(request["id"], decided_by="owner")
    result = execute_approved_action(store, request["id"], executors)
    assert result["state"] == "verified"
    assert repo.get_asset(saved.id).purchase_price == 1400.0


def test_delete_asset_unlinks_evidence_but_keeps_items(tmp_path):
    from meridian.assets import Asset, AssetRepository

    db_path = str(tmp_path / "d.db")
    repo = AssetRepository(db_path)
    saved = repo.save_asset(Asset(
        id=None, name="Bike", category="sport", purchased_on=None,
        purchase_price=800.0, return_until=None, maintenance_interval_days=None,
        replacement_reserve=None, evidence_id=None, evidence_span="owner", confidence=1.0,
    ))
    evidence = EvidenceRepository(db_path)
    item = evidence.add_item(source_kind="manual", source_id="seed-1",
                             content_hash="b" * 64, mime_type="text/plain", size_bytes=3)
    evidence.add_link(evidence_id=item.id, target_kind="asset",
                      target_id=str(saved.id), relation="supports", provenance="owner")
    store, executors = _store_and_executors(db_path)
    request = store.propose("delete_asset", {"record_id": saved.id, "change_reason": "sold"},
                            "Owner removes bike", requested_by="owner")
    store.approve(request["id"], decided_by="owner")
    result = execute_approved_action(store, request["id"], executors)
    assert result["state"] == "verified"
    assert repo.get_asset(saved.id) is None
    assert evidence.list_links_for_target("asset", str(saved.id)) == []
    assert evidence.get_item(item.id) is not None


def test_illegal_transition_without_approval(tmp_path):
    db_path = str(tmp_path / "i.db")
    store, executors = _store_and_executors(db_path)
    request = store.propose("create_contract",
                            {"kind": "insurance", "name": "Car", "confidence": 1.0},
                            "test", requested_by="owner")
    from crew.actions import IllegalTransitionError
    try:
        execute_approved_action(store, request["id"], executors)
        raise AssertionError("expected IllegalTransitionError")
    except IllegalTransitionError:
        pass


def test_create_contract_propose_approve_execute_verify(tmp_path):
    db_path = str(tmp_path / "c.db")
    store, executors = _store_and_executors(db_path)
    request = store.propose(
        "create_contract",
        {"kind": "insurance", "name": "Car policy", "starts_on": "2026-01-01",
         "escalation_percent": 3.0, "deductible": 500.0,
         "evidence_span": "owner", "confidence": 1.0},
        "Owner records car policy",
        requested_by="owner",
    )
    store.approve(request["id"], decided_by="owner")
    result = execute_approved_action(store, request["id"], executors)
    assert result["state"] == "verified"
    assert result["result"]["contract_id"]
    from meridian.contracts import ContractRepository
    record = ContractRepository(db_path).get_contract(result["result"]["contract_id"])
    assert record.name == "Car policy"
    assert record.kind == "insurance"
    assert record.escalation_percent == 3.0


def test_update_contract_changes_fields(tmp_path):
    from meridian.contracts import Contract, ContractRepository

    db_path = str(tmp_path / "u.db")
    repo = ContractRepository(db_path)
    saved = repo.save_contract(Contract(
        id=None, kind="insurance", name="Home policy", starts_on="2026-01-01",
        ends_on="2026-12-31", renews_on=None, cancel_by=None,
        escalation_percent=None, deductible=1000.0, evidence_id=None,
        evidence_span="owner", confidence=1.0,
    ))
    store, executors = _store_and_executors(db_path)
    request = store.propose(
        "update_contract",
        {"record_id": saved.id, "name": "Home policy premium", "deductible": 1200.0,
         "evidence_span": "owner", "confidence": 1.0, "change_reason": "deductible changed"},
        "Owner updates policy",
        requested_by="owner",
    )
    store.approve(request["id"], decided_by="owner")
    result = execute_approved_action(store, request["id"], executors)
    assert result["state"] == "verified"
    updated = repo.get_contract(saved.id)
    assert updated.name == "Home policy premium"
    assert updated.deductible == 1200.0
    assert updated.kind == "insurance"  # untouched field preserved by the merge


def test_delete_contract_unlinks_evidence_but_keeps_items(tmp_path):
    from meridian.contracts import Contract, ContractRepository, Obligation

    db_path = str(tmp_path / "d.db")
    repo = ContractRepository(db_path)
    saved = repo.save_contract(Contract(
        id=None, kind="subscription", name="Streaming", starts_on="2026-01-01",
        ends_on=None, renews_on="2027-01-01", cancel_by=None,
        escalation_percent=None, deductible=None, evidence_id=None,
        evidence_span="owner", confidence=1.0,
    ))
    repo.save_obligation(Obligation(
        id=None, contract_id=saved.id, name="Monthly fee", amount=15.99,
        due_on="2026-09-01", recurrence="monthly", commitment_id=None,
        evidence_id=None, evidence_span="owner", confidence=1.0,
    ))
    evidence = EvidenceRepository(db_path)
    item = evidence.add_item(source_kind="manual", source_id="seed-2",
                             content_hash="c" * 64, mime_type="text/plain", size_bytes=3)
    evidence.add_link(evidence_id=item.id, target_kind="contract",
                      target_id=str(saved.id), relation="supports", provenance="owner")
    store, executors = _store_and_executors(db_path)
    request = store.propose("delete_contract", {"record_id": saved.id, "change_reason": "cancelled"},
                            "Owner removes contract", requested_by="owner")
    store.approve(request["id"], decided_by="owner")
    result = execute_approved_action(store, request["id"], executors)
    assert result["state"] == "verified"
    assert repo.get_contract(saved.id) is None
    assert repo.list_contracts() == []
    assert repo.list_obligations() == []  # cascade via FK
    assert evidence.list_links_for_target("contract", str(saved.id)) == []
    assert evidence.get_item(item.id) is not None  # evidence item kept


def test_update_asset_single_field(tmp_path):
    from meridian.assets import Asset, AssetRepository

    db_path = str(tmp_path / "p.db")
    repo = AssetRepository(db_path)
    saved = repo.save_asset(Asset(
        id=None, name="Laptop", category="electronics", purchased_on=None,
        purchase_price=1500.0, return_until=None, maintenance_interval_days=None,
        replacement_reserve=1200.0, evidence_id=None, evidence_span="owner", confidence=1.0,
    ))
    store, executors = _store_and_executors(db_path)
    request = store.propose(
        "update_asset",
        {"record_id": saved.id, "replacement_reserve": 1000.0},
        "Owner adjusts reserve",
        requested_by="owner",
    )
    store.approve(request["id"], decided_by="owner")
    result = execute_approved_action(store, request["id"], executors)
    assert result["state"] == "verified"
    updated = repo.get_asset(saved.id)
    assert updated.replacement_reserve == 1000.0  # only the sent field changed
    assert updated.name == "Laptop"
    assert updated.purchase_price == 1500.0


def test_create_asset_persists_nested_warranties(tmp_path):
    from meridian.assets import AssetRepository

    db_path = str(tmp_path / "w.db")
    store, executors = _store_and_executors(db_path)
    request = store.propose(
        "create_asset",
        {"name": "Laptop", "category": "electronics", "purchase_price": 1500.0,
         "evidence_span": "owner", "confidence": 1.0,
         "warranties": [{"provider": "VendorCo", "expires_on": "2027-08-01",
                         "deductible": 100.0, "evidence_span": "owner", "confidence": 1.0}]},
        "Owner records laptop with warranty",
        requested_by="owner",
    )
    store.approve(request["id"], decided_by="owner")
    result = execute_approved_action(store, request["id"], executors)
    assert result["state"] == "verified"
    warranties = AssetRepository(db_path).list_warranties(result["result"]["asset_id"])
    assert [w.provider for w in warranties] == ["VendorCo"]
    assert warranties[0].deductible == 100.0


def test_create_contract_persists_nested_obligations(tmp_path):
    from meridian.contracts import ContractRepository

    db_path = str(tmp_path / "o.db")
    store, executors = _store_and_executors(db_path)
    request = store.propose(
        "create_contract",
        {"kind": "subscription", "name": "Streaming", "evidence_span": "owner",
         "confidence": 1.0,
         "obligations": [{"name": "Monthly fee", "amount": 15.99,
                          "due_on": "2026-09-01", "recurrence": "monthly",
                          "evidence_span": "owner", "confidence": 1.0}]},
        "Owner records streaming contract",
        requested_by="owner",
    )
    store.approve(request["id"], decided_by="owner")
    result = execute_approved_action(store, request["id"], executors)
    assert result["state"] == "verified"
    obligations = ContractRepository(db_path).list_obligations(result["result"]["contract_id"])
    assert [o.name for o in obligations] == ["Monthly fee"]
    assert obligations[0].amount == 15.99
