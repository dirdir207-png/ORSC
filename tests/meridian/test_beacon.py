from datetime import date, timedelta

from meridian.beacon import forecast


class Graph:
    def __init__(self, accounts, transactions):
        self._accounts = accounts
        self._transactions = transactions

    def list_accounts(self):
        return self._accounts

    def list_transactions(self, limit=200):
        return self._transactions, None


class Record:
    def __init__(self, **fields):
        self.__dict__.update(fields)


class Commitments:
    def __init__(self, items=()):
        self._items = items

    def list_active(self):
        return list(self._items)


class Rules:
    def list_for_commitment(self, commitment_id):
        return []


def test_forecast_explains_runway_low_point_and_first_shortfall():
    as_of = date(2026, 9, 1)
    graph = Graph(
        [Record(id=1, account_type="checking", is_active=True, balance=300, currency="USD")],
        [
            Record(
                id=index,
                amount=-10,
                occurred_at=(as_of - timedelta(days=index)).isoformat() + "T10:00:00Z",
                classification_kind="spend",
            )
            for index in range(1, 11)
        ],
    )
    commitments = Commitments(
        [
            Record(
                id=7,
                name="Insurance",
                type=Record(value="bill"),
                amount=250,
                target_amount=None,
                buffer_minimum=None,
                funded_amount=0,
                due_date="2026-09-10",
                target_date=None,
            )
        ]
    )

    result = forecast(graph, commitments, Rules(), as_of)

    assert result.available is True
    assert result.runway_days == 5
    assert result.low_point_date == date(2026, 9, 10)
    assert result.first_shortfall.date == date(2026, 9, 10)
    assert result.first_shortfall.cause == "Insurance"
    assert result.factors
    assert all(factor.explanation for factor in result.factors)


def test_forecast_exposes_uncertainty_and_freshness_confidence():
    as_of = date(2026, 9, 1)
    graph = Graph(
        [Record(id=1, account_type="checking", is_active=True, balance=1000, currency="USD")],
        [
            Record(id=1, amount=-10, occurred_at="2026-08-30T10:00:00Z", classification_kind="spend"),
            Record(id=2, amount=-30, occurred_at="2026-08-29T10:00:00Z", classification_kind="spend"),
        ],
    )

    result = forecast(graph, Commitments(), Rules(), as_of, freshness="stale")

    assert result.daily_expense_range == (10.0, 30.0)
    assert result.confidence < 0.7
    assert result.freshness == "stale"


def test_forecast_without_history_is_honestly_unavailable():
    graph = Graph(
        [Record(id=1, account_type="checking", is_active=True, balance=1000, currency="USD")],
        [],
    )

    result = forecast(graph, Commitments(), Rules(), date(2026, 9, 1))

    assert result.available is False
    assert result.reason == "transaction history unavailable"
