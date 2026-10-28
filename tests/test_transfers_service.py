from decimal import Decimal
from unittest.mock import patch

import pytest
from django.conf import settings

from banking.models import Account, Transaction
from banking.money import InvalidAmount
from banking.services.transfers import (
    AccountNotFound,
    InsufficientFunds,
    SelfTransfer,
    TransferResult,
    transfer,
)

pytestmark = pytest.mark.django_db

WELCOME = settings.WELCOME_CREDIT


def balance_of(account):
    return Account.objects.get(pk=account.pk).balance


def ledger(account):
    return list(
        Transaction.objects.filter(account=account)
        .order_by("id")
        .values_list("direction", "amount")
    )


def set_balance(account, balance):
    Account.objects.filter(pk=account.pk).update(balance=Decimal(balance))


def test_transfer_100_debits_105_credits_100_and_writes_ledger(account, other_account):
    result = transfer(account, other_account.account_number, Decimal("100.00"))

    assert balance_of(account) == WELCOME - Decimal("105.00")
    assert balance_of(other_account) == WELCOME + Decimal("100.00")
    assert ledger(account)[-1] == ("DEBIT", Decimal("105.00"))
    assert ledger(other_account)[-1] == ("CREDIT", Decimal("100.00"))
    assert len(ledger(account)) == 2 and len(ledger(other_account)) == 2
    assert result == TransferResult(
        amount=Decimal("100.00"),
        fee=Decimal("5.00"),
        total_debit=Decimal("105.00"),
        sender_balance=WELCOME - Decimal("105.00"),
    )


def test_transfer_1000_debits_1025_credits_1000(account, other_account):
    # Passed as Decimal("1000"): the result must come back as 1000.00.
    result = transfer(account, other_account.account_number, Decimal(1000))

    assert balance_of(account) == WELCOME - Decimal("1025.00")
    assert balance_of(other_account) == WELCOME + Decimal("1000.00")
    assert result.amount == Decimal("1000.00")
    assert str(result.amount) == "1000.00"
    assert result.fee == Decimal("25.00")


def test_exact_balance_for_amount_plus_fee_succeeds(account, other_account):
    set_balance(account, "105.00")

    result = transfer(account, other_account.account_number, Decimal("100.00"))

    assert balance_of(account) == Decimal("0.00")
    assert result.sender_balance == Decimal("0.00")


@pytest.mark.parametrize(
    "balance, target, amount, error",
    [
        (
            "103.00",
            "other",
            Decimal("100.00"),
            InsufficientFunds,
        ),  # covers amount, not fee
        ("50.00", "other", Decimal("60.00"), InsufficientFunds),  # below the amount
        ("500.00", "self", Decimal("100.00"), SelfTransfer),
        ("500.00", "unknown", Decimal("100.00"), AccountNotFound),
        ("500.00", "other", Decimal(0), InvalidAmount),
        ("500.00", "other", Decimal("-5.00"), InvalidAmount),
        ("500.00", "other", 100.0, InvalidAmount),  # a float is never money
        ("500.00", "other", Decimal("10.001"), InvalidAmount),  # too many decimals
        # Check order: the amount first, then the account, then the funds.
        ("500.00", "self", Decimal(0), InvalidAmount),
        ("50.00", "unknown", Decimal("1000.00"), AccountNotFound),
    ],
)
def test_rejected_transfers_change_nothing(
    balance, target, amount, error, account, other_account
):
    set_balance(account, balance)
    number = {
        "other": other_account.account_number,
        "self": account.account_number,
        "unknown": "0000000000",
    }[target]
    sender_before = balance_of(account)
    receiver_before = balance_of(other_account)
    rows_before = Transaction.objects.count()

    with pytest.raises(error):
        transfer(account, number, amount)

    assert balance_of(account) == sender_before
    assert balance_of(other_account) == receiver_before
    assert Transaction.objects.count() == rows_before


def test_failure_midway_rolls_back_balances_and_ledger(account, other_account):
    rows_before = Transaction.objects.count()
    real_create = Transaction.objects.create
    calls = []

    def fail_on_second(**kwargs):
        calls.append(kwargs)
        if len(calls) == 2:
            raise RuntimeError("boom")
        return real_create(**kwargs)

    with (
        patch.object(Transaction.objects, "create", side_effect=fail_on_second),
        pytest.raises(RuntimeError),
    ):
        transfer(account, other_account.account_number, Decimal("100.00"))

    assert balance_of(account) == WELCOME
    assert balance_of(other_account) == WELCOME
    assert Transaction.objects.count() == rows_before
