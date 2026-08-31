import json

import pytest

from meridian.ai.classifier import AIClassifier, classify_with_ai_fallback
from meridian.classify import ClassificationInput, classify_deterministic
from meridian.providers.base import (
    NormalizedAccount,
    NormalizedTransaction,
    ProviderSnapshot,
)
from meridian.repository import FinancialRepository
from meridian.services.activity import get_review_queue
from meridian.sync import sync_provider


class FakeClient:
    def __init__(self, payload=None, error=None):
        self.payload = payload
        self.error = error
        self.calls = []

    def complete(self, system, messages):
        self.calls.append((system, messages))
        if self.error:
            raise self.error
        return json.dumps(self.payload)


def _transaction(**overrides):
    values = {
        "id": 1,
        "amount": -14.5,
        "description": "Mystery vendor",
        "merchant": None,
        "account_type": "checking",
        "occurred_at": "2026-08-29T10:00:00Z",
    }
    values.update(overrides)
    return ClassificationInput(**values)


def test_ai_only_classifies_deterministic_fallbacks():
    client = FakeClient(
        {"category": "Dining", "kind": "spend", "confidence": 0.91, "explanation": "restaurant-like descriptor"}
    )
    classifier = AIClassifier(client, provider="openrouter", model="test-model")
    resolved = classify_deterministic(_transaction(relation_type="owned_transfer"))

    result = classify_with_ai_fallback(_transaction(), resolved, classifier)

    assert result is resolved
    assert client.calls == []


def test_ai_validates_structured_output_and_records_audit_metadata():
    client = FakeClient(
        {"category": "Dining", "kind": "spend", "confidence": 0.91, "explanation": "restaurant-like descriptor"}
    )
    fallback = classify_deterministic(_transaction())

    result = classify_with_ai_fallback(
        _transaction(),
        fallback,
        AIClassifier(client, provider="openrouter", model="test-model"),
    )

    assert result.category == "Dining"
    assert result.method == "ai"
    assert result.provider == "openrouter"
    assert result.model == "test-model"
    assert "credentials" not in client.calls[0][0].lower()


@pytest.mark.parametrize(
    "payload",
    [
        {"category": "Dining", "kind": "invented", "confidence": 0.9, "explanation": "x"},
        {"category": "Dining", "kind": "spend", "confidence": 2, "explanation": "x"},
        {"category": "", "kind": "spend", "confidence": 0.8, "explanation": "x"},
    ],
)
def test_invalid_ai_output_leaves_deterministic_fallback_healthy(payload):
    fallback = classify_deterministic(_transaction())

    result = classify_with_ai_fallback(
        _transaction(),
        fallback,
        AIClassifier(FakeClient(payload), provider="openai", model="test-model"),
    )

    assert result is fallback


def test_ai_failure_leaves_transaction_unclassified_but_healthy():
    fallback = classify_deterministic(_transaction())

    result = classify_with_ai_fallback(
        _transaction(),
        fallback,
        AIClassifier(FakeClient(error=RuntimeError("offline")), provider="openai", model="test-model"),
    )

    assert result is fallback
    assert result.category == "Uncategorized"


def test_non_runtime_provider_failure_also_leaves_fallback_healthy():
    fallback = classify_deterministic(_transaction())

    result = classify_with_ai_fallback(
        _transaction(),
        fallback,
        AIClassifier(
            FakeClient(error=OSError("connection reset")),
            provider="openai",
            model="test-model",
        ),
    )

    assert result is fallback


def test_low_confidence_ai_result_enters_review_queue(tmp_path):
    repository = FinancialRepository(str(tmp_path / "financial.db"))
    account = repository.upsert_account(
        provider="crew", external_id="checking", name="Checking", account_type="checking", balance=100
    )
    transaction = repository.upsert_transaction(
        provider="crew",
        external_id="mystery",
        account_id=account.id,
        amount=-14.5,
        occurred_at="2026-08-29T10:00:00Z",
        description="Mystery vendor",
        status="posted",
    )
    result = classify_with_ai_fallback(
        _transaction(id=transaction.id),
        classify_deterministic(_transaction(id=transaction.id)),
        AIClassifier(
            FakeClient({"category": "Other", "kind": "spend", "confidence": 0.49, "explanation": "uncertain"}),
            provider="openai",
            model="test-model",
        ),
    )
    repository.record_classification(transaction.id, result)

    queue = get_review_queue(repository)

    assert [item.id for item in queue] == [transaction.id]
    assert queue[0].classification_confidence == 0.49


def test_sync_uses_ai_for_fallback_and_survives_provider_failure(tmp_path):
    repository = FinancialRepository(str(tmp_path / "financial.db"))
    snapshot = ProviderSnapshot(
        connection_external_id="crew-household",
        connection_name="Crew",
        accounts=(NormalizedAccount("checking", "Checking", "checking", 100),),
        transactions=(
            NormalizedTransaction(
                external_id="mystery",
                account_external_id="checking",
                amount=-14.5,
                occurred_at="2026-08-29T10:00:00Z",
                description="Mystery vendor",
                status="posted",
            ),
        ),
    )

    class Adapter:
        provider_name = "crew"
        connection_external_id = "crew-household"
        connection_name = "Crew"

        @staticmethod
        def fetch_snapshot():
            return snapshot

    report = sync_provider(
        Adapter(),
        repository,
        ai_classifier=AIClassifier(
            FakeClient(error=RuntimeError("offline")),
            provider="openai",
            model="test-model",
        ),
    )

    assert report.status == "complete"
    transactions, _ = repository.list_transactions()
    assert transactions[0].classification_category == "Uncategorized"
