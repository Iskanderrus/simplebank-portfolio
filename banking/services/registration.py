from django.conf import settings
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction

from banking.account_numbers import create_account_with_number
from banking.models import Account, Transaction


class EmailTaken(Exception):
    """The email was claimed by a concurrent registration."""


def register_user(email: str, password: str) -> Account:
    """Create a user, open their account and book the welcome credit.

    One transaction: either all three rows exist afterwards or none do.
    The opening balance is a visible CREDIT, not a silently set number.
    """
    with transaction.atomic():
        user = _create_user(email, password)
        account = create_account_with_number(user)
        account.balance = settings.WELCOME_CREDIT
        account.save(update_fields=["balance"])
        Transaction.objects.create(
            account=account,
            direction=Transaction.Direction.CREDIT,
            amount=settings.WELCOME_CREDIT,
        )
    return account


def _create_user(email: str, password: str) -> User:
    try:
        # Django logs in by username, so the (normalized) email is stored as both;
        # the API never shows the word username. create_user hashes the password.
        return User.objects.create_user(username=email, email=email, password=password)
    except IntegrityError as error:
        # The serializer checks uniqueness first; this is the race where two
        # requests pass that check and the database decides.
        raise EmailTaken(email) from error
