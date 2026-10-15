from rest_framework import serializers

from accounts.models import Assignment, Duty, User
from accounts.serializers import ContentGrantSerializer, EmailField, lang_field


class StaffMemberSerializer(serializers.ModelSerializer):
    """A manager in the directory (contract §10 StaffMember)."""

    id = serializers.CharField(source="staff_id")
    content_grant = serializers.SerializerMethodField()
    active_orders = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = User
        fields = ["id", "name", "email", "role", "assignment", "duty", "status", "content_grant", "active_orders"]

    def get_content_grant(self, user) -> dict | None:
        """The grant in force or starting later (not revoked, not expired)."""
        grants = getattr(user, "current_grants", None)
        grant = grants[0] if grants else (None if grants is not None else user.content_grants.current().first())
        return ContentGrantSerializer(grant).data if grant else None


class ManagerUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120, required=False)
    duty = serializers.ChoiceField(choices=Duty.choices, required=False)
    assignment = serializers.ChoiceField(choices=Assignment.choices, required=False)


class InvitationSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    email = EmailField()
    assignment = serializers.ChoiceField(choices=Assignment.choices, default=Assignment.NONE)
    lang = lang_field()
