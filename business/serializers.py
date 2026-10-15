from rest_framework import serializers

from core.fields import LocalizedField

from .models import BusinessSettings


class SocialLinkSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=40)
    href = serializers.CharField(max_length=300)


class FeesSerializer(serializers.Serializer):
    service = serializers.IntegerField(source="service_fee", min_value=0)
    delivery = serializers.IntegerField(source="delivery_fee", min_value=0)


class BusinessSerializer(serializers.ModelSerializer):
    """GET /business (public) and PUT/PATCH /admin/business."""

    name = LocalizedField(max_length=120)
    location = LocalizedField(max_length=200, optional=True)
    hours = LocalizedField(max_length=200, optional=True)
    socials = SocialLinkSerializer(many=True, required=False)
    fees = FeesSerializer(source="*", required=False)

    class Meta:
        model = BusinessSettings
        fields = ["name", "owner", "location", "hours", "email", "phone", "socials", "fees", "queue_window_days"]

    def update(self, instance, validated_data):
        # Bilingual fields and fees arrive already flattened to model columns
        if "socials" in validated_data:
            validated_data["socials"] = [dict(link) for link in validated_data["socials"]]
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        return instance
