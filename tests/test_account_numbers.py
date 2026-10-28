from unittest.mock import patch

import pytest
from django.conf import settings
from django.db import IntegrityError

from banking.account_numbers import (
    AccountNumberExhausted,
    _random_number,
    create_account_with_number,
)
from banking.models import Account

pytestmark = pytest.mark.django_db

TAKEN = "1111111111"


@pytest.fixture
def taken_number(other_user):
    return Account.objects.create(user=other_user, account_number=TAKEN)


def test_random_number_is_zero_padded_to_ten_digits():
    with patch("banking.account_numbers.secrets.randbelow", return_value=49182736):
        assert _random_number() == "0049182736"


def test_generation_retries_on_collision(user, taken_number):
    with patch(
        "banking.account_numbers._random_number", side_effect=[TAKEN, "2222222222"]
    ):
        account = create_account_with_number(user)

    assert account.account_number == "2222222222"
    # The failed attempt must not have poisoned the surrounding transaction.
    assert Account.objects.count() == 2


def test_generation_gives_up_after_max_attempts(user, taken_number):
    with (
        patch(
            "banking.account_numbers._random_number", return_value=TAKEN
        ) as random_number,
        pytest.raises(AccountNumberExhausted),
    ):
        create_account_with_number(user)

    assert random_number.call_count == settings.ACCOUNT_NUMBER_MAX_ATTEMPTS
    assert Account.objects.count() == 1


def test_generation_does_not_retry_when_user_already_has_an_account(user):
    Account.objects.create(user=user, account_number="3333333333")

    with (
        patch(
            "banking.account_numbers._random_number",
            side_effect=["4444444444", "5555555555"],
        ) as random_number,
        pytest.raises(IntegrityError),
    ):
        create_account_with_number(user)

    assert random_number.call_count == 1
