from datetime import date

from meridian.assets import Asset, AssetRepository, Warranty, asset_events


def test_asset_lifecycle_events_keep_evidence_provenance(tmp_path):
    repository = AssetRepository(str(tmp_path / "memory.db"))
    asset = repository.save_asset(
        Asset(
            id=None,
            name="Laptop",
            category="electronics",
            purchased_on="2026-08-01",
            purchase_price=1500,
            return_until="2026-08-31",
            maintenance_interval_days=180,
            replacement_reserve=1200,
            evidence_id=9,
            evidence_span="page 1, order total",
            confidence=0.98,
        )
    )
    warranty = repository.save_warranty(
        Warranty(
            id=None,
            asset_id=asset.id,
            provider="Maker Care",
            expires_on="2027-08-01",
            deductible=99,
            evidence_id=10,
            evidence_span="page 2, warranty term",
            confidence=0.95,
        )
    )

    events = asset_events(asset, [warranty], as_of=date(2026, 8, 20))

    assert {event.kind for event in events} == {
        "return_deadline",
        "maintenance_due",
        "warranty_expiration",
        "replacement_reserve",
    }
    assert all(event.evidence_id in {9, 10} for event in events)


def test_source_document_correction_is_audited_and_proposed_not_applied(tmp_path):
    repository = AssetRepository(str(tmp_path / "memory.db"))
    asset = repository.save_asset(
        Asset(
            id=None,
            name="Phone",
            category="electronics",
            purchased_on="2026-08-01",
            purchase_price=900,
            return_until="2026-08-15",
            maintenance_interval_days=None,
            replacement_reserve=None,
            evidence_id=1,
            evidence_span="receipt total",
            confidence=0.9,
        )
    )

    proposal = repository.propose_correction(
        asset.id, field="purchase_price", proposed_value="950", evidence_id=2
    )

    assert proposal.requires_approval is True
    assert repository.get_asset(asset.id).purchase_price == 900
    assert repository.list_corrections(asset.id)[0] == proposal


def test_update_asset_persists_changed_fields(tmp_path):
    repo = AssetRepository(str(tmp_path / "a.db"))
    saved = repo.save_asset(Asset(
        id=None, name="Laptop", category="electronics",
        purchased_on=None, purchase_price=1500.0, return_until=None,
        maintenance_interval_days=None, replacement_reserve=1200.0,
        evidence_id=None, evidence_span="receipt", confidence=0.98,
    ))
    updated = repo.update_asset(Asset(
        id=saved.id, name="Laptop", category="electronics",
        purchased_on=None, purchase_price=1400.0, return_until=None,
        maintenance_interval_days=180, replacement_reserve=1000.0,
        evidence_id=None, evidence_span="receipt", confidence=1.0,
    ))
    assert updated.id == saved.id
    assert updated.purchase_price == 1400.0
    assert repo.get_asset(saved.id).maintenance_interval_days == 180


def test_delete_asset_cascades_warranties(tmp_path):
    db = str(tmp_path / "a.db")
    repo = AssetRepository(db)
    saved = repo.save_asset(Asset(
        id=None, name="Bike", category="sport", purchased_on=None,
        purchase_price=800.0, return_until=None, maintenance_interval_days=None,
        replacement_reserve=None, evidence_id=None, evidence_span="owner", confidence=1.0,
    ))
    repo.save_warranty(Warranty(
        id=None, asset_id=saved.id, provider="VendorCo",
        expires_on="2027-01-01", deductible=100.0,
        evidence_id=None, evidence_span="owner", confidence=1.0,
    ))
    repo.delete_asset(saved.id)
    assert repo.get_asset(saved.id) is None
    assert repo.list_warranties(saved.id) == []


def test_replace_warranties_replaces_stale(tmp_path):
    db = str(tmp_path / "a.db")
    repo = AssetRepository(db)
    asset = repo.save_asset(Asset(
        id=None, name="Phone", category="electronics", purchased_on=None,
        purchase_price=900.0, return_until=None, maintenance_interval_days=None,
        replacement_reserve=None, evidence_id=None, evidence_span="owner", confidence=1.0,
    ))
    old = repo.save_warranty(Warranty(
        id=None, asset_id=asset.id, provider="OldCo", expires_on="2026-09-01",
        deductible=50.0, evidence_id=None, evidence_span="owner", confidence=1.0,
    ))
    result = repo.replace_warranties(asset.id, [
        Warranty(id=None, asset_id=asset.id, provider="NewCo", expires_on="2027-09-01",
                 deductible=75.0, evidence_id=None, evidence_span="owner", confidence=1.0),
    ])
    assert len(result) == 1 and result[0].provider == "NewCo"
    assert all(w.id != old.id for w in repo.list_warranties(asset.id))
