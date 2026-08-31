def test_seed_creates_assets_contracts_and_evidence(tmp_path, monkeypatch):
    import importlib
    import os

    db_path = str(tmp_path / "preview.db")
    monkeypatch.setenv("DB_FILE", db_path)
    seed_preview = importlib.import_module("seed_preview")
    seed_preview.DB = db_path
    seed_preview.seed()

    from meridian.assets import AssetRepository
    from meridian.contracts import ContractRepository
    from meridian.evidence import EvidenceRepository

    assert len(AssetRepository(db_path).list_assets()) == 2
    assert len(ContractRepository(db_path).list_contracts()) == 2
    assert len(EvidenceRepository(db_path)._connect().execute(
        "SELECT id FROM evidence_items").fetchall()) >= 2
