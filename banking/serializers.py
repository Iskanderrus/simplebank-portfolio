from datetime import date

from django.conf import settings
from django.core.validators import RegexValidator
from rest_framework import serializers

from banking.models import Account, Transaction


class AccountSerializer(serializers.ModelSerializer[Account]):
    # Balance comes out as a decimal string, e.g. "10000.00".
    class Meta:
        model = Account
        fields = ["account_number", "balance"]


class TransactionSerializer(serializers.ModelSerializer[Transaction]):
    class Meta:
        model = Transaction
        fields = ["direction", "amount", "created_at"]


class TransactionFilterSerializer(serializers.Serializer[dict[str, date]]):
    """The `from` and `to` query parameters of the history: optional, YYYY-MM-DD."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Only YYYY-MM-DD: DRF would also accept forms like 20261001 or 2026-W40-4.
        self.fields["from"] = serializers.DateField(
            required=False, input_formats=["%Y-%m-%d"]
        )
        self.fields["to"] = serializers.DateField(
            required=False, input_formats=["%Y-%m-%d"]
        )

    def validate(self, attrs):
        if "from" in attrs and "to" in attrs and attrs["from"] > attrs["to"]:
            raise serializers.ValidationError({"to": ["Must not be before 'from'."]})
        return attrs


class StrictCharField(serializers.CharField):
    """A text field that refuses numbers instead of quietly turning them into text."""

    def to_internal_value(self, data):
        if type(data) is not str:
            self.fail("invalid")
        return super().to_internal_value(data)


def _ascii_pattern(pattern: str, message: str) -> RegexValidator:
    # \A...\Z, not ^...$: "$" also matches before a trailing newline. [0-9], not
    # \d: \d matches digits of other scripts.
    return RegexValidator(rf"\A{pattern}\Z", message)


class TransferRequestSerializer(serializers.Serializer[dict[str, str]]):
    """The shape of a transfer request. The money rules live in the service."""

    account_number = StrictCharField(
        trim_whitespace=False,
        validators=[
            _ascii_pattern(
                f"[0-9]{{{settings.ACCOUNT_NUMBER_LENGTH}}}",
                f"Must be {settings.ACCOUNT_NUMBER_LENGTH} digits.",
            )
        ],
    )
    amount = StrictCharField(
        trim_whitespace=False,
        max_length=settings.TRANSFER_AMOUNT_MAX_LENGTH,
        validators=[
            _ascii_pattern(
                f"[0-9]+(\\.[0-9]{{1,{settings.MONEY_DECIMAL_PLACES}}})?",
                "Must be a decimal string such as 100.00.",
            )
        ],
    )
