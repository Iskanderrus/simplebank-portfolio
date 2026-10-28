from rest_framework import status
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from banking.services.registration import EmailTaken, register_user
from users.serializers import LoginSerializer, RegisterSerializer


class RegisterView(APIView):
    # Open to everyone, and deliberately without authentication: a stale token in
    # the request must not turn a registration into a 401.
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        credentials = serializer.validated_data
        try:
            account = register_user(credentials["email"], credentials["password"])
        except EmailTaken:
            raise ValidationError({"email": ["A user with that email already exists."]})
        return Response(
            {
                "email": account.user.email,
                "account_number": account.account_number,
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(ObtainAuthToken):
    # Same reasoning as RegisterView: the default is now authenticated-only.
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = LoginSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"
