"""Structured AI fallback for transactions unresolved by deterministic rules."""

import json

from meridian.classify import Classification

_KINDS = {"income", "spend", "transfer", "refund", "fee", "reimbursement"}


class AIClassifier:
    def __init__(self, client, *, provider: str, model: str):
        self._client = client
        self.provider = provider
        self.model = model

    def classify(self, transaction) -> Classification:
        prompt = (
            "Classify one financial transaction. Return only JSON with category, "
            "kind, confidence, and explanation. Do not infer merchant identity or "
            "add facts absent from the supplied fields."
        )
        payload = {
            "amount": transaction.amount,
            "description": transaction.description,
            "merchant": transaction.merchant,
            "account_type": transaction.account_type,
            "occurred_at": transaction.occurred_at,
        }
        response = self._client.complete(
            prompt,
            [{"role": "user", "content": json.dumps(payload, sort_keys=True)}],
        )
        parsed = json.loads(response)
        if not isinstance(parsed, dict):
            raise ValueError("classification response must be an object")
        category = parsed.get("category")
        kind = parsed.get("kind")
        confidence = parsed.get("confidence")
        explanation = parsed.get("explanation")
        if not isinstance(category, str) or not category.strip():
            raise ValueError("category is required")
        if kind not in _KINDS:
            raise ValueError("kind is invalid")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            raise ValueError("confidence must be between zero and one")
        if not isinstance(explanation, str) or not explanation.strip():
            raise ValueError("explanation is required")
        return Classification(
            category=category.strip(),
            kind=kind,
            confidence=float(confidence),
            rule_id=f"ai:{self.provider}:{self.model}",
            evidence=explanation.strip(),
            method="ai",
            provider=self.provider,
            model=self.model,
        )


def classify_with_ai_fallback(transaction, deterministic, classifier):
    if deterministic.method != "fallback":
        return deterministic
    try:
        return classifier.classify(transaction)
    except Exception:
        return deterministic
