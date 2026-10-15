from rest_framework import serializers

from core.fields import LocalizedField
from core.phone import PhoneField

from .models import Fulfilment, Order, OrderLine, PaymentMethod, PaymentStatus, Stage

# ───────── Checkout input (contract §5) ─────────


class CartLineSerializer(serializers.Serializer):
    item_id = serializers.SlugField(max_length=80)
    quantity = serializers.IntegerField(min_value=1, max_value=99)
    choices = serializers.ListField(child=serializers.SlugField(), required=False, default=list, max_length=30)
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")


class ContactSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120, required=False)
    phone = PhoneField(required=False)
    email = serializers.EmailField(required=False, allow_blank=True)


class PlaceOrderSerializer(serializers.Serializer):
    lines = CartLineSerializer(many=True, min_length=1, max_length=50)
    fulfilment = serializers.ChoiceField(choices=Fulfilment.choices)
    address = serializers.CharField(max_length=300, required=False, allow_blank=True, allow_null=True, default="")
    payment = serializers.ChoiceField(choices=PaymentMethod.choices)
    contact = ContactSerializer(required=False, default=dict)
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True, allow_null=True, default="")

    def validate(self, attrs):
        attrs["address"] = (attrs.get("address") or "").strip()
        attrs["notes"] = (attrs.get("notes") or "").strip()
        if attrs["fulfilment"] == Fulfilment.DELIVERY and not attrs["address"]:
            raise serializers.ValidationError({"address": serializers.ErrorDetail("Delivery needs an address.", "required")})
        return attrs


class TransitionSerializer(serializers.Serializer):
    to = serializers.ChoiceField(choices=Stage.choices)


class PaymentUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=[PaymentStatus.PAID], help_text="Only `paid` for now (Mobile Money checked by staff).")


class AssignSerializer(serializers.Serializer):
    manager_id = serializers.SlugField(help_text="Staff id of the manager.")


# ───────── Output (contract §6 Order) ─────────


class OrderLineSerializer(serializers.ModelSerializer):
    item_id = serializers.CharField(source="item_slug")
    name = LocalizedField()
    options = serializers.JSONField(source="choice_details", help_text='[{"id", "name": {"en", "fr"}, "price"}]')
    note = serializers.SerializerMethodField()

    class Meta:
        model = OrderLine
        fields = ["item_id", "quantity", "choices", "options", "note", "name", "unit_price", "total"]

    def get_note(self, line) -> str | None:
        return line.note or None


class OrderContactSerializer(serializers.Serializer):
    name = serializers.CharField(source="contact_name")
    phone = serializers.CharField(source="contact_phone")


class OrderSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source="public_id")
    client_code = serializers.SerializerMethodField(help_text='"WQB001A", empty for guest orders.')
    contact = OrderContactSerializer(source="*")
    client_name = serializers.CharField(source="contact_name")
    manager_id = serializers.SerializerMethodField()
    manager_name = serializers.SerializerMethodField()
    address = serializers.SerializerMethodField()
    notes = serializers.SerializerMethodField()
    lines = OrderLineSerializer(many=True)

    class Meta:
        model = Order
        fields = [
            "id", "client_code", "guest", "contact", "client_name", "manager_id", "manager_name", "placed_at",
            "fulfilment", "address", "payment", "payment_status", "stage", "lines", "subtotal", "fees", "total",
            "history", "notes",
        ]

    def get_client_code(self, order) -> str:
        return order.client.client_code if order.client else ""

    def get_manager_id(self, order) -> str | None:
        return order.manager.staff_id if order.manager else None

    def get_manager_name(self, order) -> str | None:
        return order.manager.name if order.manager else None

    def get_address(self, order) -> str | None:
        return order.address or None

    def get_notes(self, order) -> str | None:
        return order.notes or None


class StaffOrderSerializer(OrderSerializer):
    """Staff also see how to reach the customer."""

    contact_email = serializers.SerializerMethodField()

    class Meta(OrderSerializer.Meta):
        fields = OrderSerializer.Meta.fields + ["contact_email"]

    def get_contact_email(self, order) -> str | None:
        return order.contact_email or (order.client.email if order.client else None)


class OrderEnvelopeSerializer(serializers.Serializer):
    order = OrderSerializer()


class StaffOrderEnvelopeSerializer(serializers.Serializer):
    order = StaffOrderSerializer()


class OverviewSerializer(serializers.Serializer):
    orders = serializers.IntegerField(help_text="Orders in the register window (today and the previous days).")
    orders_today = serializers.IntegerField()
    active = serializers.DictField(child=serializers.IntegerField(), help_text="Count per stage, in the window.")
    active_orders = serializers.IntegerField()
    pending_payments = serializers.IntegerField()
    completed_value = serializers.IntegerField(help_text="RWF of completed orders in the window.")
    completed_count = serializers.IntegerField()
    managers = serializers.DictField(child=serializers.IntegerField())
