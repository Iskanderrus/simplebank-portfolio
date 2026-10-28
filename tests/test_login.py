import pytest
from django.conf import settings
from rest_framework.test import APIClient

from banking.services.registration import register_user

pytestmark = pytest.mark.django_db

LOGIN_URL = "/api/v1/auth/login/"
REGISTER_URL = "/api/v1/auth/register/"
EMAIL = "alice@example.com"
PASSWORD = "correct-horse-battery-staple-42"


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def registered():
    register_user(EMAIL, PASSWORD)


def login(api_client, **payload):
    return api_client.post(LOGIN_URL, payload, format="json")


def test_login_after_register_returns_token(api_client):
    # Boundary test: crosses the SB-004 registration seam over HTTP.
    api_client.post(REGISTER_URL, {"email": EMAIL, "password": PASSWORD}, format="json")

    response = login(api_client, email=EMAIL, password=PASSWORD)

    assert response.status_code == 200
    assert set(response.json()) == {"token"}
    assert response.json()["token"]


def test_login_accepts_the_email_in_any_case(api_client, registered):
    response = login(api_client, email="  ALICE@Example.com ", password=PASSWORD)

    assert response.status_code == 200


def test_login_wrong_password_returns_400(api_client, registered):
    response = login(api_client, email=EMAIL, password="not-the-password")

    assert response.status_code == 400
    assert "token" not in response.json()


def test_login_unknown_email_returns_400(api_client, registered):
    response = login(api_client, email="nobody@example.com", password=PASSWORD)

    assert response.status_code == 400
    assert "token" not in response.json()


def test_login_rejects_the_old_username_contract(api_client, registered):
    response = login(api_client, username=EMAIL, password=PASSWORD)

    assert response.status_code == 400


def test_login_rejects_over_long_password(api_client, registered):
    too_long = "x" * (settings.PASSWORD_MAX_LENGTH + 1)

    response = login(api_client, email=EMAIL, password=too_long)

    assert response.status_code == 400
    assert "password" in response.json()


def test_login_returns_same_token_on_repeat(api_client, registered):
    first = login(api_client, email=EMAIL, password=PASSWORD).json()["token"]
    second = login(api_client, email=EMAIL, password=PASSWORD).json()["token"]

    assert first == second


def test_login_ignores_a_stale_authorization_header(api_client, registered):
    api_client.credentials(HTTP_AUTHORIZATION="Token bogus")

    response = login(api_client, email=EMAIL, password=PASSWORD)

    assert response.status_code == 200


def test_register_ignores_a_stale_authorization_header(api_client):
    api_client.credentials(HTTP_AUTHORIZATION="Token bogus")

    response = api_client.post(
        REGISTER_URL, {"email": "bob@example.com", "password": PASSWORD}, format="json"
    )

    assert response.status_code == 201


@pytest.mark.parametrize(
    "email", ["not-an-email", "alice@", "x" * 150 + "@example.com"]
)
def test_login_rejects_invalid_email(api_client, registered, email):
    response = login(api_client, email=email, password=PASSWORD)

    assert response.status_code == 400
    assert "email" in response.json()


@pytest.mark.parametrize(
    "payload",
    [
        {"email": ["alice@example.com"], "password": PASSWORD},
        {"email": {"a": 1}, "password": PASSWORD},
        {"email": "ali\x00ce@example.com", "password": PASSWORD},
        {"email": EMAIL},
        {},
    ],
)
def test_login_rejects_hostile_bodies(api_client, registered, payload):
    assert login(api_client, **payload).status_code == 400


def test_login_rejects_malformed_json(api_client):
    response = api_client.post(LOGIN_URL, "{not json", content_type="application/json")

    assert response.status_code == 400


def test_login_is_throttled_after_too_many_attempts(api_client, registered):
    allowed = int(settings.LOGIN_THROTTLE_RATE.split("/")[0])

    codes = [
        login(api_client, email=EMAIL, password="wrong").status_code
        for _ in range(allowed + 1)
    ]

    assert codes[:allowed] == [400] * allowed
    assert codes[-1] == 429
