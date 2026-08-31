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
