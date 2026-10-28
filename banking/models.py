from django.conf import settings
from django.db import models
from django.db.models import Q

ACCOUNT_NUMBER_UNIQUE = "account_number_unique"


class LedgerRowImmutable(Exception):
    """A transaction row was changed or deleted after it was written."""


class Account(models.Model):
    """Holds the current balance; the movements that explain it live in Transaction."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="account"
    )
    # Text, not a number: the leading zeros are part of the identity.
    account_number = models.CharField(max_length=settings.ACCOUNT_NUMBER_LENGTH)
    balance = models.DecimalField(
        max_digits=settings.MONEY_MAX_DIGITS,
        decimal_places=settings.MONEY_DECIMAL_PLACES,
        default=0,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["account_number"], name=ACCOUNT_NUMBER_UNIQUE
            ),
            models.CheckConstraint(
                condition=Q(balance__gte=0), name="account_balance_not_negative"
            ),
        ]

    def __str__(self):
        return self.account_number


class Direction(models.TextChoices):
    CREDIT = "CREDIT"  # adds money to the account
    DEBIT = "DEBIT"  # removes money from the account


class Transaction(models.Model):
    """One movement on an account. The amount is positive; the direction carries the sign."""

    Direction = Direction

    account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="transactions"
    )
    direction = models.CharField(max_length=6, choices=Direction)
    amount = models.DecimalField(
        max_digits=settings.MONEY_MAX_DIGITS,
        decimal_places=settings.MONEY_DECIMAL_PLACES,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0), name="transaction_amount_positive"
            ),
            models.CheckConstraint(
                condition=Q(direction__in=Direction.values),
                name="transaction_direction_valid",
            ),
        ]

    def save(self, *args, force_insert=False, **kwargs):
        # A primary key means the row exists (or claims to). Only a forced insert,
        # as `objects.create()` does, may write; anything else would be an UPDATE.
        if self.pk is not None and not force_insert:
            raise LedgerRowImmutable(
                "Transactions are never edited after they are written."
            )
        super().save(*args, force_insert=force_insert, **kwargs)

    def delete(self, *args, **kwargs):
        raise LedgerRowImmutable("Transactions are never deleted.")
