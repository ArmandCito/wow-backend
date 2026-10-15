"""Shared test helpers: `python manage.py test` (SQLite by default, no external service needed)."""

import io

from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import Assignment, Duty, User

PASSWORD = "Correct-Horse-42"


class ApiTestCase(TestCase):
    """Catalogue loaded from the seed, an owner, two managers on duty and a client."""

    @classmethod
    def setUpTestData(cls):
        call_command("seed", stdout=io.StringIO())
        cls.owner = User.objects.create_superuser("owner@test.rw", PASSWORD, name="Owner Test")
        cls.eric = User.objects.create_staff(
            "eric@test.rw", "Eric", password=PASSWORD, assignment=Assignment.PICKUP_REGISTER, duty=Duty.ON
        )
        cls.nadia = User.objects.create_staff(
            "nadia@test.rw", "Nadia", password=PASSWORD, assignment=Assignment.PICKUP_REGISTER, duty=Duty.ON
        )
        cls.aline = User.objects.create_user("aline@test.rw", PASSWORD, name="Aline", phone="078 123 4567")

    def setUp(self):
        from django.core.cache import cache

        cache.clear()  # rate limits start from zero in every test
        self.api = APIClient()

    def as_user(self, user):
        """An API client signed in as `user` (a real access token, like the website uses)."""
        from rest_framework_simplejwt.tokens import RefreshToken

        client = APIClient()
        if user is not None:
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
        return client

    def assertError(self, response, status, code):
        self.assertEqual(response.status_code, status, response.content)
        self.assertEqual(response.json()["error"]["code"], code)

    def place_order(self, client=None, **overrides):
        body = {
            "lines": [{"itemId": "wow-toasted-burger", "quantity": 1}],
            "fulfilment": "pickup",
            "payment": "pay-on-pickup",
            "contact": {"name": "Guest", "phone": "0781234567"},
            **overrides,
        }
        return (client or self.api).post("/api/v1/orders", body, format="json")

