import re
from decimal import Decimal

import pytest
from django.conf import settings

pytestmark = pytest.mark.django_db

PASSWORD = "correct-horse-battery-staple-42"
WELCOME = settings.WELCOME_CREDIT


def register_and_login(client, email):
    """Sign a user up and log them in over HTTP; return (account_number, token)."""
    credentials = {"email": email, "password": PASSWORD}
    registered = client.post("/api/v1/auth/register/", credentials, format="json")
    assert registered.status_code == 201
    assert registered.json()["email"] == email
    account_number = registered.json()["account_number"]
    assert re.fullmatch(rf"[0-9]{{{settings.ACCOUNT_NUMBER_LENGTH}}}", account_number)

    logged_in = client.post("/api/v1/auth/login/", credentials, format="json")
    assert logged_in.status_code == 200
    return account_number, logged_in.json()["token"]


def get(client, token, path):
    return client.get(path, HTTP_AUTHORIZATION=f"Token {token}")


def balance(client, token):
    return get(client, token, "/api/v1/account/").json()["balance"]


def movements(client, token, query=""):
    response = get(client, token, f"/api/v1/transactions/{query}")
    assert response.status_code == 200
    return [(row["direction"], row["amount"]) for row in response.json()]


def test_full_flow_register_login_transfer_history(api_client):
    # A real client: two users sign up and log in, nothing is set up behind the API.
    alice_account, alice_token = register_and_login(api_client, "alice@example.com")
    bob_account, bob_token = register_and_login(api_client, "bob@example.com")

    # Both start with the welcome credit.
    for token, account in [(alice_token, alice_account), (bob_token, bob_account)]:
        response = get(api_client, token, "/api/v1/account/")
        assert response.status_code == 200
        assert response.json() == {
            "account_number": account,
            "balance": str(WELCOME),
        }

    # Alice sends 100.00 to Bob: he receives 100.00, she pays 100.00 + a 5.00 fee.
    transfer = api_client.post(
        "/api/v1/transfers/",
        {"account_number": bob_account, "amount": "100.00"},
        format="json",
        HTTP_AUTHORIZATION=f"Token {alice_token}",
    )
    assert transfer.status_code == 201
    alice_after = WELCOME - Decimal("105.00")
    assert transfer.json() == {
        "amount": "100.00",
        "fee": "5.00",
        "total_debit": "105.00",
        "balance": str(alice_after),
    }

    # The new balances, read back through the API.
    assert balance(api_client, alice_token) == str(alice_after)
    assert balance(api_client, bob_token) == str(WELCOME + Decimal("100.00"))

    # Each history holds the welcome credit and its side of the transfer.
    alice_history = movements(api_client, alice_token)
    bob_history = movements(api_client, bob_token)
    assert sorted(alice_history) == sorted(
        [("CREDIT", str(WELCOME)), ("DEBIT", "105.00")]
    )
    assert sorted(bob_history) == sorted(
        [("CREDIT", str(WELCOME)), ("CREDIT", "100.00")]
    )

    # The date filter narrows the list. A range far in the future cannot contain
    # today's rows however close to midnight the test runs, so there is no clock race.
    future = "?from=2999-01-01&to=2999-12-31"
    assert movements(api_client, alice_token, future) == []
    assert movements(api_client, bob_token, future) == []
