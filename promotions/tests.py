from core.testing import ApiTestCase


class CampaignTests(ApiTestCase):
    def test_seeded_promotions_are_public(self):
        promotions = self.api.get("/api/v1/promotions").json()
        self.assertEqual([p["id"] for p in promotions], ["weekday-combo", "new-pizza", "free-delivery-friday"])
        self.assertEqual(promotions[0]["highlight"]["labelFirst"], True)

    def test_workflow(self):
        owner = self.as_user(self.owner)
        created = owner.post("/api/v1/admin/campaigns", {
            "title": {"en": "Pizza night", "fr": "Soirée pizza"}, "ctaCategory": "pizza",
            "startsAt": "2099-01-01T18:00:00+02:00",
        }, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual((created.json()["status"], created.json()["link"]), ("draft", "/menu?category=pizza"))

        self.assertEqual(owner.post("/api/v1/admin/campaigns/pizza-night/publish").json()["status"], "scheduled")
        self.assertNotIn("pizza-night", [p["id"] for p in self.api.get("/api/v1/promotions").json()])
        self.assertError(owner.delete("/api/v1/admin/campaigns/pizza-night"), 409, "conflict")

        owner.patch("/api/v1/admin/campaigns/pizza-night", {"startsAt": None}, format="json")
        self.assertIn("pizza-night", [p["id"] for p in self.api.get("/api/v1/promotions").json()])
        self.assertEqual(owner.post("/api/v1/admin/campaigns/pizza-night/pause").json()["status"], "paused")
        self.assertNotIn("pizza-night", [p["id"] for p in self.api.get("/api/v1/promotions").json()])

    def test_managers_need_a_grant(self):
        self.assertError(self.as_user(self.eric).get("/api/v1/admin/campaigns"), 403, "forbidden")
