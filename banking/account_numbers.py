import secrets

from django.conf import settings
from django.db import IntegrityError, transaction

from banking.models import ACCOUNT_NUMBER_UNIQUE, Account


class AccountNumberExhausted(Exception):
    """No free account number was found within the allowed number of attempts."""


def _random_number() -> str:
    length = settings.ACCOUNT_NUMBER_LENGTH
    return f"{secrets.randbelow(10**length):0{length}d}"


def create_account_with_number(user) -> Account:
    """Open an account for `user` with a unique random number.

    The database decides uniqueness: two requests can both pick the same free
    number, and the loser simply tries again. Any other integrity error, such as
    the user already having an account, is a real error and is raised at once.
    """
    for _ in range(settings.ACCOUNT_NUMBER_MAX_ATTEMPTS):
        try:
            with transaction.atomic():
                return Account.objects.create(
                    user=user, account_number=_random_number()
                )
        except IntegrityError as error:
            if not _is_number_collision(error):
                raise
    raise AccountNumberExhausted(
        f"No free account number after {settings.ACCOUNT_NUMBER_MAX_ATTEMPTS} attempts."
    )


def _is_number_collision(error: IntegrityError) -> bool:
    diagnostics = getattr(error.__cause__, "diag", None)
    return getattr(diagnostics, "constraint_name", None) == ACCOUNT_NUMBER_UNIQUE
