import pytest
from django.core.cache import cache
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from banking.services.registration import register_user


@pytest.fixture(autouse=True)
def fresh_throttle():
    # Throttle counters live in the cache and would carry over between tests.
    cache.clear()


@pytest.fixture
def user(django_user_model):
    return django_user_model.objects.create(username="alice")


@pytest.fixture
def other_user(django_user_model):
    return django_user_model.objects.create(username="bob")


# Funded accounts, built the way registration builds them (welcome credit included).
@pytest.fixture
def account():
    return register_user("carol", "correct-horse-battery-staple-42")


@pytest.fixture
def other_account():
    return register_user("dave", "correct-horse-battery-staple-42")


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def authenticate():
    """Return `authenticate(client, user)`: log the client in with a real token header."""

    def _authenticate(client, user):
        token, _ = Token.objects.get_or_create(user=user)
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        return client

    return _authenticate
