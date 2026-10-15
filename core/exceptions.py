"""
One error format for the whole API (contract §11):

    {"error": {"code": "validation_failed", "message": "Human-readable, for logs", "details": {...}}}

- `code` is stable and translated by the website; `message` is never shown to users.
- Validation errors are 422 with `details: {"field": "reason"}` (nested fields as "lines.0.itemId").
"""

import logging
import math

from django.conf import settings
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from .errors import ApiError, Forbidden, NotFound

logger = logging.getLogger(__name__)

CODES_BY_CLASS = [
    (exceptions.NotAuthenticated, "unauthenticated"),
    (exceptions.AuthenticationFailed, "unauthenticated"),
    (exceptions.PermissionDenied, "forbidden"),
    (exceptions.NotFound, "not_found"),
    (exceptions.MethodNotAllowed, "method_not_allowed"),
    (exceptions.Throttled, "too_many_attempts"),
    (exceptions.UnsupportedMediaType, "unsupported_media_type"),
    (exceptions.ParseError, "bad_request"),
]


def api_exception_handler(exc, context):
    if isinstance(exc, Http404):
        exc = NotFound()
    elif isinstance(exc, DjangoPermissionDenied):
        exc = Forbidden()

    response = drf_exception_handler(exc, context)

    if response is None:
        # Unexpected error: logged with its traceback, generic answer to the client
        logger.exception("Unhandled API error", exc_info=exc)
        if settings.DEBUG:
            return None
        return Response(
            {"error": {"code": "server_error", "message": "Unexpected server error.", "details": {}}},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    if isinstance(exc, exceptions.ValidationError):
        details = flatten_errors(exc.detail)
        response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
        body = {"code": "validation_failed", "message": first_message(exc.detail), "details": details}
    elif isinstance(exc, ApiError):
        body = {"code": exc.get_codes(), "message": str(exc.detail), "details": exc.details}
    else:
        code = next((code for cls, code in CODES_BY_CLASS if isinstance(exc, cls)), "error")
        if code == "unauthenticated":
            # DRF answers 403 on views without an authenticator (public endpoints): keep 401
            response.status_code = status.HTTP_401_UNAUTHORIZED
        details = {}
        if isinstance(exc, exceptions.Throttled) and exc.wait is not None:
            details = {"retry_after": math.ceil(exc.wait)}
        detail = getattr(exc, "detail", exc)
        if isinstance(detail, dict):  # Simple JWT puts a dict in `detail`
            detail = detail.get("detail", "")
        body = {"code": code, "message": str(detail), "details": details}

    response.data = {"error": body}
    if body["details"].get("retry_after"):
        response["Retry-After"] = str(body["details"]["retry_after"])
    return response


def flatten_errors(detail, path=""):
    """{"lines": [{"item_id": ["required"]}]} -> {"lines.0.item_id": "required"}"""
    if isinstance(detail, dict):
        flat = {}
        for key, value in detail.items():
            flat.update(flatten_errors(value, f"{path}.{key}" if path else str(key)))
        return flat
    if isinstance(detail, list):
        if detail and all(isinstance(item, str) for item in detail):  # ErrorDetail is a str
            return {path or "non_field_errors": getattr(detail[0], "code", "invalid")}
        flat = {}
        for index, value in enumerate(detail):
            flat.update(flatten_errors(value, f"{path}.{index}" if path else str(index)))
        return flat
    return {path or "non_field_errors": getattr(detail, "code", "invalid")}


def first_message(detail):
    if isinstance(detail, dict):
        for key, value in detail.items():
            message = first_message(value)
            if message:
                return f"{key}: {message}"
        return ""
    if isinstance(detail, list):
        return next((m for m in (first_message(item) for item in detail) if m), "")
    return str(detail)
