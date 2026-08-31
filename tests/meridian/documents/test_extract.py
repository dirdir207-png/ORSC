import pytest

from meridian.documents.extract import extract_document


@pytest.mark.parametrize(
    ("document_type", "text", "field", "value"),
    [
        (
            "bill",
            "UTILITY BILL\nAmount due: $84.12\nDue date: 2026-09-15",
            "amount_due",
            84.12,
        ),
        (
            "statement",
            "BANK STATEMENT\nStatement total: $1,204.55",
            "statement_total",
            1204.55,
        ),
        ("receipt", "RECEIPT\nTotal: $23.40", "total", 23.40),
        ("renewal", "RENEWAL NOTICE\nRenewal amount: $99.00", "renewal_amount", 99.0),
        ("pay_stub", "PAY STUB\nNet pay: $2,100.00", "net_pay", 2100.0),
    ],
)
def test_document_extraction_retains_page_and_region_provenance(
    document_type, text, field, value
):
    document = extract_document(text.encode(), mime_type="text/plain")

    assert document.document_type == document_type
    fact = next(item for item in document.facts if item.field == field)
    assert fact.value == value
    assert fact.provenance.page == 1
    assert fact.provenance.region.startswith("line:")


def test_ambiguous_amounts_remain_candidates_not_facts():
    document = extract_document(
        b"NOTICE\nCurrent amount $50.00\nPossible adjusted amount $65.00",
        mime_type="text/plain",
    )

    assert document.facts == ()
    assert {candidate.value for candidate in document.candidates} == {50.0, 65.0}


def test_image_uses_ocr_before_deterministic_extraction():
    calls = []

    def ocr(blob, mime_type):
        calls.append((blob, mime_type))
        return "RECEIPT\nTotal: $18.25"

    document = extract_document(b"image bytes", mime_type="image/png", ocr=ocr)

    assert calls == [(b"image bytes", "image/png")]
    assert document.document_type == "receipt"
    assert document.facts[0].value == 18.25
