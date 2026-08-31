"""Deterministic document reconciliation against normalized transactions."""

from dataclasses import dataclass
from difflib import SequenceMatcher

from meridian.documents.extract import ExtractedDocument
from meridian.repository import FinancialRepository


@dataclass(frozen=True)
class DocumentMatch:
    transaction_id: int
    evidence_id: int | None
    confidence: float
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class DocumentDiscrepancy:
    kind: str
    message: str
    transaction_id: int | None = None


@dataclass(frozen=True)
class DocumentProposal:
    kind: str
    summary: str
    requires_approval: bool = True


@dataclass(frozen=True)
class DocumentReconciliation:
    status: str
    matches: tuple[DocumentMatch, ...]
    discrepancies: tuple[DocumentDiscrepancy, ...]
    proposals: tuple[DocumentProposal, ...]


def _document_amount(document: ExtractedDocument) -> float | None:
    preferred = {"amount_due", "statement_total", "total", "renewal_amount", "net_pay"}
    return next(
        (
            float(fact.value)
            for fact in document.facts
            if fact.field in preferred and isinstance(fact.value, (int, float))
        ),
        None,
    )


def _merchant_score(document: ExtractedDocument, merchant: str) -> float:
    heading = next(
        (line.strip() for line in document.text.splitlines() if line.strip()), ""
    )
    left = heading.casefold()
    right = merchant.casefold()
    if left and (left in right or right in left):
        return 0.4
    return 0.4 * SequenceMatcher(None, left, right).ratio()


def reconcile_document(
    document: ExtractedDocument,
    graph: FinancialRepository,
    *,
    evidence_id: int | None = None,
) -> DocumentReconciliation:
    """Return suggestions only; never mutate transactions or Commitments."""
    amount = _document_amount(document)
    if amount is None:
        return DocumentReconciliation(
            "unresolved",
            (),
            (
                DocumentDiscrepancy(
                    "amount_unknown", "No authoritative document total."
                ),
            ),
            (),
        )
    transactions, _ = graph.list_transactions(limit=200)
    candidates = []
    for transaction in transactions:
        merchant = transaction.merchant or transaction.description
        difference = abs(abs(transaction.amount) - amount)
        ratio = difference / amount if amount else 1.0
        if difference <= 0.01:
            amount_score, amount_reason = 0.55, "exact_amount"
        elif ratio <= 0.15:
            amount_score, amount_reason = 0.3, "amount_near"
        else:
            continue
        score = _merchant_score(document, merchant) + amount_score
        if score >= 0.45:
            candidates.append((score, transaction, difference, amount_reason))
    candidates.sort(key=lambda item: (-item[0], item[1].id))
    if not candidates:
        return DocumentReconciliation(
            "unresolved",
            (),
            (
                DocumentDiscrepancy(
                    "missing_expected_charge", "No matching transaction was found."
                ),
            ),
            (),
        )
    ambiguous = len(candidates) > 1 and candidates[0][0] - candidates[1][0] < 0.08
    selected = candidates if ambiguous else candidates[:1]
    matches = tuple(
        DocumentMatch(
            transaction.id,
            evidence_id,
            round(max(0.0, score - (0.1 if ambiguous else 0.0)), 3),
            (amount_reason, "merchant_similarity"),
        )
        for score, transaction, _difference, amount_reason in selected
    )
    discrepancies = []
    proposals = []
    top_score, top_transaction, difference, _amount_reason = candidates[0]
    if difference > 0.01:
        discrepancies.append(
            DocumentDiscrepancy(
                "amount_mismatch",
                f"Document and transaction differ by ${difference:.2f}.",
                top_transaction.id,
            )
        )
        proposals.append(
            DocumentProposal(
                "review_commitment_amount",
                "Review the linked Commitment amount; no change has been applied.",
            )
        )
    if (
        "late fee" in document.text.casefold()
        or "late fee"
        in (top_transaction.merchant or top_transaction.description).casefold()
    ):
        discrepancies.append(
            DocumentDiscrepancy(
                "late_fee",
                "A late fee is present in the evidence chain.",
                top_transaction.id,
            )
        )
    status = (
        "ambiguous" if ambiguous else ("matched" if top_score >= 0.75 else "unresolved")
    )
    return DocumentReconciliation(
        status, matches, tuple(discrepancies), tuple(proposals)
    )
