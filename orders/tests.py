from accounts.models import Status, User
from business.models import BusinessSettings
from core.testing import ApiTestCase
from menu.models import MenuItem
from notifications.models import ClientNotification


class CheckoutTests(ApiTestCase):
    def test_client_order_is_priced_by_the_server(self):
        response = self.place_order(
            self.as_user(self.aline),
            lines=[
                {"itemId": "chips-marinated-chicken-leg", "quantity": 2, "choices": ["extra-cheese", "no-salt"]},
                {"itemId": "fresh-mint-mojito", "quantity": 1},
            ],
            contact={},
        )
        self.assertEqual(response.status_code, 201, response.content)
        order = response.json()["order"]
        self.assertRegex(order["id"], r"^ORD-\d{4}$")
        self.assertEqual((order["clientCode"], order["guest"]), (self.aline.client_code, False))
        self.assertEqual(order["lines"][0]["unitPrice"], 7000 + 700)
        self.assertEqual((order["subtotal"], order["total"]), (15400 + 3000, 18400))
        self.assertEqual(order["contact"], {"name": "Aline", "phone": "078 123 4567"})
        self.assertEqual(list(order["history"]), ["new"])
        self.assertTrue(ClientNotification.objects.filter(client=self.aline, stage="new").exists())

    def test_guest_order_and_fees(self):
        settings = BusinessSettings.load()
        settings.service_fee, settings.delivery_fee = 100, 1000
        settings.save()
        response = self.place_order(fulfilment="delivery", address="KG 7 Ave")
        order = response.json()["order"]
        self.assertEqual((order["guest"], order["clientCode"], order["fees"]), (True, "", 1100))
        self.assertError(self.place_order(fulfilment="delivery"), 422, "validation_failed")  # no address
        self.assertError(self.place_order(contact={"name": "No phone"}), 422, "validation_failed")

    def test_unavailable_items_and_invalid_options(self):
        MenuItem.objects.filter(slug="fresh-mint-mojito").update(is_available=False)
        response = self.place_order(lines=[{"itemId": "fresh-mint-mojito", "quantity": 1}, {"itemId": "ghost", "quantity": 1}])
        self.assertError(response, 409, "item_unavailable")
        self.assertEqual(response.json()["error"]["details"]["itemIds"], ["fresh-mint-mojito", "ghost"])

        response = self.place_order(lines=[{"itemId": "wow-toasted-burger", "quantity": 1, "choices": ["extra-cheese"]}])
        self.assertError(response, 422, "validation_failed")
        self.assertEqual(response.json()["error"]["details"], {"lines.0.choices": "invalid_choice"})

    def test_staff_cannot_order(self):
        self.assertError(self.place_order(self.as_user(self.eric)), 403, "forbidden")


class RegisterTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.order = self.place_order(self.as_user(self.aline), contact={}).json()["order"]
        self.manager = User.objects.get(staff_id=self.order["managerId"])
        self.other = self.nadia if self.manager == self.eric else self.eric

    def move(self, user, to):
        return self.as_user(user).post(f"/api/v1/orders/{self.order['id']}/transition", {"to": to}, format="json")

    def test_happy_path_marks_paid_and_notifies(self):
        for stage in ("accepted", "preparing", "ready", "completed"):
            response = self.move(self.manager, stage)
            self.assertEqual(response.status_code, 200, response.content)
        order = response.json()["order"]
        self.assertEqual((order["stage"], order["paymentStatus"]), ("completed", "paid"))
        self.assertEqual(set(order["history"]), {"new", "accepted", "preparing", "ready", "completed"})
        texts = ClientNotification.objects.filter(client=self.aline).values_list("text_fr", flat=True)
        self.assertTrue(any("a accepté votre commande" in text for text in texts))

    def test_rules(self):
        self.assertError(self.move(self.manager, "ready"), 409, "invalid_transition")
        self.assertError(self.move(self.other, "accepted"), 403, "not_assigned")
        self.assertError(self.move(self.aline, "accepted"), 403, "forbidden")
        self.assertEqual(self.move(self.owner, "cancelled").json()["order"]["paymentStatus"], "not-charged")
        self.assertError(self.move(self.manager, "accepted"), 409, "invalid_transition")

    def test_queue_and_client_views(self):
        queue = self.as_user(self.eric).get("/api/v1/orders?stage=active").json()
        self.assertEqual([order["id"] for order in queue], [self.order["id"]])
        self.assertEqual(self.as_user(self.aline).get("/api/v1/me/orders?status=active").json()[0]["id"], self.order["id"])
        other_client = User.objects.create_user("x@test.rw", "Pass-word-99", name="X")
        self.assertError(self.as_user(other_client).get(f"/api/v1/me/orders/{self.order['id']}"), 404, "not_found")

    def test_suspended_manager_orders_move_and_token_stops_working(self):
        self.as_user(self.owner).post(f"/api/v1/admin/managers/{self.manager.staff_id}/suspend")
        self.assertError(self.as_user(self.manager).get("/api/v1/auth/me"), 403, "account_suspended")
        moved = self.as_user(self.owner).get(f"/api/v1/orders/{self.order['id']}").json()
        self.assertEqual(moved["managerId"], self.other.staff_id)
        self.assertEqual(User.objects.get(pk=self.manager.pk).status, Status.SUSPENDED)
