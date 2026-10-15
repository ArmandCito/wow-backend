import io
import tempfile
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from PIL import Image

from accounts.models import ContentGrant
from core.models import Upload
from core.testing import ApiTestCase


class CatalogueTests(ApiTestCase):
    def test_catalogue_matches_the_website_types(self):
        response = self.api.get("/api/v1/menu")
        self.assertEqual(response.status_code, 200)
        self.assertIn("max-age=60", response.headers["Cache-Control"])
        body = response.json()
        self.assertEqual(set(body), {"categories", "drinkSections", "tags", "optionGroups", "items"})
        burger = next(item for item in body["items"] if item["id"] == "wow-toasted-burger")
        self.assertEqual(burger["name"]["fr"], "Burger toasté WOW")
        self.assertEqual((burger["price"], burger["group"], burger["categories"]), (6000, "food", ["burgers"]))
        self.assertEqual(body["tags"]["beef"], {"en": "Beef", "fr": "Bœuf"})

    def test_filters_and_lookups(self):
        drinks = self.api.get("/api/v1/menu/items?group=drinks&section=mojitos").json()
        self.assertTrue(drinks and all(item["section"] == "mojitos" for item in drinks))
        groups = self.api.get("/api/v1/menu/option-groups").json()
        self.assertEqual(groups["leave-out-chicken"]["kind"], "remove")
        self.assertError(self.api.get("/api/v1/menu/items/nope"), 404, "not_found")


class EditingTests(ApiTestCase):
    def grant(self, manager, scopes):
        ContentGrant.objects.create(manager=manager, granted_by=self.owner, scopes=scopes,
                                    expires_at=timezone.now() + timedelta(days=1))

    def test_published_item_keeps_its_live_version_until_publish(self):
        owner = self.as_user(self.owner)
        response = owner.patch("/api/v1/admin/menu/items/wow-toasted-burger", {"price": 6500, "isNew": True}, format="json")
        self.assertEqual(response.json()["state"], "draft")
        self.assertEqual(response.json()["draft"]["price"], 6500)
        self.assertEqual(self.api.get("/api/v1/menu/items/wow-toasted-burger").json()["price"], 6000)

        published = owner.post("/api/v1/admin/menu/items/wow-toasted-burger/publish").json()
        self.assertEqual((published["state"], published["price"], published["isNew"]), ("published", 6500, True))
        self.assertEqual(self.api.get("/api/v1/menu/items/wow-toasted-burger").json()["price"], 6500)

    def test_new_item_is_hidden_until_published(self):
        owner = self.as_user(self.owner)
        created = owner.post("/api/v1/admin/menu/items", {
            "name": {"en": "Passion Juice"}, "price": 2500, "group": "drinks", "section": "mojitos",
            "categories": ["drinks"], "tags": ["fresh"],
        }, format="json")
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.json()["name"], {"en": "Passion Juice", "fr": "Passion Juice"})  # copied without DeepL
        self.assertEqual(self.api.get("/api/v1/menu/items/passion-juice").status_code, 404)
        owner.post("/api/v1/admin/menu/items/passion-juice/publish")
        self.assertEqual(self.api.get("/api/v1/menu/items/passion-juice").status_code, 200)

    def test_grant_scopes(self):
        manager = self.as_user(self.eric)
        self.assertError(manager.patch("/api/v1/admin/menu/items/wow-toasted-burger", {"price": 1}, format="json"), 403, "forbidden")
        self.grant(self.eric, ["food"])
        manager = self.as_user(self.eric)
        self.assertEqual(manager.patch("/api/v1/admin/menu/items/wow-toasted-burger", {"price": 1}, format="json").status_code, 200)
        self.assertError(manager.patch("/api/v1/admin/menu/items/fresh-mint-mojito", {"price": 1}, format="json"), 403, "forbidden")
        self.assertError(manager.patch("/api/v1/admin/menu/items/wow-toasted-burger", {"isNew": True}, format="json"), 403, "forbidden")
        self.assertError(manager.post("/api/v1/admin/menu/items/wow-toasted-burger/publish"), 403, "forbidden")

    def test_labels_only_grant_changes_the_badge_only(self):
        self.grant(self.eric, ["labels"])
        manager = self.as_user(self.eric)
        self.assertEqual(manager.patch("/api/v1/admin/menu/items/wow-toasted-burger", {"isNew": True}, format="json").status_code, 200)
        self.assertError(manager.patch("/api/v1/admin/menu/items/wow-toasted-burger", {"price": 1}, format="json"), 403, "forbidden")

    def test_validation(self):
        response = self.as_user(self.owner).post("/api/v1/admin/menu/items", {
            "name": {"en": "X"}, "price": -1, "group": "food", "categories": ["nope"],
        }, format="json")
        self.assertError(response, 422, "validation_failed")
        self.assertIn("price", response.json()["error"]["details"])


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(), CLOUDINARY_URL="")
class UploadTests(ApiTestCase):
    def upload(self, content, name="photo.png", user=None):
        file = SimpleUploadedFile(name, content)
        return self.as_user(user or self.owner).post("/api/v1/admin/uploads", {"file": file}, format="multipart")

    def test_image_is_resized_and_usable_in_an_item(self):
        buffer = io.BytesIO()
        Image.new("RGB", (3000, 2000)).save(buffer, "PNG")
        response = self.upload(buffer.getvalue())
        self.assertEqual(response.status_code, 201, response.content)
        self.assertRegex(response.json()["url"], r"^http://testserver/media/uploads/\w+\.png$")
        self.assertEqual((Upload.objects.get().width, Upload.objects.get().height), (1600, 1067))

        item = self.as_user(self.owner).patch(
            "/api/v1/admin/menu/items/wow-toasted-burger", {"imageId": response.json()["imageId"]}, format="json"
        )
        self.assertEqual(item.json()["draft"]["image"], response.json()["url"])

    def test_rejects_other_files_and_clients(self):
        self.assertError(self.upload(b"not an image", "notes.txt"), 422, "validation_failed")
        self.assertError(self.upload(b"x", user=self.aline), 403, "forbidden")
