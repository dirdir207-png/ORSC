from pathlib import Path


def test_transaction_inspector_exposes_document_evidence_controls():
    root = Path(__file__).parents[2]
    template = (
        root / "templates/meridian/partials/transaction-inspector.html"
    ).read_text()
    controller = (root / "static/js/meridian/transaction-inspector.js").read_text()

    assert "data-document-evidence" in template
    assert "data-evidence-list" in template
    assert "data-retention-state" in template
    assert "content_url" in controller
    assert "confidence" in controller


def test_plan_supports_proposal_only_document_discrepancies():
    root = Path(__file__).parents[2]
    plan = (root / "static/js/meridian/plan.js").read_text()

    assert "document_discrepancies" in plan
    assert "requires_approval" in plan
