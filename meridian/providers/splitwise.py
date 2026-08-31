"""Read-only Splitwise balance and shared-expense normalization."""

from datetime import datetime, timezone

from .base import (
    CommitmentCandidate,
    ExpectedInflow,
    NormalizedAccount,
    NormalizedTransaction,
    ProviderSnapshot,
)


class SplitwiseAdapter:
    provider_name = "splitwise"
    connection_name = "Splitwise"

    def __init__(self, fetch_friends, fetch_expenses, *, current_user_id: int, observed_at: str | None = None):
        self._fetch_friends = fetch_friends
        self._fetch_expenses = fetch_expenses
        self._current_user_id = current_user_id
        self.connection_external_id = f"user:{current_user_id}"
        self._observed_at = observed_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def fetch_snapshot(self) -> ProviderSnapshot:
        expected_inflows = []
        candidates = []
        currencies = set()
        for friend in self._fetch_friends().get("friends", []):
            friend_id = friend.get("id")
            if friend_id is None:
                continue
            name = str(friend.get("first_name") or friend.get("name") or f"Person {friend_id}")
            for balance in friend.get("balance") or []:
                amount = round(float(balance.get("amount") or 0), 2)
                currency = str(balance.get("currency_code") or "USD").upper()
                currencies.add(currency)
                if amount > 0:
                    expected_inflows.append(ExpectedInflow(f"friend:{friend_id}", f"Splitwise — {name}", amount, currency, self._observed_at))
                elif amount < 0:
                    candidates.append(CommitmentCandidate(f"friend:{friend_id}", f"Splitwise — {name}", abs(amount), currency, self._observed_at))
        transactions = []
        for expense in self._fetch_expenses().get("expenses", []):
            expense_id = expense.get("id")
            occurred_at = expense.get("date") or expense.get("created_at")
            user_share = next((user for user in expense.get("users") or [] if user.get("user_id") == self._current_user_id), None)
            if expense_id is None or not isinstance(occurred_at, str) or not user_share:
                continue
            transactions.append(NormalizedTransaction(
                external_id=f"expense:{expense_id}",
                account_external_id=self.connection_external_id,
                amount=round(float(user_share.get("paid_share") or 0) - float(user_share.get("owed_share") or 0), 2),
                occurred_at=occurred_at,
                description=str(expense.get("description") or "Splitwise expense"),
                status="posted",
                currency=str(expense.get("currency_code") or "USD").upper(),
                source_updated_at=str(expense.get("updated_at") or self._observed_at),
                relation_hint=f"splitwise-expense:{expense_id}",
            ))
        account = NormalizedAccount(
            external_id=self.connection_external_id,
            name="Splitwise reimbursements",
            account_type="reimbursement",
            balance=round(sum(item.amount for item in expected_inflows) - sum(item.amount for item in candidates), 2),
            currency=next(iter(currencies), "USD"),
            source_updated_at=self._observed_at,
        )
        return ProviderSnapshot(
            connection_external_id=self.connection_external_id,
            connection_name=self.connection_name,
            accounts=(account,),
            transactions=tuple(transactions),
            expected_inflows=tuple(expected_inflows),
            commitment_candidates=tuple(candidates),
        )
