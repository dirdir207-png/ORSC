from datetime import date

from meridian.assets import Asset, AssetRepository
from meridian.contracts import Contract, ContractRepository
from meridian.services.memory import build_memory


def test_memory_composes_attention_reserves_and_structure_with_evidence_links(tmp_path):
    db_path = str(tmp_path / "memory.db")
    assets = AssetRepository(db_path)
    assets.save_asset(
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
            evidence_span="receipt",
            confidence=0.98,
        )
    )
    contracts = ContractRepository(db_path)
    contracts.save_contract(
        Contract(
            id=None,
            kind="insurance",
            name="Home policy",
            starts_on="2026-01-01",
            ends_on="2026-12-31",
            renews_on="2027-01-01",
            cancel_by="2026-11-30",
            escalation_percent=None,
            deductible=1000,
            evidence_id=10,
            evidence_span="declarations",
            confidence=0.96,
        )
    )

    result = build_memory(db_path, as_of=date(2026, 8, 20))

    assert result["today"][0]["kind"] == "return_deadline"
    assert result["plan"][0]["amount"] == 1200
    assert result["accounts"]["assets"][0]["name"] == "Laptop"
    assert result["accounts"]["contracts"][0]["name"] == "Home policy"
    assert all("why_it_matters" in item for item in result["today"])
    assert all("evidence_url" in item for item in result["today"])
