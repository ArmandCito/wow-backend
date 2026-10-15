from rest_framework import serializers

from core.fields import LocalizedField

from .models import AuditEvent


class AuditEventSerializer(serializers.ModelSerializer):
    id = serializers.CharField()
    at = serializers.DateTimeField(source="created_at")
    actor_id = serializers.SerializerMethodField(help_text='Staff id, or "system".')
    target_id = serializers.SerializerMethodField()
    text = LocalizedField()

    class Meta:
        model = AuditEvent
        fields = ["id", "at", "actor_id", "scope", "target_id", "type", "data", "text"]

    def get_actor_id(self, event) -> str:
        return event.actor.public_id if event.actor else "system"

    def get_target_id(self, event) -> str | None:
        return event.target.public_id if event.target else None


class AuditPageSerializer(serializers.Serializer):
    items = AuditEventSerializer(many=True)
    next_cursor = serializers.CharField(allow_null=True)
