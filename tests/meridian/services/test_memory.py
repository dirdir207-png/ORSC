from datetime import date

from meridian.assets import Asset, AssetRepository
from meridian.contracts import Contract, ContractRepository
from meridian.evidence import EvidenceRepository, _now
from meridian.services.memory import build_memory


def _seed(db_path):
    evidence = EvidenceRepository(db_path)
    receipt = evidence.add_item(
        source_kind="manual", source_id="seed-receipt", content_hash="a" * 64,
        mime_type="text/plain", size_bytes=14, title="receipt",
    )
    assets = AssetRepository(db_path)
    saved_asset = assets.save_asset(Asset(
        id=None, name="Laptop", category="electronics", purchased_on="2026-08-01",
        purchase_price=1500, return_until="2026-08-31", maintenance_interval_days=180,
        replacement_reserve=1200, evidence_id=receipt.id, evidence_span="receipt",
        confidence=0.98,
    ))
    assets.save_warranty(_warranty(saved_asset.id))
    contracts = ContractRepository(db_path)
    contracts.save_contract(Contract(
        id=None, kind="insurance", name="Home policy", starts_on="2026-01-01",
        ends_on="2026-12-31", renews_on="2027-01-01", cancel_by="2026-11-30",
        escalation_percent=None, deductible=1000, evidence_id=None,
        evidence_span="declarations", confidence=0.96,
    ))
    return saved_asset, receipt


def _warranty(asset_id):
    from meridian.assets import Warranty
    return Warranty(
        id=None, asset_id=asset_id, provider="VendorCo", expires_on="2027-01-01",
        deductible=100.0, evidence_id=None, evidence_span="owner", confidence=1.0,
    )


def test_today_memory_orders_by_urgency_and_carries_evidence(tmp_path):
    db_path = str(tmp_path / "m.db")
    _seed(db_path)
    result = build_memory(db_path, "today", as_of=date(2026, 8, 20))
    assert result["workspace"] == "today"
    kinds = [item["kind"] for item in result["items"]]
    assert kinds[0] == "return_deadline"  # overdue first
    first = result["items"][0]
    assert first["why_it_matters"]
    assert first["evidence"][0]["span"] == "receipt"
    assert first["evidence"][0]["confidence"] == 0.98
    assert all("reference_transaction_id" in item for item in result["items"])


def test_plan_memory_reserves_and_obligations_with_escalation_field(tmp_path):
    db_path = str(tmp_path / "m.db")
    _seed(db_path)
    result = build_memory(db_path, "plan", as_of=date(2026, 8, 20))
    kinds = {item["kind"] for item in result["items"]}
    assert "replacement_reserve" in kinds
    reserve = next(i for i in result["items"] if i["kind"] == "replacement_reserve")
    assert reserve["amount"] == 1200
    assert "escalation_percent" in reserve  # always present, possibly None


def test_activity_memory_lists_lifecycle_events_without_transactions(tmp_path):
    db_path = str(tmp_path / "m.db")
    _seed(db_path)
    result = build_memory(db_path, "activity", as_of=date(2026, 8, 20))
    assert result["workspace"] == "activity"
    assert all(item["reference_transaction_id"] is None for item in result["items"])


def test_accounts_memory_assets_contracts_with_nested_children(tmp_path):
    db_path = str(tmp_path / "m.db")
    _seed(db_path)
    result = build_memory(db_path, "accounts", as_of=date(2026, 8, 20))
    kinds = {item["kind"] for item in result["items"]}
    assert {"asset", "contract"} <= kinds
    asset = next(i for i in result["items"] if i["kind"] == "asset")
    assert asset["warranties"][0]["provider"] == "VendorCo"


def test_unknown_workspace_raises(tmp_path):
    db_path = str(tmp_path / "m.db")
    _seed(db_path)
    try:
        build_memory(db_path, "nope")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_expired_evidence_is_omitted_but_live_evidence_remains(tmp_path):
    db_path = str(tmp_path / "m.db")
    _seed(db_path)
    evidence = EvidenceRepository(db_path)
    expired = evidence.add_item(
        source_kind="manual", source_id="seed-expired", content_hash="b" * 64,
        mime_type="text/plain", size_bytes=10, title="expired", expires_at=_now(),
    )
    assets = AssetRepository(db_path)
    assets.save_asset(Asset(
        id=None, name="Old printer", category="electronics", purchased_on="2026-08-01",
        purchase_price=200, return_until="2026-08-25", maintenance_interval_days=180,
        replacement_reserve=0, evidence_id=expired.id, evidence_span="expired",
        confidence=0.9,
    ))

    result = build_memory(db_path, "today", as_of=date(2026, 8, 20))
    printer = next(i for i in result["items"] if "Old printer" in i["title"])
    laptop = next(i for i in result["items"] if "Laptop" in i["title"])
    assert printer["evidence"] == []  # materialized-expired evidence hidden
    assert laptop["evidence"][0]["span"] == "receipt"  # live evidence still appears


def test_escalation_review_carries_percent_in_dedicated_field(tmp_path):
    from meridian.contracts import Contract, ContractRepository

    db_path = str(tmp_path / "m.db")
    _seed(db_path)
    ContractRepository(db_path).save_contract(Contract(
        id=None, kind="lease", name="Apartment lease", starts_on="2026-07-01",
        ends_on="2027-06-30", renews_on="2027-06-15", cancel_by="2027-05-01",
        escalation_percent=3.0, deductible=None, evidence_id=None,
        evidence_span="owner", confidence=1.0,
    ))
    result = build_memory(db_path, "today", as_of=date(2026, 8, 20))
    escalation = next(i for i in result["items"] if i["kind"] == "escalation_review")
    assert escalation["escalation_percent"] == 3.0
    assert escalation["amount"] is None
