from core.routing import route

from . import views

urlpatterns = [
    route("auth/sign-in", views.SignInView.as_view(), "sign-in"),
    route("auth/sign-up", views.SignUpView.as_view(), "sign-up"),
    route("auth/verify-email", views.VerifyEmailView.as_view(), "verify-email"),
    route("auth/verify-email/resend", views.ResendCodeView.as_view(), "verify-email-resend"),
    route("auth/refresh", views.RefreshView.as_view(), "token-refresh"),
    route("auth/sign-out", views.SignOutView.as_view(), "sign-out"),
    route("auth/me", views.MeView.as_view(), "auth-me"),
    route("me", views.MeView.as_view(), "me"),
    route("auth/password/forgot", views.PasswordForgotView.as_view(), "password-forgot"),
    route("auth/password/reset", views.PasswordResetView.as_view(), "password-reset"),
    route("auth/password/change", views.PasswordChangeView.as_view(), "password-change"),
    route("auth/google", views.GoogleSignInView.as_view(), "google-sign-in"),
    route("auth/invitations/accept", views.InvitationAcceptView.as_view(), "invitation-accept"),
]
