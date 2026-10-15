"""OpenAPI helpers: tags by URL and the shared error response."""

from drf_spectacular.contrib.rest_framework_simplejwt import SimpleJWTScheme
from drf_spectacular.openapi import AutoSchema as BaseAutoSchema
from drf_spectacular.utils import OpenApiResponse, inline_serializer
from rest_framework import serializers

TAGS_BY_PREFIX = [
    ("/api/v1/auth/", "Auth"),
    ("/api/v1/me/notifications", "Notifications"),
    ("/api/v1/me/orders", "Orders"),
    ("/api/v1/me", "Auth"),
    ("/api/v1/menu", "Catalogue"),
    ("/api/v1/promotions", "Catalogue"),
    ("/api/v1/business", "Catalogue"),
    ("/api/v1/orders/", "Register"),
    ("/api/v1/orders", "Orders"),
    ("/api/v1/admin/menu", "Content"),
    ("/api/v1/admin/uploads", "Content"),
    ("/api/v1/admin/campaigns", "Content"),
    ("/api/v1/admin/business", "Content"),
    ("/api/v1/admin/", "Staff"),
]


class AutoSchema(BaseAutoSchema):
    def get_tags(self):
        path = self.path
        for prefix, tag in TAGS_BY_PREFIX:
            if path.startswith(prefix):
                return [tag]
        return ["Other"]


ErrorSerializer = inline_serializer(
    name="Error",
    fields={
        "error": inline_serializer(
            name="ErrorBody",
            fields={
                "code": serializers.CharField(),
                "message": serializers.CharField(),
                "details": serializers.DictField(),
            },
        )
    },
)


def errors(*codes):
    """`responses={200: X, **errors(401, 422)}` documents the error responses of a view."""
    descriptions = {
        400: "bad_request / invalid_code / invalid_or_expired_token",
        401: "unauthenticated / invalid_credentials",
        403: "forbidden / account_suspended / not_assigned / staff_password_only",
        404: "not_found",
        409: "conflict / email_taken / invalid_transition / item_unavailable",
        410: "code_expired",
        422: "validation_failed",
        429: "too_many_attempts",
        503: "email_unavailable",
    }
    return {code: OpenApiResponse(ErrorSerializer, description=descriptions.get(code, "")) for code in codes}


class BearerTokenScheme(SimpleJWTScheme):
    """Swagger "Authorize" button for our JWT authentication class."""

    target_class = "accounts.authentication.JWTAuthentication"
    name = "bearerAuth"
