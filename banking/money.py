"""Money rules: representation and rounding and the transfer fee.

The constants live in config/settings.py; this module only applies them.
"""

from decimal import (
    ROUND_HALF_UP,
    Context,
    Decimal,
    DivisionByZero,
    InvalidOperation,
    Overflow,
)

from django.conf import settings

MONEY_CONTEXT = Context(
    prec=28,
    rounding=ROUND_HALF_UP,
    traps=[InvalidOperation, DivisionByZero, Overflow],
)


# The first value that no longer fits the money columns (14 digits, 2 decimals).
_COLUMN_LIMIT = Decimal(10) ** (
    settings.MONEY_MAX_DIGITS - settings.MONEY_DECIMAL_PLACES
)


class InvalidAmount(ValueError):
    """The value is not a usable amount of euros."""


def validate_amount(value) -> Decimal:
    """Return `value` as a positive amount with exactly two decimal places."""
    if type(value) is not Decimal or not value.is_finite():
        raise InvalidAmount("Amount must be a finite Decimal.")
    if value <= 0:
        raise InvalidAmount("Amount must be greater than zero.")
    if value >= _COLUMN_LIMIT:
        # Not a product rule: a larger amount could not be stored, and its
        # fee would no longer be calculated exactly.
        raise InvalidAmount("Amount is too large.")
    cents = value.quantize(settings.MONEY_QUANTUM, context=MONEY_CONTEXT)
    if cents != value:
        raise InvalidAmount("Amount cannot have more than two decimal places.")
    return cents


def calculate_fee(amount: Decimal) -> Decimal:
    """2.5% of the amount, rounded half up to the cent, but never below 5.00"""
    return _fee_for(validate_amount(amount))


def total_debit(amount: Decimal) -> Decimal:
    """What leaves the sender's account: the amount plus the fee (the recipient gets the amount)."""
    amount = validate_amount(amount)
    return MONEY_CONTEXT.add(amount, _fee_for(amount))


def _fee_for(amount: Decimal) -> Decimal:
    """The fee for an amount that has already been through `validate_amount`."""
    raw_fee = MONEY_CONTEXT.multiply(amount, settings.TRANSFER_FEE_RATE)
    percentage_fee = raw_fee.quantize(
        settings.MONEY_QUANTUM, rounding=ROUND_HALF_UP, context=MONEY_CONTEXT
    )
    return max(percentage_fee, settings.TRANSFER_MIN_FEE)
