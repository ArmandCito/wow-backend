"""
python manage.py seed                    # catalogue, homepage promotions, business details
python manage.py seed --demo-accounts    # + the website's sample staff and clients (staging only)
python manage.py seed --if-empty         # only when the menu is empty (safe in the Render build command)

Data: core/seed/catalogue.json, exported from the website's mock data (data/*.ts), so the API serves
exactly the menu the website shows today. Safe to run again: existing rows are updated, never duplicated.
"""

import json
from datetime import timedelta
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import Assignment, ContentGrant, Duty, Role, Status, User
from business.models import BusinessSettings
from menu.models import Category, DrinkSection, MenuItem, OptionChoice, OptionGroup, Tag
from promotions.models import Campaign

DATA = Path(__file__).resolve().parents[2] / "seed" / "catalogue.json"

DEMO_STAFF = [
    # name, email, role, assignment, duty, status
    ("Rwasibo Alexis Junior", "owner@wowquickbites.rw", Role.SUPERADMIN, Assignment.NONE, Duty.ON, Status.ACTIVE),
    ("Eric", "eric@wowquickbites.rw", Role.MANAGER, Assignment.PICKUP_REGISTER, Duty.ON, Status.ACTIVE),
    ("Nadia", "nadia@wowquickbites.rw", Role.MANAGER, Assignment.PICKUP_REGISTER, Duty.ON, Status.ACTIVE),
    ("Kevin", "kevin@wowquickbites.rw", Role.MANAGER, Assignment.BACKUP, Duty.OFF, Status.ACTIVE),
    ("Chantal", "chantal@wowquickbites.rw", Role.MANAGER, Assignment.NONE, Duty.OFF, Status.SUSPENDED),
]
DEMO_CLIENTS = [
    ("Aline", "aline@example.com", "078 123 4567"),
    ("Patrick", "patrick@example.com", ""),
    ("Claude", "claude@example.com", ""),
    ("Diane", "diane@example.com", ""),
    ("Grace", "grace@example.com", ""),
    ("Jean", "jean@example.com", ""),
]


def texts(base, value):
    value = value or {}
    return {f"{base}_en": value.get("en", ""), f"{base}_fr": value.get("fr", "")}


class Command(BaseCommand):
    help = "Loads the website's catalogue, promotions and business details (and optionally demo accounts)."

    def add_arguments(self, parser):
        parser.add_argument("--demo-accounts", action="store_true", help="Create the sample staff and clients.")
        parser.add_argument("--if-empty", action="store_true", help="Do nothing when menu items already exist.")
        parser.add_argument("--staff-password", default="WowStaff#2026")
        parser.add_argument("--client-password", default="WowClient#2026")

    @transaction.atomic
    def handle(self, *args, **options):
        if options["if_empty"] and MenuItem.objects.exists():
            self.stdout.write("Menu already filled: seed skipped (edits made in the portal are kept).")
            return
        data = json.loads(DATA.read_text(encoding="utf-8"))
        self.seed_catalogue(data)
        self.seed_promotions(data)
        self.seed_business(data["business"])
        if options["demo_accounts"]:
            self.seed_accounts(options["staff_password"], options["client_password"])
        self.stdout.write(self.style.SUCCESS("Seed data loaded."))

    def seed_catalogue(self, data):
        for order, category in enumerate(data["categories"]):
            Category.objects.update_or_create(
                slug=category["id"],
                defaults={**texts("name", category["name"]), "icon": category["icon"], "display_order": order},
            )
        for order, section in enumerate(data["drinkSections"]):
            DrinkSection.objects.update_or_create(
                slug=section["id"],
                defaults={**texts("name", section["name"]), **texts("note", section.get("note")), "display_order": order},
            )
        for key, label in data["tags"].items():
            Tag.objects.update_or_create(key=key, defaults=texts("label", label))
        for order, group in enumerate(data["optionGroups"]):
            option_group, _ = OptionGroup.objects.update_or_create(
                slug=group["id"],
                defaults={
                    **texts("name", group["name"]), **texts("hint", group.get("hint")), "kind": group["kind"],
                    "required": group["required"], "max_choices": group.get("max"), "display_order": order,
                },
            )
            for position, choice in enumerate(group["choices"]):
                OptionChoice.objects.update_or_create(
                    slug=choice["id"],
                    defaults={**texts("name", choice["name"]), "group": option_group, "price": choice["price"],
                              "display_order": position},
                )

        for order, entry in enumerate(data["menuItems"]):
            item, _ = MenuItem.objects.update_or_create(
                slug=entry["id"],
                defaults={
                    **texts("name", entry["name"]), **texts("description", entry["description"]),
                    **texts("cart_meta", entry.get("cartMeta")), "price": entry["price"], "image": entry["image"],
                    "group": entry["group"], "section": DrinkSection.objects.filter(slug=entry.get("section")).first(),
                    "is_new": entry.get("isNew", False), "is_available": True, "is_published": True, "draft": None,
                    "deleted_at": None, "display_order": order,
                },
            )
            item.categories.set(Category.objects.filter(slug__in=entry["categories"]))
            item.tags.set(Tag.objects.filter(key__in=entry["tags"]))
            item.option_groups.set(OptionGroup.objects.filter(slug__in=entry.get("optionGroups", [])))
        for entry in data["menuItems"]:  # second pass: the paired item exists now
            MenuItem.objects.filter(slug=entry["id"]).update(
                pairs_with=MenuItem.objects.filter(slug=entry.get("pairsWith")).first()
            )
        self.stdout.write(f"  {len(data['menuItems'])} menu items, {len(data['categories'])} categories")

    def seed_promotions(self, data):
        """The homepage offers, published without dates (the website shows them all today)."""
        extra = {campaign["promotionId"]: campaign for campaign in data["campaigns"]}
        for order, promotion in enumerate(data["promotions"]):
            campaign = extra.get(promotion["id"], {})
            highlight = promotion.get("highlight") or {}
            Campaign.objects.update_or_create(
                slug=promotion["id"],
                defaults={
                    **texts("kicker", promotion["kicker"]), **texts("title", promotion["title"]),
                    **texts("text", promotion["text"]), **texts("cta", promotion["cta"]),
                    **texts("highlight_label", highlight.get("label")), **texts("highlight_value", highlight.get("value")),
                    **texts("schedule", campaign.get("schedule")),
                    "highlight_label_first": highlight.get("labelFirst", True),
                    "image": promotion["image"], "href": promotion["href"], "tone": promotion["tone"],
                    "tag": campaign.get("tag", Campaign.Tag.PROMOTION),
                    "placement": campaign.get("placement", Campaign.Placement.HOME_OFFERS),
                    "cta_category": Category.objects.filter(slug=campaign.get("ctaCategory")).first(),
                    "status": Campaign.Status.PUBLISHED, "starts_at": None, "ends_at": None, "display_order": order,
                },
            )
        self.stdout.write(f"  {len(data['promotions'])} homepage promotions")

    def seed_business(self, business):
        settings = BusinessSettings.load()
        for field, value in {
            **texts("name", business["name"]), **texts("location", business["location"]),
            **texts("hours", business["hours"]), "owner": business["owner"], "email": business["email"],
            "phone": business["phone"], "socials": business["socials"], "queue_window_days": business["queueWindowDays"],
        }.items():
            setattr(settings, field, value)
        settings.save()
        self.stdout.write("  business details")

    def seed_accounts(self, staff_password, client_password):
        for name, email, role, assignment, duty, status in DEMO_STAFF:
            user = User.objects.filter(email=email).first()
            if user is None:
                user = User.objects.create_staff(
                    email, name, role=role, password=staff_password, assignment=assignment, duty=duty, status=status,
                    is_staff=role == Role.SUPERADMIN, is_superuser=role == Role.SUPERADMIN,
                )
        owner = User.objects.get(email="owner@wowquickbites.rw")
        eric = User.objects.get(email="eric@wowquickbites.rw")
        if not eric.content_grants.current().exists():
            ContentGrant.objects.create(
                manager=eric, granted_by=owner, scopes=["food", "drinks", "labels", "ads", "publish"],
                starts_at=timezone.now(), expires_at=timezone.now() + timedelta(days=30),
            )
        for name, email, phone in DEMO_CLIENTS:
            if not User.objects.filter(email=email).exists():
                User.objects.create_user(email, client_password, name=name, phone=phone)
        self.stdout.write(
            f"  demo accounts: staff password {staff_password!r}, client password {client_password!r}"
        )
