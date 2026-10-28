from decimal import Decimal

import pytest
from django.conf import settings

from banking.models import Account, Transaction

pytestmark = pytest.mark.django_db

TRANSFERS_URL = "/api/v1/transfers/"
WELCOME = settings.WELCOME_CREDIT
UNKNOWN_NUMBER = "0000000000"
CAP = settings.TRANSFER_AMOUNT_MAX_LENGTH


def transfer(client, body):
    return client.post(TRANSFERS_URL, body, format="json")


def balance_of(account):
    return Account.objects.get(pk=account.pk).balance


def test_transfer_endpoint_moves_money_and_writes_ledger(
    api_client, authenticate, account, other_account
):
    authenticate(api_client, account.user)

    response = transfer(
        api_client,
        {"account_number": other_account.account_number, "amount": "100.00"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body == {
        "amount": "100.00",
        "fee": "5.00",
        "total_debit": "105.00",
        "balance": str(WELCOME - Decimal("105.00")),
    }
    # The same facts again, read back through the other endpoints.
    assert api_client.get("/api/v1/account/").json()["balance"] == body["balance"]
    newest = api_client.get("/api/v1/transactions/").json()[0]  # newest first
    assert (newest["direction"], newest["amount"]) == ("DEBIT", "105.00")
    authenticate(api_client, other_account.user)
    assert api_client.get("/api/v1/account/").json()["balance"] == str(
        WELCOME + Decimal("100.00")
    )
    newest = api_client.get("/api/v1/transactions/").json()[0]
    assert (newest["direction"], newest["amount"]) == ("CREDIT", "100.00")


def test_sender_in_body_is_ignored(api_client, authenticate, account, other_account):
    authenticate(api_client, account.user)

    response = transfer(
        api_client,
        {
            "account_number": other_account.account_number,
            "amount": "100.00",
            "sender": other_account.account_number,
            "from_account": other_account.account_number,
        },
    )

    assert response.status_code == 201
    assert balance_of(account) == WELCOME - Decimal("105.00")
    assert balance_of(other_account) == WELCOME + Decimal("100.00")


@pytest.mark.parametrize(
    "target, amount, balance, code",
    [
        ("unknown", "100.00", None, "account_not_found"),
        ("self", "100.00", None, "self_transfer"),
        ("other", "100.00", "103.00", "insufficient_funds"),  # covers amount, not fee
        ("other", "0.00", None, "invalid_amount"),
        ("other", "1000000000000.00", None, "invalid_amount"),  # too large
        ("other", "1" + "0" * (CAP - 1), None, "invalid_amount"),  # longest allowed
        ("unknown", "0.00", None, "invalid_amount"),  # the amount is checked first
    ],
)
def test_rejected_transfers_return_a_code_and_change_nothing(
    target, amount, balance, code, api_client, authenticate, account, other_account
):
    if balance is not None:
        Account.objects.filter(pk=account.pk).update(balance=Decimal(balance))
    number = {
        "unknown": UNKNOWN_NUMBER,
        "self": account.account_number,
        "other": other_account.account_number,
    }[target]
    sender_before, receiver_before = balance_of(account), balance_of(other_account)
    rows_before = Transaction.objects.count()
    authenticate(api_client, account.user)

    response = transfer(api_client, {"account_number": number, "amount": amount})

    assert response.status_code == 400
    assert response.json()["code"] == code
    assert number not in response.json()["detail"]  # nothing is echoed back
    assert balance_of(account) == sender_before
    assert balance_of(other_account) == receiver_before
    assert Transaction.objects.count() == rows_before


def assert_rejected_as_invalid_request(response, account, rows_before):
    assert response.status_code == 400
    assert response.json()["code"] == "invalid_request"
    assert balance_of(account) == WELCOME
    assert Transaction.objects.count() == rows_before


@pytest.mark.parametrize(
    "field, value",
    [
        ("account_number", 1234567890),  # a number, not a string
        ("account_number", ["1234567890"]),
        ("account_number", {"a": 1}),
        ("account_number", None),
        ("account_number", "123456789"),  # too short
        ("account_number", "12345678901"),  # too long
        ("account_number", "12345abcde"),
        ("account_number", "1234 56789"),
        ("account_number", "1234567890\n"),  # trailing newline
        ("account_number", "١٢٣٤٥٦٧٨٩٠"),  # Arabic-Indic digits
        ("account_number", "123456789\x00"),  # NUL byte
        ("amount", 100),  # a JSON number
        ("amount", 100.5),
        ("amount", None),
        ("amount", ["1.00"]),
        ("amount", "1e2"),
        ("amount", " 100"),
        ("amount", "100\n"),
        ("amount", "100."),
        ("amount", "+100"),
        ("amount", "-5.00"),
        ("amount", "1_000"),
        ("amount", "10.001"),  # too many decimals
        ("amount", "١٠٠"),
        ("amount", "NaN"),
        ("amount", "1" * (CAP + 1)),  # one past the cap
    ],
)
def test_malformed_field_values_return_invalid_request(
    field, value, api_client, authenticate, account, other_account
):
    body = {"account_number": other_account.account_number, "amount": "1.00"}
    body[field] = value
    rows_before = Transaction.objects.count()
    authenticate(api_client, account.user)

    response = transfer(api_client, body)

    assert_rejected_as_invalid_request(response, account, rows_before)


@pytest.mark.parametrize(
    "body",
    [
        {"amount": "1.00"},  # missing keys
        {"account_number": "1234567890"},
        {},
        ["1234567890", "1.00"],  # not an object
        "text",
    ],
)
def test_malformed_bodies_return_invalid_request(
    body, api_client, authenticate, account
):
    rows_before = Transaction.objects.count()
    authenticate(api_client, account.user)

    response = transfer(api_client, body)

    assert_rejected_as_invalid_request(response, account, rows_before)


@pytest.mark.parametrize(
    "raw, status",
    [
        pytest.param(b"null", 400, id="json-null"),
        pytest.param(b"[" * 100_000, 400, id="nested-too-deeply"),
        pytest.param(b"{nope", 400, id="not-json"),
    ],
)
def test_unparseable_bodies_are_a_400_not_a_crash(
    raw, status, api_client, authenticate, account
):
    authenticate(api_client, account.user)

    response = api_client.post(TRANSFERS_URL, raw, content_type="application/json")

    assert response.status_code == status
    assert balance_of(account) == WELCOME


def test_form_encoded_post_is_415(api_client, authenticate, account, other_account):
    form = {"account_number": other_account.account_number, "amount": "100.00"}

    assert api_client.post(TRANSFERS_URL, form).status_code == 401  # auth runs first
    authenticate(api_client, account.user)
    assert api_client.post(TRANSFERS_URL, form).status_code == 415
    assert balance_of(account) == WELCOME


@pytest.mark.parametrize(
    "well_formed, status, key", [(True, 500, "detail"), (False, 400, "code")]
)
def test_user_without_an_account(
    well_formed, status, key, api_client, authenticate, user, other_account
):
    # `user` was created directly, so registration never opened an account for it.
    number = other_account.account_number if well_formed else "bad"
    authenticate(api_client, user)

    response = transfer(api_client, {"account_number": number, "amount": "1.00"})

    assert response.status_code == status
    assert key in response.json()


@pytest.mark.parametrize("token", [None, "bogus"])
def test_transfer_requires_a_valid_token(token, api_client, other_account):
    if token:
        api_client.credentials(HTTP_AUTHORIZATION=f"Token {token}")

    response = transfer(
        api_client,
        {"account_number": other_account.account_number, "amount": "1.00"},
    )

    assert response.status_code == 401
