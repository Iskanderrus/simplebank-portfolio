from datetime import date

from django.contrib.auth.models import User
from django.db.models import QuerySet

from banking.models import Account, Transaction


def get_account_for_user(user: User) -> Account:
    """The user's one account. Raises Account.DoesNotExist if they have none."""
    return Account.objects.get(user=user)


def list_transactions(
    account: Account, date_from: date | None = None, date_to: date | None = None
) -> QuerySet[Transaction]:
    """The account's movements, newest first (the model's default ordering).

    Both dates are inclusive whole days. Timestamps are stored in UTC and
    TIME_ZONE is UTC, so `created_at__date` is the UTC calendar day.
    """
    transactions = Transaction.objects.filter(account=account)
    if date_from is not None:
        transactions = transactions.filter(created_at__date__gte=date_from)
    if date_to is not None:
        transactions = transactions.filter(created_at__date__lte=date_to)
    return transactions
