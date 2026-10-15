"""
Django settings for the WOW Quick Bites API.

Every value that changes between environments comes from environment variables (or a local `.env`
file), see `.env.example` for the full list.
"""

from datetime import timedelta
from pathlib import Path

import dj_database_url
from decouple import Csv, config
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

# ───────── Security ─────────

DEBUG = config("DEBUG", default=False, cast=bool)

SECRET_KEY = config("SECRET_KEY", default="")
if not SECRET_KEY:
    if not DEBUG:
        raise ImproperlyConfigured("SECRET_KEY is required when DEBUG is False.")
    SECRET_KEY = "dev-only-insecure-secret-key"

ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="127.0.0.1,localhost,.onrender.com", cast=Csv())
CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", default="", cast=Csv())

# The website calls the API from its server, so CORS is only needed for browser tools.
CORS_ALLOWED_ORIGINS = [origin.rstrip("/") for origin in config("CORS_ALLOWED_ORIGINS", default="", cast=Csv())]
CORS_ALLOW_CREDENTIALS = False

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = config("SECURE_HSTS_SECONDS", default=3600, cast=int)
    # Render already redirects to HTTPS; redirecting here too would break its internal HTTP health check
    SILENCED_SYSTEM_CHECKS = ["security.W008"]

# ───────── Applications ─────────

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "corsheaders",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    # Project (one app per area of the API contract)
    "core",
    "accounts",
    "audit",
    "business",
    "menu",
    "orders",
    "notifications",
    "promotions",
    "staff",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "WOWBites.urls"
WSGI_APPLICATION = "WOWBites.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ───────── Database ─────────
# DATABASE_URL (Neon in production) > DB_NAME/DB_USER… (local PostgreSQL) > SQLite (quick local start, tests).

DATABASE_URL = config("DATABASE_URL", default="")

if DATABASE_URL:
    DATABASES = {"default": dj_database_url.parse(DATABASE_URL, conn_max_age=600, conn_health_checks=True)}
elif config("DB_NAME", default=""):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": config("DB_NAME"),
            "USER": config("DB_USER", default="postgres"),
            "PASSWORD": config("DB_PASSWORD", default=""),
            "HOST": config("DB_HOST", default="localhost"),
            "PORT": config("DB_PORT", default="5432"),
        }
    }
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ───────── Users and passwords ─────────

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ───────── Language and time ─────────
# Dates are stored in UTC and returned in Kigali time ("2026-10-06T12:18:00+02:00").

LANGUAGE_CODE = "en"
TIME_ZONE = "Africa/Kigali"
USE_I18N = True
USE_TZ = True

# ───────── Static and uploaded files ─────────

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# Uploaded images go to Cloudinary when this is set (recommended on Render, whose disk is wiped on
# every deploy), otherwise to MEDIA_ROOT. Format: cloudinary://<api_key>:<api_secret>@<cloud_name>
CLOUDINARY_URL = config("CLOUDINARY_URL", default="")
UPLOAD_MAX_BYTES = 5 * 1024 * 1024
UPLOAD_MAX_SIDE = 1600

# ───────── Website (frontend) ─────────

# Public URL of the website: used in the links sent by email (password reset, invitations).
FRONTEND_URL = config("FRONTEND_URL", default="http://localhost:3000").rstrip("/")

# Shared secret only the website server knows. Required by POST /auth/google and lets the website
# forward the visitor's IP (X-Client-IP) for rate limiting. Never sent to a browser.
FRONTEND_SHARED_SECRET = config("FRONTEND_SHARED_SECRET", default="")

# ───────── Email (Brevo) ─────────
# Without BREVO_API_KEY, emails are printed in the server log (development).

BREVO_API_KEY = config("BREVO_API_KEY", default="")
DEFAULT_FROM_EMAIL = config("BREVO_SENDER_EMAIL", default="no-reply@wowquickbites.rw")
EMAIL_SENDER_NAME = config("EMAIL_SENDER_NAME", default="WOW Quick Bites")
EMAIL_BACKEND = (
    "core.mail.BrevoEmailBackend" if BREVO_API_KEY else "django.core.mail.backends.console.EmailBackend"
)

# ───────── Translation (DeepL, optional) ─────────
# When an editor fills only one language, the other one is translated (or copied without a key).

DEEPL_AUTH_KEY = config("DEEPL_AUTH_KEY", default="")

# ───────── REST API ─────────

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["accounts.authentication.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    # JSON keys are camelCase on the wire and snake_case in Python
    "DEFAULT_RENDERER_CLASSES": ["djangorestframework_camel_case.render.CamelCaseJSONRenderer"],
    "DEFAULT_PARSER_CLASSES": [
        "djangorestframework_camel_case.parser.CamelCaseJSONParser",
        "djangorestframework_camel_case.parser.CamelCaseMultiPartParser",
        "djangorestframework_camel_case.parser.CamelCaseFormParser",
    ],
    "EXCEPTION_HANDLER": "core.exceptions.api_exception_handler",
    "DEFAULT_SCHEMA_CLASS": "core.schema.AutoSchema",
    "DEFAULT_THROTTLE_RATES": {
        "sign_in": "10/minute",
        "sign_up": "20/hour",
        "email_code": "30/hour",
        "password_reset": "10/hour",
        "place_order": "30/hour",
    },
    "NUM_PROXIES": config("NUM_PROXIES", default=0 if DEBUG else 1, cast=int),
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
    "UNAUTHENTICATED_USER": "django.contrib.auth.models.AnonymousUser",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=config("ACCESS_TOKEN_MINUTES", default=60, cast=int)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=config("REFRESH_TOKEN_DAYS", default=7, cast=int)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    # Suspended accounts are refused with 403 account_suspended (accounts.authentication)
    "CHECK_USER_IS_ACTIVE": False,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "WOW Quick Bites API",
    "DESCRIPTION": (
        "API of the WOW Quick Bites website: catalogue, orders, client area and staff portal. "
        "JSON keys are camelCase. Errors: `{ \"error\": { \"code\", \"message\", \"details\" } }`. "
        "Authenticate with `Authorization: Bearer <access token>` from `POST /api/v1/auth/sign-in`."
    ),
    "VERSION": "2.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": r"/api/v1",
    "ENUM_NAME_OVERRIDES": {"OrderStage": "orders.models.Stage"},
    "POSTPROCESSING_HOOKS": [
        "drf_spectacular.contrib.djangorestframework_camel_case.camelize_serializer_fields",
        "drf_spectacular.hooks.postprocess_schema_enums",
    ],
    "TAGS": [
        {"name": "Auth", "description": "Sign-up, email code, sign-in, tokens, password, profile."},
        {"name": "Catalogue", "description": "Public menu, promotions and business details."},
        {"name": "Orders", "description": "Checkout (clients and guests) and the client's orders."},
        {"name": "Notifications", "description": "Order updates sent to clients."},
        {"name": "Register", "description": "Staff order queue and order transitions."},
        {"name": "Content", "description": "Menu editing (drafts, publish), uploads and homepage campaigns."},
        {"name": "Staff", "description": "Managers, invitations, content grants, overview and audit (superadmin)."},
    ],
    "SWAGGER_UI_SETTINGS": {"persistAuthorization": True, "filter": True, "docExpansion": "list"},
}

# ───────── Logging ─────────

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {"django": {"handlers": ["console"], "level": "WARNING", "propagate": False}},
}
