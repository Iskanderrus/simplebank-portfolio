from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError

from banking.models import Account, LedgerRowImmutable, Transaction

pytestmark = pytest.mark.django_db


@pytest.fixture
def account(user):
    return Account.objects.create(user=user, account_number="0049182736")


def test_negative_balance_rejected_by_database(user):
    with pytest.raises(IntegrityError), transaction.atomic():
        Account.objects.create(
            user=user, account_number="1111111111", balance=Decimal("-0.01")
        )


@pytest.mark.parametrize("amount", ["0.00", "-5.00"])
def test_transaction_amount_must_be_positive(account, amount):
    with pytest.raises(IntegrityError), transaction.atomic():
        Transaction.objects.create(
            account=account, direction=Transaction.Direction.CREDIT, amount=amount
        )


def test_transaction_direction_must_be_credit_or_debit(account):
    with pytest.raises(IntegrityError), transaction.atomic():
        Transaction.objects.create(account=account, direction="REFUND", amount="1.00")


def test_account_number_unique_and_keeps_leading_zeros(account, other_user):
    account.refresh_from_db()
    assert account.account_number == "0049182736"

    with pytest.raises(IntegrityError), transaction.atomic():
        Account.objects.create(user=other_user, account_number="0049182736")


def test_transaction_cannot_be_updated_or_deleted(account):
    ledger_row = Transaction.objects.create(
        account=account, direction=Transaction.Direction.CREDIT, amount="10.00"
    )

    ledger_row.amount = Decimal("99.00")
    with pytest.raises(LedgerRowImmutable):
        ledger_row.save()
    with pytest.raises(LedgerRowImmutable):
        ledger_row.delete()

    # A fresh object pointing at an existing primary key must not overwrite it either.
    impostor = Transaction(
        id=ledger_row.pk,
        account=account,
        direction=Transaction.Direction.DEBIT,
        amount="99.00",
    )
    with pytest.raises(LedgerRowImmutable):
        impostor.save()
    ledger_row.refresh_from_db()
    assert ledger_row.amount == Decimal("10.00")


def test_account_and_transaction_roundtrip_with_constraints(account):
    first = Transaction.objects.create(
        account=account, direction=Transaction.Direction.CREDIT, amount="10000.00"
    )
    second = Transaction.objects.create(
        account=account, direction=Transaction.Direction.DEBIT, amount="105.00"
    )

    assert account.balance == Decimal(0)
    assert list(account.transactions.all()) == [second, first]  # newest first
    first.refresh_from_db()
    assert first.amount == Decimal("10000.00")
    assert first.created_at.tzinfo is not None

    with pytest.raises(ProtectedError):
        account.delete()
