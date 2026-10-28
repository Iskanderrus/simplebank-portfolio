from decimal import Decimal

import pytest
from django.conf import settings
from rest_framework.test import APIClient

from banking.models import Transaction

pytestmark = pytest.mark.django_db

TRANSACTIONS_URL = "/api/v1/transactions/"
PASSWORD = "correct-horse-battery-staple-42"


@pytest.fixture
def api_client():
    return APIClient()


def book(account, direction, amount):
    return Transaction.objects.create(
        account=account, direction=direction, amount=Decimal(amount)
    )


def test_history_shows_welcome_credit_after_registration(api_client):
    # Boundary test: register -> login -> read, all over HTTP.
    credentials = {"email": "alice@example.com", "password": PASSWORD}
    api_client.post("/api/v1/auth/register/", credentials, format="json")
    token = api_client.post("/api/v1/auth/login/", credentials, format="json").json()[
        "token"
    ]

    response = api_client.get(TRANSACTIONS_URL, HTTP_AUTHORIZATION=f"Token {token}")

    assert response.status_code == 200
    [row] = response.json()
    assert row["direction"] == "CREDIT"
    assert row["amount"] == str(settings.WELCOME_CREDIT)
    assert set(row) == {"direction", "amount", "created_at"}


def test_history_requires_authentication(api_client):
    assert api_client.get(TRANSACTIONS_URL).status_code == 401


def test_history_only_contains_callers_rows(api_client, account, other_account):
    book(other_account, Transaction.Direction.DEBIT, "55.00")
    api_client.force_authenticate(account.user)

    rows = api_client.get(TRANSACTIONS_URL).json()

    assert [row["amount"] for row in rows] == [str(settings.WELCOME_CREDIT)]


def test_history_is_newest_first_and_amounts_are_strings(api_client, account):
    book(account, Transaction.Direction.DEBIT, "105.00")
    book(account, Transaction.Direction.CREDIT, "7.5")
    api_client.force_authenticate(account.user)

    rows = api_client.get(TRANSACTIONS_URL).json()

    assert [(row["direction"], row["amount"]) for row in rows] == [
        ("CREDIT", "7.50"),
        ("DEBIT", "105.00"),
        ("CREDIT", str(settings.WELCOME_CREDIT)),
    ]


def test_user_without_an_account_gets_a_clean_server_error(api_client, user):
    api_client.force_authenticate(user)

    assert api_client.get(TRANSACTIONS_URL).status_code == 500
