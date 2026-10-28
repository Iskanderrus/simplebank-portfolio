import re
from unittest.mock import patch

import pytest
from django.conf import settings
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from banking.models import Account, Transaction
from banking.services.registration import EmailTaken, register_user

pytestmark = pytest.mark.django_db

REGISTER_URL = "/api/v1/auth/register/"
STRONG_PASSWORD = "correct-horse-battery-staple-42"
EMAIL = "alice@example.com"


@pytest.fixture
def api_client():
    return APIClient()


def register(api_client, **payload):
    return api_client.post(REGISTER_URL, payload, format="json")


def row_counts():
    return User.objects.count(), Account.objects.count(), Transaction.objects.count()


# --- service ---------------------------------------------------------------


def test_register_creates_user_account_and_welcome_credit():
    account = register_user(EMAIL, STRONG_PASSWORD)

    assert account.user.email == EMAIL
    assert account.user.username == EMAIL
    account.refresh_from_db()
    assert account.balance == settings.WELCOME_CREDIT
    welcome = Transaction.objects.get(account=account)
    assert welcome.direction == Transaction.Direction.CREDIT
    assert welcome.amount == settings.WELCOME_CREDIT
    assert row_counts() == (1, 1, 1)


def test_registration_rolls_back_all_rows_on_failure():
    with (
        patch.object(Transaction.objects, "create", side_effect=RuntimeError("boom")),
        pytest.raises(RuntimeError),
    ):
        register_user(EMAIL, STRONG_PASSWORD)

    assert row_counts() == (0, 0, 0)


def test_password_is_hashed():
    account = register_user(EMAIL, STRONG_PASSWORD)

    assert account.user.password != STRONG_PASSWORD
    assert account.user.check_password(STRONG_PASSWORD)


def test_register_user_raises_email_taken_and_leaves_nothing_behind():
    register_user(EMAIL, STRONG_PASSWORD)

    with pytest.raises(EmailTaken):
        register_user(EMAIL, STRONG_PASSWORD)

    assert row_counts() == (1, 1, 1)


# --- endpoint --------------------------------------------------------------


def test_register_endpoint_returns_201_and_account_number(api_client):
    response = register(api_client, email=EMAIL, password=STRONG_PASSWORD)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"email", "account_number"}
    assert body["email"] == EMAIL
    assert re.fullmatch(r"\d{10}", body["account_number"])
    assert STRONG_PASSWORD not in response.content.decode()
    assert (
        Account.objects.get(user__email=EMAIL).account_number
        == (body["account_number"])
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"email": EMAIL, "password": "12345678"},  # weak password
        {"email": EMAIL, "password": "alice123"},  # too similar to the email
        {"email": EMAIL},  # no password
        {"password": STRONG_PASSWORD},  # no email
        {"email": "not-an-email", "password": STRONG_PASSWORD},  # malformed
        {"email": "alice@", "password": STRONG_PASSWORD},  # malformed
        {"email": "a" * 150 + "@example.com", "password": STRONG_PASSWORD},  # too long
        {"username": EMAIL, "password": STRONG_PASSWORD},  # old contract
        {
            "email": EMAIL,
            "password": "x" * (settings.PASSWORD_MAX_LENGTH + 1),
        },  # password too long
    ],
)
def test_register_rejects_invalid_input(api_client, payload):
    response = register(api_client, **payload)

    assert response.status_code == 400
    assert row_counts() == (0, 0, 0)


def test_register_rejects_duplicate_email(api_client):
    register_user(EMAIL, STRONG_PASSWORD)

    response = register(api_client, email=EMAIL, password=STRONG_PASSWORD)

    assert response.status_code == 400
    assert "email" in response.json()
    assert row_counts() == (1, 1, 1)


def test_register_keeps_whitespace_in_password(api_client):
    password = "  correct horse battery staple  "

    response = register(api_client, email=EMAIL, password=password)

    assert response.status_code == 201
    assert User.objects.get(email=EMAIL).check_password(password)


def test_register_maps_email_race_to_400(api_client):
    with patch("users.views.register_user", side_effect=EmailTaken(EMAIL)):
        response = register(api_client, email=EMAIL, password=STRONG_PASSWORD)

    assert response.status_code == 400
    assert "email" in response.json()


def test_register_normalizes_email_before_storing(api_client):
    response = register(
        api_client, email="  Alice@Example.COM ", password=STRONG_PASSWORD
    )

    assert response.status_code == 201
    assert response.json()["email"] == EMAIL
    user = User.objects.get()
    assert user.email == EMAIL
    assert user.username == EMAIL  # Django's login name is the same normalized email


def test_register_treats_emails_differing_only_in_case_as_duplicates(api_client):
    register_user(EMAIL, STRONG_PASSWORD)

    response = register(api_client, email="ALICE@example.com", password=STRONG_PASSWORD)

    assert response.status_code == 400
    assert row_counts() == (1, 1, 1)
