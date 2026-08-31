from meridian.documents.extract import ExtractedDocument, ExtractedValue, Provenance
from meridian.documents.reconcile import reconcile_document
from meridian.repository import FinancialRepository


def _document(text, amount, *, field="amount_due"):
    return ExtractedDocument(
        "bill",
        text,
        (
            ExtractedValue(
                field,
                amount,
                0.98,
                Provenance(1, "line:2", f"Amount due: ${amount:.2f}"),
            ),
        ),
        (),
    )


def _transaction(repository, *, external_id, amount, merchant, occurred_at):
    accounts = repository.list_accounts()
    account = (
        accounts[0]
        if accounts
        else repository.upsert_account(
            provider="crew",
            external_id="checking",
            name="Checking",
            account_type="checking",
            balance=1000,
        )
    )
    return repository.upsert_transaction(
        provider="crew",
        external_id=external_id,
        account_id=account.id,
        amount=amount,
        occurred_at=occurred_at,
        description=merchant,
        merchant=merchant,
        status="posted",
    )


def test_exact_bill_match_returns_evidence_bound_chain_without_changing_totals(
    tmp_path,
):
    repository = FinancialRepository(str(tmp_path / "graph.db"))
    charge = _transaction(
        repository,
        external_id="charge",
        amount=-84.12,
        merchant="City Water",
        occurred_at="2026-08-20T12:00:00Z",
    )
    before = sum(item.amount for item in repository.list_transactions(limit=200)[0])

    result = reconcile_document(
        _document("CITY WATER\nAmount due: $84.12", 84.12),
        repository,
        evidence_id=7,
    )

    assert result.status == "matched"
    assert result.matches[0].transaction_id == charge.id
    assert result.matches[0].evidence_id == 7
    assert result.matches[0].confidence >= 0.95
    assert (
        sum(item.amount for item in repository.list_transactions(limit=200)[0])
        == before
    )


def test_fuzzy_match_and_ambiguous_duplicate_bills(tmp_path):
    repository = FinancialRepository(str(tmp_path / "graph.db"))
    _transaction(
        repository,
        external_id="one",
        amount=-99,
        merchant="StreamFlix Media",
        occurred_at="2026-08-10T12:00:00Z",
    )
    _transaction(
        repository,
        external_id="two",
        amount=-99,
        merchant="StreamFlix Media",
        occurred_at="2026-08-11T12:00:00Z",
    )

    result = reconcile_document(
        _document("STREAMFLIX\nRenewal amount: $99.00", 99), repository
    )

    assert result.status == "ambiguous"
    assert len(result.matches) == 2
    assert all(match.confidence < 0.95 for match in result.matches)


def test_price_increase_and_late_fee_are_discrepancies_not_silent_updates(tmp_path):
    repository = FinancialRepository(str(tmp_path / "graph.db"))
    transaction = _transaction(
        repository,
        external_id="utility",
        amount=-110,
        merchant="North Power late fee",
        occurred_at="2026-08-25T12:00:00Z",
    )

    result = reconcile_document(
        _document("NORTH POWER\nAmount due: $100.00\nLate fee: $10.00", 100),
        repository,
    )

    assert result.matches[0].transaction_id == transaction.id
    assert {item.kind for item in result.discrepancies} == {
        "amount_mismatch",
        "late_fee",
    }
    assert result.proposals[0].kind == "review_commitment_amount"
    assert result.proposals[0].requires_approval is True


def test_missing_or_partial_payment_stays_unresolved(tmp_path):
    repository = FinancialRepository(str(tmp_path / "graph.db"))
    _transaction(
        repository,
        external_id="partial",
        amount=-40,
        merchant="Internet Co",
        occurred_at="2026-08-20T12:00:00Z",
    )

    result = reconcile_document(
        _document("INTERNET CO\nAmount due: $80.00", 80), repository
    )

    assert result.status == "unresolved"
    assert result.matches == ()
    assert result.discrepancies[0].kind == "missing_expected_charge"
