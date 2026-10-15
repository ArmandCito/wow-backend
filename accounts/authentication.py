from rest_framework_simplejwt import authentication
from rest_framework_simplejwt.exceptions import InvalidToken

from core.errors import AccountSuspended

from .models import Status


class JWTAuthentication(authentication.JWTAuthentication):
    """
    Bearer access token, checked against the account's *current* state on every request:
    a suspended staff member is refused at once (403 account_suspended), even with a valid token.
    Permissions are recomputed from the database, never read from the token.
    """

    def get_user(self, validated_token):
        user = super().get_user(validated_token)  # unknown account -> 401
        if user.status == Status.SUSPENDED:
            raise AccountSuspended()
        if user.status != Status.ACTIVE:
            raise InvalidToken("Inactive account.")
        return user
