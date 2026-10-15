"""
Business errors of the API.

Each error has a stable `code` that the website translates (EN/FR), so codes never change once
released. Raise them anywhere in a view or a service:

    raise InvalidTransition(details={"from": "new", "to": "ready"})

and the client receives `{"error": {"code": "invalid_transition", "message": "...", "details": {...}}}`.
"""

from rest_framework import status
from rest_framework.exceptions import APIException


class ApiError(APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "bad_request"
    default_detail = "Bad request."

    def __init__(self, message=None, *, details=None, code=None):
        super().__init__(message or self.default_detail, code or self.default_code)
        self.details = details or {}


# ───────── 400 ─────────


class InvalidCode(ApiError):
    default_code = "invalid_code"
    default_detail = "The verification code is not valid."


class InvalidToken(ApiError):
    default_code = "invalid_or_expired_token"
    default_detail = "This link is invalid or has expired."


# ───────── 401 / 403 ─────────


class InvalidCredentials(ApiError):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_code = "invalid_credentials"
    default_detail = "Invalid email or password."


class Forbidden(ApiError):
    status_code = status.HTTP_403_FORBIDDEN
    default_code = "forbidden"
    default_detail = "You do not have permission to do this."


class AccountSuspended(Forbidden):
    default_code = "account_suspended"
    default_detail = "This account is suspended."


class NotAssigned(Forbidden):
    default_code = "not_assigned"
    default_detail = "This order is assigned to another manager."


class StaffPasswordOnly(Forbidden):
    default_code = "staff_password_only"
    default_detail = "Staff accounts sign in with their password."


# ───────── 404 / 409 / 410 ─────────


class NotFound(ApiError):
    status_code = status.HTTP_404_NOT_FOUND
    default_code = "not_found"
    default_detail = "Not found."


class Conflict(ApiError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "conflict"
    default_detail = "This action conflicts with the current state."


class EmailTaken(Conflict):
    default_code = "email_taken"
    default_detail = "An account already exists with this email."


class InvalidTransition(Conflict):
    default_code = "invalid_transition"
    default_detail = "This order cannot move to that stage."


class ItemUnavailable(Conflict):
    default_code = "item_unavailable"
    default_detail = "Some items are not available."


class CodeExpired(ApiError):
    status_code = status.HTTP_410_GONE
    default_code = "code_expired"
    default_detail = "The verification code has expired. Ask for a new one."


# ───────── 422 / 429 / 503 ─────────


class ValidationFailed(ApiError):
    """Business-rule validation outside a serializer. `details` maps field -> reason code."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_code = "validation_failed"
    default_detail = "Some fields are not valid."


class TooManyAttempts(ApiError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    default_code = "too_many_attempts"
    default_detail = "Too many attempts. Try again later."


class EmailUnavailable(ApiError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_code = "email_unavailable"
    default_detail = "The email could not be sent. Try again in a moment."
