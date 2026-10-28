import os
from decimal import Decimal
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = os.environ.get("DJANGO_DEBUG") == "1"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "rest_framework",
    "rest_framework.authtoken",
    "users",
    "banking",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "simplebank"),
        "USER": os.environ.get("POSTGRES_USER", "simplebank"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "simplebank"),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

PASSWORD_MAX_LENGTH = 128
EMAIL_MAX_LENGTH = 150  # stored as User.username, which Django caps at 150
LOGIN_THROTTLE_RATE = "10/min"  # per client address; slows password guessing

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Every stored timestamp is timezone-aware.
USE_TZ = True
TIME_ZONE = "UTC"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    # Every endpoint needs a token unless it opts out (register, login).
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication"
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_THROTTLE_RATES": {"login": LOGIN_THROTTLE_RATE},
    # Money on the API is a decimal string, never a float.
    "COERCE_DECIMAL_TO_STRING": True,
}

# Banking rules.
MONEY_QUANTUM = Decimal("0.01")  # smallest unit: one cent
TRANSFER_FEE_RATE = Decimal("0.025")  # 2.5% of the transferred amount
TRANSFER_MIN_FEE = Decimal("5.00")  # the min fee
MONEY_MAX_DIGITS = 14  # room for 999,999,999,999.99
MONEY_DECIMAL_PLACES = 2
# The longest amount string we read: far above any real amount.
TRANSFER_AMOUNT_MAX_LENGTH = 32

WELCOME_CREDIT = Decimal("10000.00")  # opening balance, booked as a CREDIT

# Account numbers
ACCOUNT_NUMBER_LENGTH = 10
ACCOUNT_NUMBER_MAX_ATTEMPTS = 5  # tries to find a free number before giving up
