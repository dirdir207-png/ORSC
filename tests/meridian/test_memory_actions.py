from crew.actions import ActionStore
from crew.executors import ExecutorSpec, execute_approved_action
from meridian.evidence import EvidenceRepository
from meridian.memory_actions import MEMORY_ACTION_TYPES, asset_executors, contract_executors


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
