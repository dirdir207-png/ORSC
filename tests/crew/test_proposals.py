import pytest

from crew.proposals import ProposalError, build_transfer_proposal


class FakeResolver:
    def __init__(self, mapping):
        self._mapping = mapping

    def resolve(self, name):
        return self._mapping.get(name)


@pytest.fixture
def resolver():
    return FakeResolver({"checking": "acc-1", "rent": "pock-9", "savings": "pock-2"})


def test_builds_proposal_with_resolved_ids_and_summary(resolver):
    proposal = build_transfer_proposal(
        resolver,
        from_name="Checking",
        to_name="Rent",
        amount=50,
        memo="October",
    )
    assert proposal["type"] == "move_money"
    assert proposal["params"] == {
        "from_id": "acc-1",
        "to_id": "pock-9",
        "amount": 50,
        "memo": "October",
    }
    assert proposal["summary"] == "Move $50.00 from Checking → Rent (memo: 'October')"


def test_names_are_matched_case_insensitively(resolver):
    proposal = build_transfer_proposal(resolver, "CHECKING", "rent", 10, "")
    assert proposal["params"]["from_id"] == "acc-1"


def test_unresolvable_source_raises_with_clear_error(resolver):
    with pytest.raises(ProposalError) as exc:
        build_transfer_proposal(resolver, "Mystery Account", "Rent", 10, "")
    assert "mystery account" in str(exc.value).lower()


def test_unresolvable_destination_raises(resolver):
    with pytest.raises(ProposalError):
        build_transfer_proposal(resolver, "Checking", "Nowhere", 10, "")


@pytest.mark.parametrize("amount", [0, -5, "abc", None])
def test_non_positive_or_invalid_amount_raises(resolver, amount):
    with pytest.raises(ProposalError) as exc:
        build_transfer_proposal(resolver, "Checking", "Rent", amount, "")
    assert "amount" in str(exc.value).lower()


def test_same_source_and_destination_is_rejected(resolver):
    with pytest.raises(ProposalError) as exc:
        build_transfer_proposal(resolver, "Checking", "checking", 10, "")
    assert "same" in str(exc.value).lower()


def test_summary_without_memo_omits_parenthetical(resolver):
    proposal = build_transfer_proposal(resolver, "Checking", "Savings", 25.5, "")
    assert proposal["summary"] == "Move $25.50 from Checking → Savings"
