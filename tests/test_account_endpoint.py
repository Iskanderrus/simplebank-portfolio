from decimal import Decimal

import pytest
from django.conf import settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from banking.models import Account

pytestmark = pytest.mark.django_db

ACCOUNT_URL = "/api/v1/account/"
PASSWORD = "correct-horse-battery-staple-42"


@pytest.fixture
def api_client():
    return APIClient()


def test_registered_user_sees_welcome_balance_via_token(api_client):
    # Boundary test: register -> login -> read, all over HTTP.
    credentials = {"email": "alice@example.com", "password": PASSWORD}
    registered = api_client.post(
        "/api/v1/auth/register/", credentials, format="json"
    ).json()
    token = api_client.post("/api/v1/auth/login/", credentials, format="json").json()[
        "token"
    ]

    response = api_client.get(ACCOUNT_URL, HTTP_AUTHORIZATION=f"Token {token}")

    assert response.status_code == 200
    assert response.json() == {
        "account_number": registered["account_number"],
        "balance": str(settings.WELCOME_CREDIT),
    }


def test_account_requires_authentication(api_client):
    assert api_client.get(ACCOUNT_URL).status_code == 401


def test_account_returns_only_callers_account(api_client, account, other_account):
    api_client.force_authenticate(account.user)
    mine = api_client.get(ACCOUNT_URL).json()
    api_client.force_authenticate(other_account.user)
    theirs = api_client.get(ACCOUNT_URL).json()

    assert mine["account_number"] == account.account_number
    assert theirs["account_number"] == other_account.account_number


def test_account_response_has_exactly_the_intended_fields(api_client, account):
    api_client.force_authenticate(account.user)

    body = api_client.get(ACCOUNT_URL).json()

    assert body == {
        "account_number": account.account_number,
        "balance": "10000.00",
    }


def test_balance_is_a_two_decimal_string_and_follows_the_database(api_client, account):
    Account.objects.filter(pk=account.pk).update(balance=Decimal("7.5"))
    api_client.force_authenticate(account.user)

    assert api_client.get(ACCOUNT_URL).json()["balance"] == "7.50"


def test_caller_cannot_choose_another_account_by_parameter(
    api_client, account, other_account
):
    api_client.force_authenticate(account.user)

    response = api_client.get(
        ACCOUNT_URL,
        {"account_number": other_account.account_number, "id": other_account.pk},
    )

    assert response.json()["account_number"] == account.account_number


def test_reading_the_balance_is_one_query_and_writes_nothing(
    api_client, account, django_assert_num_queries
):
    token = Token.objects.create(user=account.user)

    # one query for the token and its user, one for the account
    with django_assert_num_queries(2) as captured:
        api_client.get(ACCOUNT_URL, HTTP_AUTHORIZATION=f"Token {token.key}")

    writes = [q["sql"] for q in captured if not q["sql"].startswith("SELECT")]
    assert writes == []


def test_user_without_an_account_gets_a_clean_server_error(api_client, user):
    api_client.force_authenticate(user)

    response = api_client.get(ACCOUNT_URL)

    assert response.status_code == 500
    assert response.json() == {"detail": "No account is linked to this user."}
