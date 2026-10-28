from datetime import UTC, datetime
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from banking.models import Transaction

pytestmark = pytest.mark.django_db

TRANSACTIONS_URL = "/api/v1/transactions/"


@pytest.fixture
def api_client(account):
    client = APIClient()
    client.force_authenticate(account.user)
    return client


def book_at(account, moment, amount="1.00"):
    """A ledger row stamped at `moment` (created_at is set by the database layer)."""
    row = Transaction.objects.create(
        account=account, direction=Transaction.Direction.CREDIT, amount=Decimal(amount)
    )
    Transaction.objects.filter(pk=row.pk).update(created_at=moment)
    return row


def amounts(response):
    return [row["amount"] for row in response.json()]


@pytest.fixture
def history(account):
    # The welcome credit is "now"; push it out of the way of the test dates.
    Transaction.objects.filter(account=account).update(
        created_at=datetime(2020, 1, 1, tzinfo=UTC)
    )
    book_at(account, datetime(2026, 10, 1, 0, 0, 0, tzinfo=UTC), "1.00")  # first moment
    book_at(account, datetime(2026, 10, 3, 12, 0, tzinfo=UTC), "2.00")
    book_at(account, datetime(2026, 10, 5, 23, 59, 59, 999999, tzinfo=UTC), "3.00")
    book_at(account, datetime(2026, 10, 6, 0, 0, 0, tzinfo=UTC), "4.00")  # next day
    book_at(account, datetime(2026, 9, 30, 23, 59, 59, 999999, tzinfo=UTC), "5.00")


def test_from_is_inclusive_at_start_of_day(api_client, history):
    response = api_client.get(TRANSACTIONS_URL, {"from": "2026-10-01"})

    assert "1.00" in amounts(response)
    assert "5.00" not in amounts(response)  # one microsecond earlier


def test_to_is_inclusive_through_end_of_day(api_client, history):
    response = api_client.get(TRANSACTIONS_URL, {"to": "2026-10-05"})

    assert "3.00" in amounts(response)  # 23:59:59.999999 on the last day
    assert "4.00" not in amounts(response)  # midnight of the day after


def test_from_and_to_together_give_the_inclusive_range(api_client, history):
    response = api_client.get(
        TRANSACTIONS_URL, {"from": "2026-10-01", "to": "2026-10-05"}
    )

    assert amounts(response) == ["3.00", "2.00", "1.00"]  # newest first


def test_the_same_from_and_to_gives_that_single_day(api_client, history):
    response = api_client.get(
        TRANSACTIONS_URL, {"from": "2026-10-05", "to": "2026-10-05"}
    )

    assert amounts(response) == ["3.00"]


@pytest.mark.parametrize(
    "params",
    [
        {"from": "garbage"},
        {"to": "garbage"},
        {"from": ""},  # present but empty is still malformed, not "no filter"
        {"from": "2026-02-30"},  # not a real date
        {"from": "2026-10-01T10:00:00Z"},  # a datetime, not a date
        {"from": "01/10/2026"},
        {"from": "20261001"},  # valid ISO, but not the documented YYYY-MM-DD
    ],
)
def test_malformed_date_returns_400_not_unfiltered(api_client, history, params):
    assert api_client.get(TRANSACTIONS_URL, params).status_code == 400


def test_from_after_to_returns_400(api_client, history):
    response = api_client.get(
        TRANSACTIONS_URL, {"from": "2026-10-05", "to": "2026-10-01"}
    )

    assert response.status_code == 400


def test_the_last_representable_day_does_not_break_the_filter(api_client, history):
    response = api_client.get(TRANSACTIONS_URL, {"to": "9999-12-31"})

    assert response.status_code == 200
    assert len(response.json()) == 6


def test_filtered_history_subset_of_unfiltered_history(api_client, history):
    everything = api_client.get(TRANSACTIONS_URL).json()
    some = api_client.get(TRANSACTIONS_URL, {"from": "2026-10-02"}).json()

    assert 0 < len(some) < len(everything)
    assert all(row in everything for row in some)
