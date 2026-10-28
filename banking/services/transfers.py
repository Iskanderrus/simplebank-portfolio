from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction

from banking.models import Account, Transaction
from banking.money import MONEY_CONTEXT, total_debit, validate_amount


class AccountNotFound(Exception):
    """No account has the receiver's account number."""


class SelfTransfer(Exception):
    """The sender tried to pay their own account."""


class InsufficientFunds(Exception):
    """The balance does not cover the amount plus the fee."""


@dataclass(frozen=True)
class TransferResult:
    amount: Decimal  # what the receiver got
    fee: Decimal
    total_debit: Decimal  # what the sender paid: amount + fee
    sender_balance: Decimal  # the sender's balance after the transfer


def transfer(
    sender: Account, receiver_account_number: str, amount: Decimal
) -> TransferResult:
    """Move `amount` to the receiver; the sender also pays the fee.

    A bad amount raises money.InvalidAmount. Nothing is written unless
    every step succeeds.
    """
    amount = validate_amount(amount)
    total = total_debit(amount)
    if receiver_account_number == sender.account_number:
        raise SelfTransfer()
    try:
        # Accounts are never deleted and their number never changes, so the id
        # found here is still the right row once the locks are taken.
        receiver_id = Account.objects.values_list("id", flat=True).get(
            account_number=receiver_account_number
        )
    except Account.DoesNotExist:
        raise AccountNotFound(receiver_account_number)

    with transaction.atomic():
        # Locked in id order, not sender-first, so two crossing transfers cannot
        # deadlock. Building the dict runs the query now, inside the transaction.
        locked = {
            account.pk: account
            for account in Account.objects.select_for_update()
            .filter(id__in=[sender.pk, receiver_id])
            .order_by("id")
        }
        locked_sender = locked[sender.pk]
        locked_receiver = locked.get(receiver_id)
        if locked_receiver is None:
            raise AccountNotFound(receiver_account_number)
        # The balance is read from the locked row: any copy loaded earlier may
        # be out of date by now.
        if locked_sender.balance < total:
            raise InsufficientFunds()

        locked_sender.balance = MONEY_CONTEXT.subtract(locked_sender.balance, total)
        locked_receiver.balance = MONEY_CONTEXT.add(locked_receiver.balance, amount)
        locked_sender.save(update_fields=["balance"])
        locked_receiver.save(update_fields=["balance"])
        Transaction.objects.create(
            account=locked_sender, direction=Transaction.Direction.DEBIT, amount=total
        )
        Transaction.objects.create(
            account=locked_receiver,
            direction=Transaction.Direction.CREDIT,
            amount=amount,
        )

    return TransferResult(
        amount=amount,
        fee=MONEY_CONTEXT.subtract(total, amount),
        total_debit=total,
        sender_balance=locked_sender.balance,
    )
