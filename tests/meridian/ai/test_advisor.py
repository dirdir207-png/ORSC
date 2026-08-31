import json

import pytest

from meridian.ai.advisor import (
    AdvisorContext,
    ContextualAdvisor,
    MeridianContextBuilder,
    UnsupportedAdvisorClaim,
)
from meridian.repository import FinancialRepository


class Client:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def complete(self, system, messages):
        self.calls.append((system, messages))
        return json.dumps(self.payload)


def _repository(tmp_path):
    repository = FinancialRepository(str(tmp_path / "advisor.db"))
    account = repository.upsert_account(
        provider="crew",
        external_id="private-account-id",
        name="Checking",
        account_type="checking",
        balance=125.5,
    )
    transaction = repository.upsert_transaction(
        provider="crew",
        external_id="private-transaction-id",
        account_id=account.id,
        amount=-12.5,
        occurred_at="2026-08-29T10:00:00Z",
        description="Coffee",
        status="posted",
    )
    return repository, account, transaction


def test_context_builder_allowlists_transaction_fields_and_evidence_ids(tmp_path):
    repository, _account, transaction = _repository(tmp_path)

    context = MeridianContextBuilder(repository).build(
        AdvisorContext("transaction", transaction.id, (f"transaction:{transaction.id}",))
    )

    serialized = json.dumps(context)
    assert context["object"]["amount"] == -12.5
    assert context["evidence_ids"] == [f"transaction:{transaction.id}"]
    assert "private-transaction-id" not in serialized
    assert "private-account-id" not in serialized
    assert "token" not in serialized.lower()


def test_advisor_returns_evidence_bound_answer_and_proposals(tmp_path):
    repository, _account, transaction = _repository(tmp_path)
    client = Client(
        {
            "answer": "This was a $12.50 expense.",
            "evidence": [f"transaction:{transaction.id}"],
            "proposals": [{"type": "create_commitment", "params": {"name": "Coffee cap"}}],
            "usage": {"input_tokens": 20, "output_tokens": 10},
        }
    )
    proposed = []
    advisor = ContextualAdvisor(
        client,
        MeridianContextBuilder(repository),
        provider="openrouter",
        model="test-model",
        proposal_sink=proposed.append,
    )

    result = advisor.ask(
        AdvisorContext("transaction", transaction.id, (f"transaction:{transaction.id}",)),
        "What happened?",
    )

    assert result["provider"] == "openrouter"
    assert result["model"] == "test-model"
    assert result["evidence"] == [f"transaction:{transaction.id}"]
    assert result["proposals"][0]["state"] == "proposed"
    assert proposed == [{"type": "create_commitment", "params": {"name": "Coffee cap"}}]


def test_advisor_rejects_evidence_ids_outside_context(tmp_path):
    repository, _account, transaction = _repository(tmp_path)
    advisor = ContextualAdvisor(
        Client({"answer": "Unsupported", "evidence": ["account:999"], "proposals": [], "usage": {}}),
        MeridianContextBuilder(repository),
        provider="openai",
        model="test-model",
        proposal_sink=lambda proposal: proposal,
    )

    with pytest.raises(UnsupportedAdvisorClaim):
        advisor.ask(
            AdvisorContext("transaction", transaction.id, (f"transaction:{transaction.id}",)),
            "Tell me more",
        )


def test_advisor_surfaces_provider_failure_without_fabricating(tmp_path):
    repository, _account, transaction = _repository(tmp_path)

    class FailingClient:
        def complete(self, system, messages):
            raise OSError("offline")

    advisor = ContextualAdvisor(
        FailingClient(),
        MeridianContextBuilder(repository),
        provider="openai",
        model="test-model",
        proposal_sink=lambda proposal: proposal,
    )

    result = advisor.ask(
        AdvisorContext("transaction", transaction.id, (f"transaction:{transaction.id}",)),
        "Tell me more",
    )

    assert result["answer"] == "The advisor is temporarily unavailable."
    assert result["evidence"] == []
    assert result["proposals"] == []
