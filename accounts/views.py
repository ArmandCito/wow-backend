"""
Authentication and profile (contract §2). Every sign-in answers {access, refresh, user}.
"""

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from core.errors import AccountSuspended, Forbidden
from core.schema import errors
from core.throttles import VisitorRateThrottle, from_website

from . import services
from .models import PendingSignup, User
from .serializers import (
    AuthSerializer,
    EmailRequestSerializer,
    GoogleSignInSerializer,
    InvitationAcceptSerializer,
    PasswordChangeSerializer,
    PasswordResetSerializer,
    PendingVerificationSerializer,
    ProfileSerializer,
    RefreshSerializer,
    SessionUserSerializer,
    SignInSerializer,
    SignUpSerializer,
    TokenPairSerializer,
    VerifyEmailSerializer,
)


def validated(serializer_class, request):
    serializer = serializer_class(data=request.data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


class PublicView(APIView):
    """Endpoints used before signing in: no token needed, limited per visitor."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [VisitorRateThrottle]


class SignInView(PublicView):
    throttle_scope = "sign_in"

    @extend_schema(summary="Sign in with email and password", request=SignInSerializer,
                   responses={200: AuthSerializer, **errors(401, 403, 422, 429)})
    def post(self, request):
        data = validated(SignInSerializer, request)
        user = services.sign_in(data["email"], data["password"])
        return Response(services.issue_tokens(user))


class SignUpView(PublicView):
    throttle_scope = "sign_up"

    @extend_schema(
        summary="Sign up (client): emails a 6-digit code",
        description="Nothing is created yet: the account exists once the code is verified (POST /auth/verify-email).",
        request=SignUpSerializer,
        responses={202: PendingVerificationSerializer, **errors(409, 422, 429, 503)},
    )
    def post(self, request):
        data = validated(SignUpSerializer, request)
        services.start_signup(**data)
        return Response(
            {
                "pending_verification": True,
                "email": data["email"],
                "expires_in": int(PendingSignup.LIFETIME.total_seconds()),
            },
            status=status.HTTP_202_ACCEPTED,
        )


class VerifyEmailView(PublicView):
    throttle_scope = "email_code"

    @extend_schema(
        summary="Verify the email code: creates the client account and signs in",
        description="Codes are valid 10 minutes, 5 attempts. `invalid_code` details: `{attemptsLeft}`.",
        request=VerifyEmailSerializer,
        responses={201: AuthSerializer, **errors(400, 409, 410, 422, 429)},
    )
    def post(self, request):
        data = validated(VerifyEmailSerializer, request)
        user = services.verify_signup(data["email"], data["code"])
        return Response(services.issue_tokens(user), status=status.HTTP_201_CREATED)


class ResendCodeView(PublicView):
    throttle_scope = "email_code"

    @extend_schema(
        summary="Send a new email code",
        description="At most one code every 30 seconds (`429` with `details.retryAfter`). Always 202 otherwise.",
        request=EmailRequestSerializer,
        responses={202: None, **errors(422, 429, 503)},
    )
    def post(self, request):
        data = validated(EmailRequestSerializer, request)
        services.resend_signup_code(data["email"], data["lang"])
        return Response(status=status.HTTP_202_ACCEPTED)


class RefreshView(PublicView):
    throttle_classes = []

    @extend_schema(
        summary="New access token",
        description="The refresh token is rotated: keep the new `refresh`, the old one stops working.",
        request=RefreshSerializer,
        responses={200: TokenPairSerializer, **errors(401, 403)},
    )
    def post(self, request):
        data = validated(RefreshSerializer, request)
        try:
            refresh = RefreshToken(data["refresh"])
            user = User.objects.filter(pk=refresh.payload.get("user_id")).first()
        except TokenError:
            user = None
            refresh = None
        if user is None:
            raise InvalidToken("Invalid or expired refresh token.")
        if not user.is_active:
            services.revoke_sessions(user)
            raise AccountSuspended()

        refresh.blacklist()
        new = RefreshToken.for_user(user)
        return Response({"access": str(new.access_token), "refresh": str(new)})


class SignOutView(PublicView):
    throttle_classes = []

    @extend_schema(summary="Sign out (revokes the refresh token)", request=RefreshSerializer,
                   responses={204: None})
    def post(self, request):
        data = validated(RefreshSerializer, request)
        try:
            RefreshToken(data["refresh"]).blacklist()
        except TokenError:
            pass  # already invalid: signing out is still a success
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(summary="The signed-in person", responses={200: SessionUserSerializer, **errors(401, 403)})
    def get(self, request):
        return Response(SessionUserSerializer(request.user).data)

    @extend_schema(summary="Update name and phone (the email is the sign-in identity)",
                   request=ProfileSerializer, responses={200: SessionUserSerializer, **errors(401, 403, 422)})
    def patch(self, request):
        data = validated(ProfileSerializer, request)
        user = request.user
        for field, value in data.items():
            setattr(user, field, value)
        if data:
            user.save(update_fields=list(data))
        return Response(SessionUserSerializer(user).data)


class PasswordForgotView(PublicView):
    throttle_scope = "password_reset"

    @extend_schema(
        summary="Email a password reset link",
        description="Always 202 (never reveals whether the email has an account). "
        "The link opens `{FRONTEND_URL}/{lang}/forgot-password?token=…`, valid 1 hour.",
        request=EmailRequestSerializer,
        responses={202: None, **errors(422, 429, 503)},
    )
    def post(self, request):
        data = validated(EmailRequestSerializer, request)
        services.request_password_reset(data["email"], data["lang"])
        return Response(status=status.HTTP_202_ACCEPTED)


class PasswordResetView(PublicView):
    throttle_scope = "password_reset"

    @extend_schema(summary="Choose a new password with the emailed token (signs out everywhere)",
                   request=PasswordResetSerializer, responses={204: None, **errors(400, 422, 429)})
    def post(self, request):
        data = validated(PasswordResetSerializer, request)
        services.reset_password(data["token"], data["password"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Change the password (signed in)",
        description="Other sessions are signed out; the response carries new tokens for this one.",
        request=PasswordChangeSerializer,
        responses={200: AuthSerializer, **errors(401, 422)},
    )
    def post(self, request):
        data = validated(PasswordChangeSerializer, request)
        services.change_password(request.user, data["current_password"], data["new_password"])
        return Response(services.issue_tokens(request.user))


class GoogleSignInView(PublicView):
    throttle_classes = []

    @extend_schema(
        summary="Google sign-in (server-to-server, from the website)",
        description="The website runs the OAuth flow and sends the Google-verified email. Requires the "
        "`X-Frontend-Secret` header. 200 = existing account, 201 = new client account.",
        request=GoogleSignInSerializer,
        responses={200: AuthSerializer, 201: AuthSerializer, **errors(403, 422)},
    )
    def post(self, request):
        if not from_website(request):
            raise Forbidden("Only the website server may call this endpoint.")
        data = validated(GoogleSignInSerializer, request)
        user, created = services.google_sign_in(data["email"], data.get("name", ""))
        return Response(services.issue_tokens(user), status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class InvitationAcceptView(PublicView):
    throttle_scope = "password_reset"

    @extend_schema(
        summary="Accept a staff invitation: choose a password and sign in",
        description="The invitation email links to `{FRONTEND_URL}/{lang}/accept-invitation?token=…` (valid 7 days).",
        request=InvitationAcceptSerializer,
        responses={200: AuthSerializer, **errors(400, 422, 429)},
    )
    def post(self, request):
        data = validated(InvitationAcceptSerializer, request)
        user = services.accept_invitation(data["token"], data["password"])
        return Response(services.issue_tokens(user))

