from django.core import mail

from core.testing import ApiTestCase


class StaffAdminTests(ApiTestCase):
    def test_directory_grant_and_audit(self):
        owner = self.as_user(self.owner)
        directory = owner.get("/api/v1/admin/managers").json()
        self.assertEqual({m["id"] for m in directory}, {"eric", "nadia"})

        grant = owner.put("/api/v1/admin/managers/eric/grant", {"scopes": ["drinks", "food"]}, format="json")
        self.assertEqual(grant.status_code, 200, grant.content)
        self.assertEqual(grant.json()["scopes"], ["food", "drinks"])
        me = self.as_user(self.eric).get("/api/v1/auth/me").json()
        self.assertEqual(me["permissions"], ["menu:edit", "orders:process"])

        self.assertEqual(owner.delete("/api/v1/admin/managers/eric/grant").status_code, 204)
        self.assertEqual(self.as_user(self.eric).get("/api/v1/auth/me").json()["permissions"], ["orders:process"])

        audit = owner.get("/api/v1/admin/audit?scope=access&limit=1").json()
        self.assertEqual(audit["items"][0]["type"], "grant.revoked")
        self.assertIsNotNone(audit["nextCursor"])

    def test_invitation_and_suspension_rules(self):
        owner = self.as_user(self.owner)
        invited = owner.post("/api/v1/admin/invitations", {"name": "Sam K", "email": "sam@test.rw"}, format="json")
        self.assertEqual((invited.status_code, invited.json()["status"]), (201, "invited"))
        self.assertIn("/en/accept-invitation?token=", mail.outbox[-1].body)
        self.assertError(owner.post("/api/v1/admin/invitations", {"name": "Sam", "email": "sam@test.rw"}, format="json"),
                         409, "email_taken")

        owner.post("/api/v1/admin/managers/nadia/suspend")
        response = owner.patch("/api/v1/admin/managers/nadia", {"duty": "on"}, format="json")
        self.assertError(response, 409, "manager_suspended")

    def test_only_the_superadmin(self):
        self.assertError(self.as_user(self.eric).get("/api/v1/admin/managers"), 403, "forbidden")
        self.assertError(self.api.get("/api/v1/admin/overview"), 401, "unauthenticated")
        overview = self.as_user(self.owner).get("/api/v1/admin/overview").json()
        self.assertEqual(overview["managers"]["onDuty"], 2)
