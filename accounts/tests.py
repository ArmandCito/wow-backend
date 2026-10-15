import re

from django.core import mail
from django.test import override_settings

from accounts.models import AccountToken, PendingSignup, Status, User
from core.testing import PASSWORD, ApiTestCase


def code_from_email():
    return re.search(r"\b(\d{6})\b", mail.outbox[-1].body).group(1)


class SignUpTests(ApiTestCase):
    signup = {"name": "Jean", "email": "Jean@Test.rw", "phone": "+250 788 000 111", "password": PASSWORD, "lang": "fr"}

    def test_sign_up_then_verify_creates_the_account_and_signs_in(self):
        response = self.api.post("/api/v1/auth/sign-up", self.signup, format="json")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json(), {"pendingVerification": True, "email": "jean@test.rw", "expiresIn": 600})
        self.assertFalse(User.objects.filter(email="jean@test.rw").exists())  # nothing created yet
        self.assertIn("Votre code", mail.outbox[-1].subject)  # French email

        response = self.api.post("/api/v1/auth/verify-email", {"email": "jean@test.rw", "code": code_from_email()}, format="json")
        self.assertEqual(response.status_code, 201)
        user = response.json()["user"]
        self.assertEqual((user["role"], user["phone"]), ("client", "078 800 0111"))
        self.assertRegex(user["clientCode"], r"^WQB\d{3}[A-Z]$")
        self.assertEqual(user["id"], user["clientCode"])
        self.assertFalse(PendingSignup.objects.exists())

    def test_wrong_codes_are_counted_then_blocked(self):
        self.api.post("/api/v1/auth/sign-up", self.signup, format="json")
        for attempts_left in (4, 3, 2, 1, 0):
            response = self.api.post("/api/v1/auth/verify-email", {"email": "jean@test.rw", "code": "000000"}, format="json")
            self.assertError(response, 400, "invalid_code")
            self.assertEqual(response.json()["error"]["details"], {"attemptsLeft": attempts_left})
        response = self.api.post("/api/v1/auth/verify-email", {"email": "jean@test.rw", "code": code_from_email()}, format="json")
        self.assertError(response, 429, "too_many_attempts")

    def test_resend_waits_30_seconds(self):
        self.api.post("/api/v1/auth/sign-up", self.signup, format="json")
        response = self.api.post("/api/v1/auth/verify-email/resend", {"email": "jean@test.rw"}, format="json")
        self.assertError(response, 429, "too_many_attempts")
        self.assertIn("retryAfter", response.json()["error"]["details"])
        self.assertIn("Retry-After", response.headers)

    def test_existing_email_and_bad_input(self):
        self.assertError(self.api.post("/api/v1/auth/sign-up", {**self.signup, "email": "aline@test.rw"}, format="json"),
                         409, "email_taken")
        response = self.api.post("/api/v1/auth/sign-up", {**self.signup, "phone": "12345", "password": "123"}, format="json")
        self.assertError(response, 422, "validation_failed")
        self.assertEqual(response.json()["error"]["details"]["phone"], "invalid_phone")


class SignInTests(ApiTestCase):
    def sign_in(self, email, password=PASSWORD):
        return self.api.post("/api/v1/auth/sign-in", {"email": email, "password": password}, format="json")

    def test_sign_in_returns_tokens_and_the_session_user(self):
        response = self.sign_in("ERIC@test.rw")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(set(body), {"access", "refresh", "user"})
        self.assertEqual(body["user"]["id"], "eric")
        self.assertEqual(body["user"]["permissions"], ["orders:process"])
        self.assertIsNone(body["user"]["clientCode"])

    def test_wrong_password_and_suspended_account(self):
        self.assertError(self.sign_in("eric@test.rw", "nope"), 401, "invalid_credentials")
        self.assertError(self.sign_in("nobody@test.rw"), 401, "invalid_credentials")
        User.objects.filter(pk=self.nadia.pk).update(status=Status.SUSPENDED)
        self.assertError(self.sign_in("nadia@test.rw"), 403, "account_suspended")

    def test_refresh_rotates_and_sign_out_revokes(self):
        refresh = self.sign_in("aline@test.rw").json()["refresh"]
        rotated = self.api.post("/api/v1/auth/refresh", {"refresh": refresh}, format="json")
        self.assertEqual(rotated.status_code, 200)
        self.assertError(self.api.post("/api/v1/auth/refresh", {"refresh": refresh}, format="json"), 401, "unauthenticated")

        new_refresh = rotated.json()["refresh"]
        self.assertEqual(self.api.post("/api/v1/auth/sign-out", {"refresh": new_refresh}, format="json").status_code, 204)
        self.assertError(self.api.post("/api/v1/auth/refresh", {"refresh": new_refresh}, format="json"), 401, "unauthenticated")

    def test_sign_in_is_rate_limited(self):
        for _ in range(10):
            self.sign_in("aline@test.rw", "wrong")
        self.assertError(self.sign_in("aline@test.rw"), 429, "too_many_attempts")

    def test_profile_update(self):
        response = self.as_user(self.aline).patch("/api/v1/me", {"name": "Aline U.", "phone": "0788 111 222"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.json()["name"], response.json()["phone"]), ("Aline U.", "078 811 1222"))


class PasswordTests(ApiTestCase):
    def test_reset_flow(self):
        response = self.api.post("/api/v1/auth/password/forgot", {"email": "aline@test.rw"}, format="json")
        self.assertEqual(response.status_code, 202)
        token = re.search(r"token=([\w-]+)", mail.outbox[-1].body).group(1)
        self.assertIn("/en/forgot-password?token=", mail.outbox[-1].body)

        weak = self.api.post("/api/v1/auth/password/reset", {"token": token, "password": "123"}, format="json")
        self.assertError(weak, 422, "validation_failed")  # the token is still usable after a weak password
        ok = self.api.post("/api/v1/auth/password/reset", {"token": token, "password": "New-Password-77"}, format="json")
        self.assertEqual(ok.status_code, 204)
        again = self.api.post("/api/v1/auth/password/reset", {"token": token, "password": "Other-Password-77"}, format="json")
        self.assertError(again, 400, "invalid_or_expired_token")

    def test_unknown_email_looks_the_same(self):
        response = self.api.post("/api/v1/auth/password/forgot", {"email": "nobody@test.rw"}, format="json")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(len(mail.outbox), 0)


@override_settings(FRONTEND_SHARED_SECRET="s3cret")
class GoogleAndInvitationTests(ApiTestCase):
    def google(self, email, secret="s3cret"):
        return self.api.post("/api/v1/auth/google", {"email": email, "name": "G User"}, format="json",
                             HTTP_X_FRONTEND_SECRET=secret)

    def test_google_needs_the_website_secret(self):
        self.assertError(self.google("new@test.rw", secret="wrong"), 403, "forbidden")

    def test_google_creates_or_finds_clients_and_refuses_staff(self):
        self.assertEqual(self.google("new@test.rw").status_code, 201)
        self.assertEqual(self.google("new@test.rw").status_code, 200)
        self.assertError(self.google("eric@test.rw"), 403, "staff_password_only")

    def test_invitation_accept(self):
        invited = User.objects.create_staff("sam@test.rw", "Sam", status=Status.INVITED)
        token = AccountToken.issue(invited, AccountToken.Purpose.INVITATION)
        response = self.api.post("/api/v1/auth/invitations/accept", {"token": token, "password": PASSWORD}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["role"], "manager")
        invited.refresh_from_db()
        self.assertEqual(invited.status, Status.ACTIVE)
