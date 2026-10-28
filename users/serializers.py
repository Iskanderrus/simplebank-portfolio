from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers


class NormalizedEmailField(serializers.EmailField):
    """An email, trimmed and lower-cased, so "Alice@X.com " and "alice@x.com" match."""

    def __init__(self, **kwargs):
        super().__init__(max_length=settings.EMAIL_MAX_LENGTH, **kwargs)

    def to_internal_value(self, data):
        return super().to_internal_value(data).strip().lower()


def _password_field():
    # trim_whitespace=False: a password is taken exactly as typed, at register
    # and at login alike. The cap keeps us from hashing a multi-megabyte body.
    return serializers.CharField(
        write_only=True, trim_whitespace=False, max_length=settings.PASSWORD_MAX_LENGTH
    )


class RegisterSerializer(serializers.Serializer[dict[str, str]]):
    email = NormalizedEmailField()
    password = _password_field()

    def validate_email(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("A user with that email already exists.")
        return value

    def validate(self, attrs):
        # Needs the email too: one validator rejects passwords similar to it.
        user = User(username=attrs["email"], email=attrs["email"])
        try:
            validate_password(attrs["password"], user)
        except DjangoValidationError as error:
            raise serializers.ValidationError({"password": list(error.messages)})
        return attrs


class LoginSerializer(serializers.Serializer[dict[str, str]]):
    email = NormalizedEmailField()
    password = _password_field()

    def validate(self, attrs):
        # Django's auth backend looks users up by username, which holds the email.
        user = authenticate(
            request=self.context.get("request"),
            username=attrs["email"],
            password=attrs["password"],
        )
        if user is None:
            raise serializers.ValidationError(
                "Unable to log in with provided credentials.", code="authorization"
            )
        attrs["user"] = user
        return attrs
