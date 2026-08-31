"""Evidence-bound contextual advisor for Meridian workspaces."""

import json
from dataclasses import dataclass


class UnsupportedAdvisorClaim(ValueError):
    pass


@dataclass(frozen=True)
class AdvisorContext:
    kind: str
    object_id: int | str
    evidence_ids: tuple[str, ...] = ()


class MeridianContextBuilder:
    def __init__(self, repository):
        self._repository = repository

    def build(self, context: AdvisorContext) -> dict:
        if context.kind == "transaction":
            transaction = self._repository.get_transaction(int(context.object_id))
            if transaction is None:
                raise ValueError("transaction not found")
            evidence_id = f"transaction:{transaction.id}"
            return {
                "kind": context.kind,
                "object": {
                    "id": transaction.id,
                    "amount": transaction.amount,
                    "currency": transaction.currency,
                    "occurred_at": transaction.occurred_at,
                    "description": transaction.description,
                    "merchant": transaction.merchant,
                    "category": transaction.classification_category,
                    "kind": transaction.classification_kind,
                    "confidence": transaction.classification_confidence,
                },
                "evidence_ids": [evidence_id],
            }
        if context.kind == "account":
            account = next(
                (item for item in self._repository.list_accounts() if item.id == int(context.object_id)),
                None,
            )
            if account is None:
                raise ValueError("account not found")
            return {
                "kind": context.kind,
                "object": {
                    "id": account.id,
                    "name": account.name,
                    "account_type": account.account_type,
                    "balance": account.balance,
                    "available_balance": account.available_balance,
                    "currency": account.currency,
                },
                "evidence_ids": [f"account:{account.id}"],
            }
        if context.kind in {"commitment", "forecast"}:
            return {
                "kind": context.kind,
                "object": {"id": context.object_id},
                "evidence_ids": list(context.evidence_ids),
            }
        raise ValueError("unsupported advisor context")


class ContextualAdvisor:
    def __init__(self, client, context_builder, *, provider, model, proposal_sink):
        self._client = client
        self._context_builder = context_builder
        self.provider = provider
        self.model = model
        self._proposal_sink = proposal_sink

    def ask(self, context: AdvisorContext, question: str) -> dict:
        financial_context = self._context_builder.build(context)
        system = (
            "Answer only from the supplied Meridian evidence. Return JSON with "
            "answer, evidence, proposals, and usage. Every numeric claim must cite "
            "an evidence id. If evidence is insufficient, state uncertainty. Never "
            "claim a proposal was executed."
        )
        try:
            raw = self._client.complete(
                system,
                [
                    {
                        "role": "user",
                        "content": json.dumps(
                            {"question": question, "context": financial_context},
                            sort_keys=True,
                        ),
                    }
                ],
            )
            payload = json.loads(raw)
            if not isinstance(payload, dict) or not isinstance(payload.get("answer"), str):
                raise ValueError("advisor response is invalid")
            evidence = payload.get("evidence") or []
            if not isinstance(evidence, list) or not all(isinstance(item, str) for item in evidence):
                raise ValueError("advisor evidence is invalid")
            allowed_evidence = set(financial_context["evidence_ids"])
            if not set(evidence) <= allowed_evidence:
                raise UnsupportedAdvisorClaim("advisor cited unsupported evidence")
            proposals = []
            for proposal in payload.get("proposals") or []:
                if not isinstance(proposal, dict) or not isinstance(proposal.get("type"), str):
                    continue
                if proposal["type"] not in {
                    "create_commitment",
                    "update_funding_rule",
                    "scheduled_move_money",
                }:
                    continue
                self._proposal_sink(proposal)
                proposals.append({**proposal, "state": "proposed"})
            return {
                "answer": payload["answer"],
                "evidence": evidence,
                "proposals": proposals,
                "provider": getattr(self._client, "last_provider", None) or self.provider,
                "model": self.model,
                "usage": payload.get("usage") or {},
            }
        except UnsupportedAdvisorClaim:
            raise
        except Exception:
            return {
                "answer": "The advisor is temporarily unavailable.",
                "evidence": [],
                "proposals": [],
                "provider": self.provider,
                "model": self.model,
                "usage": {},
            }
