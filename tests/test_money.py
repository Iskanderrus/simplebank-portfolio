from decimal import Decimal, Inexact, localcontext

import pytest

from banking.money import (
    InvalidAmount,
    calculate_fee,
    total_debit,
    validate_amount,
)


@pytest.mark.parametrize(
    "amount, expected_fee",
    [
        ("0.01", "5.00"),  # tiny amounts still pay the minimum
        ("100.00", "5.00"),  # 2.5% = 2.50, below the minimum
        ("200.00", "5.00"),  # 2.5% = 5.00, exactly the minimum
        ("1000.00", "25.00"),  # percentage wins
    ],
)
def test_fee_is_two_and_a_half_percent_but_at_least_five_euro(amount, expected_fee):
    assert calculate_fee(Decimal(amount)) == Decimal(expected_fee)


def test_fee_percentage_branch_after_rounding():
    # 2.5% of 200.20 is 5.005, which rounds up to 5.01 and beats the minimum.
    assert calculate_fee(Decimal("200.20")) == Decimal("5.01")


def test_fee_rounds_half_cent_up():
    # 2.5% of 1000.20 is 25.005; ROUND_HALF_UP gives 25.01
    assert calculate_fee(Decimal("1000.20")) == Decimal("25.01")


def test_total_debit_is_amount_plus_fee():
    assert total_debit(Decimal("100.00")) == Decimal("105.00")
    assert total_debit(Decimal("1000.00")) == Decimal("1025.00")


def test_largest_storable_amount_is_calculated_exactly():
    largest = Decimal("999999999999.99")
    assert calculate_fee(largest) == Decimal("25000000000.00")
    assert total_debit(largest) == Decimal("1024999999999.99")


def test_results_do_not_depend_on_the_callers_decimal_context():
    with localcontext() as ctx:
        ctx.prec = 3
        ctx.traps[Inexact] = True
        assert calculate_fee(Decimal("1000.20")) == Decimal("25.01")
        assert total_debit(Decimal("1234.56")) == Decimal("1265.42")


@pytest.mark.parametrize(
    "value",
    [
        Decimal(0),
        Decimal("-1.00"),
        100.0,  # float
        True,  # bool
        "100.00",  # str: callers must parse before the money rules run
        Decimal("NaN"),
        Decimal("sNaN"),
        Decimal("Infinity"),
        Decimal("10.001"),  # more than two decimal places
        Decimal("1E-999999999"),  # positive, but far below one cent
        Decimal("1000000000000.00"),  # no longer fits the money columns
        Decimal("1E+999999999"),  # huge exponent must not escape as decimal.Overflow
    ],
)
def test_amount_rejects_zero_negative_float_nan_infinity_and_extra_decimals(value):
    with pytest.raises(InvalidAmount):
        validate_amount(value)


@pytest.mark.parametrize("value", [100.0, "100.00", None, Decimal("NaN")])
def test_fee_and_total_debit_reject_invalid_amounts(value):
    with pytest.raises(InvalidAmount):
        calculate_fee(value)
    with pytest.raises(InvalidAmount):
        total_debit(value)


def test_amount_rejects_decimal_subclasses():
    class LyingDecimal(Decimal):
        def __le__(self, other):
            return False

    with pytest.raises(InvalidAmount):
        validate_amount(LyingDecimal("-5"))


def test_amount_is_normalised_to_two_decimal_places():
    assert str(validate_amount(Decimal(5))) == "5.00"
    assert str(validate_amount(Decimal("1.500"))) == "1.50"
