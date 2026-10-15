from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from core.phone import PhoneField

from .models import ContentGrant, GrantScope, User, normalize_email


def lang_field():
    return serializers.ChoiceField(choices=["en", "fr"], default="en", help_text="Language of the email.")


class EmailField(serializers.EmailField):
    def to_internal_value(self, data):
        return normalize_email(super().to_internal_value(data))


def check_password_strength(password, *, email="", name=""):
    try:
        validate_password(password, user=User(email=email, name=name))
    except DjangoValidationError as exc:
        codes = {error.code for error in exc.error_list}
        code = next(
            (c for c in ("password_too_short", "password_too_common", "password_entirely_numeric") if c in codes),
            "password_too_similar" if "password_too_similar" in codes else "invalid",
        )
        raise serializers.ValidationError(
            {"password": serializers.ErrorDetail(exc.messages[0], code=code)}
        ) from exc


# ───────── Output ─────────


class ContentGrantSerializer(serializers.ModelSerializer):
    granted_by = serializers.CharField(source="granted_by.staff_id", default=None, read_only=True)

    class Meta:
        model = ContentGrant
        fields = ["granted_by", "scopes", "starts_at", "expires_at"]


class SessionUserSerializer(serializers.ModelSerializer):
    """The signed-in person (contract §2 SessionUser)."""

    id = serializers.CharField(source="public_id")
    phone = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()
    content_grant = ContentGrantSerializer(source="active_grant", allow_null=True)

    class Meta:
        model = User
        fields = ["id", "role", "name", "email", "phone", "client_code", "permissions", "content_grant"]

    def get_phone(self, user) -> str | None:
        return user.phone or None

    def get_permissions(self, user) -> list[str]:
        return sorted(user.effective_permissions)


class AuthSerializer(serializers.Serializer):
    """Response of every successful sign-in."""

    access = serializers.CharField(help_text="Access token, send it as `Authorization: Bearer <access>`.")
    refresh = serializers.CharField(help_text="Refresh token, exchange it at POST /auth/refresh.")
    user = SessionUserSerializer()


class TokenPairSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()


class PendingVerificationSerializer(serializers.Serializer):
    pending_verification = serializers.BooleanField()
    email = serializers.EmailField()
    expires_in = serializers.IntegerField(help_text="Seconds before the code expires.")


# ───────── Input ─────────


class SignInSerializer(serializers.Serializer):
    email = EmailField()
    password = serializers.CharField(trim_whitespace=False)


class SignUpSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    email = EmailField()
    phone = PhoneField()
    password = serializers.CharField(trim_whitespace=False, max_length=128)
    lang = lang_field()

    def validate(self, attrs):
        check_password_strength(attrs["password"], email=attrs["email"], name=attrs["name"])
        return attrs


class VerifyEmailSerializer(serializers.Serializer):
    email = EmailField()
    code = serializers.RegexField(r"^\s*\d{6}\s*$", error_messages={"invalid": "Enter the 6-digit code."})


class EmailRequestSerializer(serializers.Serializer):
    email = EmailField()
    lang = lang_field()


class RefreshSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class ProfileSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120, required=False)
    phone = PhoneField(required=False)


class PasswordResetSerializer(serializers.Serializer):
    token = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False, max_length=128)


class PasswordChangeSerializer(serializers.Serializer):
    current_password = serializers.CharField(trim_whitespace=False)
    new_password = serializers.CharField(trim_whitespace=False, max_length=128)


class GoogleSignInSerializer(serializers.Serializer):
    email = EmailField(help_text="Email verified by Google.")
    name = serializers.CharField(max_length=120, required=False, allow_blank=True)


class InvitationAcceptSerializer(serializers.Serializer):
    token = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False, max_length=128)


class ContentGrantInputSerializer(serializers.Serializer):
    scopes = serializers.ListField(child=serializers.ChoiceField(choices=GrantScope.choices), min_length=1)
    starts_at = serializers.DateTimeField(required=False)
    expires_at = serializers.DateTimeField(required=False, allow_null=True)
