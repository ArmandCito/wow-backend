from rest_framework import serializers

from core.fields import LocalizedField

from .models import ClientNotification


class ClientNotificationSerializer(serializers.ModelSerializer):
    id = serializers.CharField()
    client_code = serializers.CharField(source="client.client_code")
    order_id = serializers.CharField(source="order.public_id")
    title = LocalizedField()
    text = LocalizedField()
    at = serializers.DateTimeField(source="created_at")
    read = serializers.SerializerMethodField()

    class Meta:
        model = ClientNotification
        fields = ["id", "client_code", "order_id", "stage", "title", "text", "at", "read"]

    def get_read(self, notification) -> bool:
        return notification.read_at is not None


class MarkReadSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.CharField(), required=False)
    all = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        if not attrs.get("all") and not attrs.get("ids"):
            raise serializers.ValidationError("Send `ids` or `all: true`.", code="required")
        return attrs
