"""Account use cases. Views stay thin: they validate input, call one of these and shape the response."""

from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import update_last_login
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from audit.services import record
from core import emails
from core.errors import (
    AccountSuspended,
    CodeExpired,
    EmailTaken,
    InvalidCode,
    InvalidCredentials,
    InvalidToken,
    StaffPasswordOnly,
    TooManyAttempts,
)

from .models import AccountToken, PendingSignup, Role, Status, User
from .serializers import SessionUserSerializer, check_password_strength


def issue_tokens(user):
    """Signs the user in: {access, refresh, user}."""
    refresh = RefreshToken.for_user(user)
    update_last_login(None, user)
    return {"access": str(refresh.access_token), "refresh": str(refresh), "user": SessionUserSerializer(user).data}


def revoke_sessions(user):
    """Revokes every refresh token of the user (password reset, suspension)."""
    for token in OutstandingToken.objects.filter(user=user, expires_at__gt=timezone.now()):
        BlacklistedToken.objects.get_or_create(token=token)


# ───────── Sign-in ─────────


def sign_in(email, password):
    user = User.objects.filter(email=email).first()
    if user is None:
        make_password(password)  # same work as a real check: no timing hint that the email is unknown
        raise InvalidCredentials()
    if not user.check_password(password) or user.status == Status.INVITED:
        raise InvalidCredentials()
    if user.status == Status.SUSPENDED:
        raise AccountSuspended()
    return user


# ───────── Sign-up with an email code ─────────


def start_signup(*, name, email, phone, password, lang):
    if User.objects.filter(email=email).exists():
        raise EmailTaken()
    with transaction.atomic():
        pending = PendingSignup.objects.select_for_update().filter(email=email).first() or PendingSignup(email=email)
        wait = pending.seconds_before_resend() if pending.pk else 0
        if not wait:
            pending.name, pending.phone, pending.lang = name, phone, lang
            pending.password = make_password(password)
            code = pending.new_code()
            pending.save()
    if wait:
        raise TooManyAttempts("Wait before asking for a new code.", details={"retry_after": wait})
    emails.send("signup_code", email, lang, name=name, code=code, minutes=_minutes(PendingSignup.LIFETIME))
    return pending


def resend_signup_code(email, lang=None):
    """Silently does nothing for an unknown email (never reveals which emails sign up)."""
    with transaction.atomic():
        pending = PendingSignup.objects.select_for_update().filter(email=email).first()
        if pending is None:
            return
        wait = pending.seconds_before_resend()
        if not wait:
            code = pending.new_code()
            pending.save()
    if wait:
        raise TooManyAttempts("Wait before asking for a new code.", details={"retry_after": wait})
    emails.send(
        "signup_code", email, lang or pending.lang, name=pending.name, code=code,
        minutes=_minutes(PendingSignup.LIFETIME),
    )


def verify_signup(email, code):
    """Creates the client account once the code is right. Errors are raised after the attempt is saved."""
    error = None
    with transaction.atomic():
        pending = PendingSignup.objects.select_for_update().filter(email=email).first()
        if pending is None:
            error = InvalidCode()
        elif pending.attempts >= PendingSignup.MAX_ATTEMPTS:
            error = TooManyAttempts("Too many wrong codes. Ask for a new code.")
        elif pending.is_expired:
            error = CodeExpired()
        elif not pending.code_matches(code.strip()):
            pending.attempts += 1
            pending.save(update_fields=["attempts"])
            error = InvalidCode(details={"attempts_left": PendingSignup.MAX_ATTEMPTS - pending.attempts})
        elif User.objects.filter(email=email).exists():
            pending.delete()
            error = EmailTaken()
        else:
            user = User(email=email, name=pending.name, phone=pending.phone, role=Role.CLIENT, password=pending.password)
            user.save_with_public_id()
            pending.delete()
    if error:
        raise error
    return user


# ───────── Password ─────────


def request_password_reset(email, lang):
    """Always succeeds from the outside: never reveals whether the email has an account."""
    user = User.objects.filter(email=email, status=Status.ACTIVE).first()
    if user is None:
        return
    raw = AccountToken.issue(user, AccountToken.Purpose.PASSWORD_RESET)
    emails.send(
        "password_reset", user.email, lang, name=user.name,
        link=emails.frontend_link(lang, "/forgot-password", token=raw),
        minutes=_minutes(AccountToken.LIFETIMES[AccountToken.Purpose.PASSWORD_RESET]),
    )


@transaction.atomic
def reset_password(raw_token, password):
    user = AccountToken.consume(raw_token, AccountToken.Purpose.PASSWORD_RESET)
    if user is None:
        raise InvalidToken()
    check_password_strength(password, email=user.email, name=user.name)  # rolls the token back on failure
    user.set_password(password)
    user.save(update_fields=["password"])
    revoke_sessions(user)
    return user


def change_password(user, current, new):
    if not user.check_password(current):
        raise serializers.ValidationError(
            {"current_password": serializers.ErrorDetail("The current password is wrong.", code="incorrect")}
        )
    check_password_strength(new, email=user.email, name=user.name)
    user.set_password(new)
    user.save(update_fields=["password"])
    revoke_sessions(user)


# ───────── Google (OAuth done by the website) ─────────


def google_sign_in(email, name):
    """The account matching a Google-verified email, or a new client account. Returns (user, created)."""
    user = User.objects.filter(email=email).first()
    if user is not None:
        if user.is_staff_member:
            raise StaffPasswordOnly()
        if user.status != Status.ACTIVE:
            raise AccountSuspended()
        return user, False
    PendingSignup.objects.filter(email=email).delete()  # Google already verified this email
    user = User.objects.create_user(email, name=name or email.split("@")[0].capitalize())
    return user, True


# ───────── Staff invitation ─────────


@transaction.atomic
def accept_invitation(raw_token, password):
    user = AccountToken.consume(raw_token, AccountToken.Purpose.INVITATION)
    if user is None or user.status != Status.INVITED:
        raise InvalidToken()
    check_password_strength(password, email=user.email, name=user.name)
    user.set_password(password)
    user.status = Status.ACTIVE
    user.save(update_fields=["password", "status"])
    record(
        actor=user, scope="access", type="invitation.accepted", target=user, data={"email": user.email},
        text=("Invitation accepted · {email}", "Invitation acceptée · {email}"), values={"email": user.email},
    )
    return user


def _minutes(delta):
    return int(delta.total_seconds() // 60)
