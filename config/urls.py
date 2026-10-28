from django.urls import include, path

from banking.views import AccountView, TransactionListView, TransferView

urlpatterns = [
    path("api/v1/auth/", include("users.urls")),
    path("api/v1/account/", AccountView.as_view(), name="account"),
    path("api/v1/transactions/", TransactionListView.as_view(), name="transactions"),
    path("api/v1/transfers/", TransferView.as_view(), name="transfers"),
]
