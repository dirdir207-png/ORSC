from datetime import date

import pytest

from meridian.contracts import (
    Contract,
    ContractRepository,
    Obligation,
    advisory_boundary,
    contract_events,
)


def test_contract_events_include_renewal_cancellation_escalation_and_obligation(
    tmp_path,
):
    repository = ContractRepository(str(tmp_path / "memory.db"))
    contract = repository.save_contract(
        Contract(
            id=None,
            kind="lease",
            name="Apartment lease",
            starts_on="2026-01-01",
            ends_on="2026-12-31",
            renews_on="2027-01-01",
            cancel_by="2026-11-30",
            escalation_percent=3.0,
            deductible=None,
            evidence_id=20,
            evidence_span="pages 1 and 8",
            confidence=0.96,
        )
    )
    obligation = repository.save_obligation(
        Obligation(
            id=None,
            contract_id=contract.id,
            name="Rent",
            amount=1800,
            due_on="2026-09-01",
            recurrence="monthly",
            commitment_id=4,
            evidence_id=21,
            evidence_span="page 2, rent clause",
            confidence=0.99,
        )
    )

    events = contract_events(contract, [obligation], as_of=date(2026, 8, 20))

    assert {event.kind for event in events} >= {
        "obligation_due",
        "cancellation_deadline",
        "renewal",
        "escalation_review",
    }
    assert all(event.evidence_id in {20, 21} for event in events)


@pytest.mark.parametrize("kind", ["medical", "insurance", "lease", "tax"])
def test_sensitive_contracts_quote_financial_facts_without_professional_determinations(
    kind,
):
    contract = Contract(
        id=1,
        kind=kind,
        name="Sensitive document",
        starts_on="2026-01-01",
        ends_on="2026-12-31",
        renews_on=None,
        cancel_by="2026-11-01",
        escalation_percent=None,
        deductible=500,
        evidence_id=3,
        evidence_span="quoted clause",
        confidence=0.9,
    )

    summary = advisory_boundary(contract)

    assert summary.quoted_facts["deductible"] == 500
    assert summary.deadlines == ("2026-11-01", "2026-12-31")
    assert summary.determinations == ()
    assert "not medical, legal, coverage, or tax advice" in summary.disclaimer.lower()


def test_update_and_delete_contract_cascades_obligations(tmp_path):
    db = str(tmp_path / "c.db")
    repo = ContractRepository(db)
    saved = repo.save_contract(Contract(
        id=None, kind="lease", name="Apartment lease", starts_on="2026-01-01",
        ends_on="2026-12-31", renews_on=None, cancel_by="2026-11-30",
        escalation_percent=3.0, deductible=None,
        evidence_id=None, evidence_span="owner", confidence=1.0,
    ))
    repo.save_obligation(Obligation(
        id=None, contract_id=saved.id, name="Rent", amount=1800.0,
        due_on="2026-09-01", recurrence="monthly", commitment_id=None,
        evidence_id=None, evidence_span="owner", confidence=1.0,
    ))
    updated = repo.update_contract(Contract(
        id=saved.id, kind="lease", name="Apartment lease", starts_on="2026-01-01",
        ends_on="2027-12-31", renews_on=None, cancel_by="2027-11-30",
        escalation_percent=3.0, deductible=None,
        evidence_id=None, evidence_span="owner", confidence=1.0,
    ))
    assert updated.ends_on == "2027-12-31"
    repo.delete_contract(saved.id)
    assert repo.list_contracts() == []
    assert repo.list_obligations(saved.id) == []


def test_replace_obligations_replaces_stale(tmp_path):
    db = str(tmp_path / "c.db")
    repo = ContractRepository(db)
    contract = repo.save_contract(Contract(
        id=None, kind="insurance", name="Car policy", starts_on="2026-01-01",
        ends_on="2026-12-31", renews_on=None, cancel_by=None,
        escalation_percent=None, deductible=500.0,
        evidence_id=None, evidence_span="owner", confidence=1.0,
    ))
    repo.save_obligation(Obligation(
        id=None, contract_id=contract.id, name="Premium", amount=120.0,
        due_on="2026-09-01", recurrence="monthly", commitment_id=None,
        evidence_id=None, evidence_span="owner", confidence=1.0,
    ))
    result = repo.replace_obligations(contract.id, [
        Obligation(id=None, contract_id=contract.id, name="Premium", amount=125.0,
                   due_on="2026-10-01", recurrence="monthly", commitment_id=None,
                   evidence_id=None, evidence_span="owner", confidence=1.0),
    ])
    assert len(result) == 1 and result[0].amount == 125.0
