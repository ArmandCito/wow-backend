"""
Orders (contract §5–6). Names and prices are copied into the order lines when the order is placed,
so past orders never change when the menu changes.
"""

import re

from django.conf import settings
from django.db import models
from django.utils import timezone

ORDER_NUMBER_OFFSET = 1000  # first order is ORD-1001


class Stage(models.TextChoices):
    NEW = "new"
    ACCEPTED = "accepted"
    PREPARING = "preparing"
    READY = "ready"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


ACTIVE_STAGES = [Stage.NEW, Stage.ACCEPTED, Stage.PREPARING, Stage.READY]

# The register's only allowed moves (anything else is 409 invalid_transition)
TRANSITIONS = {
    Stage.NEW: {Stage.ACCEPTED, Stage.CANCELLED},
    Stage.ACCEPTED: {Stage.PREPARING, Stage.CANCELLED},
    Stage.PREPARING: {Stage.READY},
    Stage.READY: {Stage.COMPLETED},
}


class Fulfilment(models.TextChoices):
    PICKUP = "pickup"
    DELIVERY = "delivery"


class PaymentMethod(models.TextChoices):
    PAY_ON_PICKUP = "pay-on-pickup"
    MTN_MOMO = "mtn-momo"
    AIRTEL_MONEY = "airtel-money"


class PaymentStatus(models.TextChoices):
    PENDING = "pending"
    PAID = "paid"
    NOT_CHARGED = "not-charged"


class OrderQuerySet(models.QuerySet):
    def with_lines(self):
        return self.select_related("client", "manager").prefetch_related("lines")

    def by_public_id(self, public_id):
        """"ORD-1042" -> the order (empty queryset for a malformed id)."""
        match = re.fullmatch(r"ORD-(\d+)", (public_id or "").upper())
        if not match:
            return self.none()
        return self.filter(pk=int(match.group(1)) - ORDER_NUMBER_OFFSET)


class Order(models.Model):
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="orders"
    )
    guest = models.BooleanField(default=False, help_text="Placed without an account (name and phone only).")
    contact_name = models.CharField(max_length=120)
    contact_phone = models.CharField(max_length=20)
    contact_email = models.EmailField(blank=True)

    manager = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_orders"
    )
    fulfilment = models.CharField(max_length=8, choices=Fulfilment.choices)
    address = models.CharField(max_length=300, blank=True)
    payment = models.CharField(max_length=13, choices=PaymentMethod.choices)
    payment_status = models.CharField(max_length=11, choices=PaymentStatus.choices, default=PaymentStatus.PENDING)
    stage = models.CharField(max_length=9, choices=Stage.choices, default=Stage.NEW)
    notes = models.CharField(max_length=500, blank=True)

    subtotal = models.PositiveIntegerField()
    fees = models.PositiveIntegerField(default=0)
    total = models.PositiveIntegerField()

    history = models.JSONField(default=dict, help_text='When each stage was reached: {"new": "2026-10-06T12:18:00+02:00"}')
    placed_at = models.DateTimeField(default=timezone.now, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = OrderQuerySet.as_manager()

    class Meta:
        ordering = ["-placed_at", "-id"]
        indexes = [models.Index(fields=["stage", "-placed_at"]), models.Index(fields=["manager", "stage"])]

    def __str__(self):
        return self.public_id

    @property
    def public_id(self):
        return f"ORD-{self.pk + ORDER_NUMBER_OFFSET}" if self.pk else ""

    @property
    def is_active(self):
        return self.stage in ACTIVE_STAGES


class OrderLine(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey("menu.MenuItem", null=True, on_delete=models.SET_NULL, related_name="+")
    item_slug = models.SlugField(max_length=80)
    name_en = models.CharField(max_length=120)
    name_fr = models.CharField(max_length=120)
    quantity = models.PositiveSmallIntegerField()
    choices = models.JSONField(default=list, help_text="Option choice ids")
    choice_details = models.JSONField(default=list, help_text='[{"id", "name": {"en", "fr"}, "price"}] at order time')
    note = models.CharField(max_length=200, blank=True)
    unit_price = models.PositiveIntegerField(help_text="Item price + choices, at order time (RWF)")
    total = models.PositiveIntegerField()

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.quantity} × {self.name_en}"
