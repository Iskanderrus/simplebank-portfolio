from decimal import Decimal

from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import APIView

from banking.models import Account
from banking.money import InvalidAmount
from banking.parsers import SafeJSONParser
from banking.selectors import get_account_for_user, list_transactions
from banking.serializers import (
    AccountSerializer,
    TransactionFilterSerializer,
    TransactionSerializer,
    TransferRequestSerializer,
)
from banking.services.transfers import (
    AccountNotFound,
    InsufficientFunds,
    SelfTransfer,
    transfer,
)


class AccountMissing(APIException):
    # Registration always opens an account, so a user without one is a broken
    # invariant on our side: a clear server error, not a "not found" for the client.
    status_code = 500
    default_detail = "No account is linked to this user."
    default_code = "account_missing"


def own_account(request) -> Account:
    # The account always comes from the token's user, never from the request.
    try:
        return get_account_for_user(request.user)
    except Account.DoesNotExist:
        raise AccountMissing()


class AccountView(APIView):
    # Token-authenticated by default.
    def get(self, request):
        return Response(AccountSerializer(own_account(request)).data)


class TransactionListView(APIView):
    def get(self, request):
        # .dict() so an empty `?from=` is a malformed date, not "no filter".
        filters = TransactionFilterSerializer(data=request.query_params.dict())
        filters.is_valid(raise_exception=True)
        transactions = list_transactions(
            own_account(request),
            date_from=filters.validated_data.get("from"),
            date_to=filters.validated_data.get("to"),
        )
        return Response(TransactionSerializer(transactions, many=True).data)


# Each rejection the transfer can end in: a stable code for clients, and fixed
# text (never the error's own message, which can carry what the caller sent).
TRANSFER_REJECTIONS = {
    InvalidAmount: ("invalid_amount", "The amount is not a usable sum of money."),
    AccountNotFound: ("account_not_found", "No account has that number."),
    SelfTransfer: ("self_transfer", "You cannot send money to your own account."),
    InsufficientFunds: (
        "insufficient_funds",
        "The balance does not cover the amount and the fee.",
    ),
}


class TransferView(APIView):
    # JSON only: a form post would be read as plain strings too.
    parser_classes = [SafeJSONParser]

    def post(self, request):
        request_data = TransferRequestSerializer(data=request.data)
        if not request_data.is_valid():
            return Response(
                {"code": "invalid_request", "errors": request_data.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Only after the body is known to be well-formed: a user without an
        # account and a bad body is a 400, not an AccountMissing 500.
        sender = own_account(request)
        try:
            result = transfer(
                sender,
                request_data.validated_data["account_number"],
                Decimal(request_data.validated_data["amount"]),
            )
        except tuple(TRANSFER_REJECTIONS) as error:
            # The first class in the error's own ancestry that has a rejection
            # entry, so a subclass of one of them is still reported properly.
            code, detail = next(
                TRANSFER_REJECTIONS[cls]
                for cls in type(error).__mro__
                if cls in TRANSFER_REJECTIONS
            )
            return Response(
                {"code": code, "detail": detail}, status=status.HTTP_400_BAD_REQUEST
            )
        return Response(
            {
                "amount": str(result.amount),
                "fee": str(result.fee),
                "total_debit": str(result.total_debit),
                "balance": str(result.sender_balance),
            },
            status=status.HTTP_201_CREATED,
        )
