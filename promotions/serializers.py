from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from core.fields import LOCALIZED_SCHEMA, LocalizedField, localized
from core.models import Upload
from menu.models import Category

from .models import Campaign

HIGHLIGHT_SCHEMA = {
    "type": "object",
    "nullable": True,
    "properties": {"label": LOCALIZED_SCHEMA, "value": LOCALIZED_SCHEMA, "labelFirst": {"type": "boolean"}},
}


@extend_schema_field(HIGHLIGHT_SCHEMA)
class HighlightField(serializers.Field):
    """{"label": {en, fr}, "value": {en, fr}, "labelFirst": bool} or null."""

    default_error_messages = {"invalid": "Expected {label, value, labelFirst} or null."}

    def __init__(self, **kwargs):
        kwargs.update(source="*", required=False, allow_null=True)
        super().__init__(**kwargs)

    def to_representation(self, campaign):
        if not (campaign.highlight_label_en or campaign.highlight_value_en):
            return None
        return {
            "label": localized(campaign, "highlight_label"),
            "value": localized(campaign, "highlight_value"),
            "label_first": campaign.highlight_label_first,
        }

    def validate_empty_values(self, data):
        if data is None:
            return True, {f"highlight_{part}_{lang}": "" for part in ("label", "value") for lang in ("en", "fr")}
        return super().validate_empty_values(data)

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            self.fail("invalid")
        columns = {}
        for part in ("label", "value"):
            texts = data.get(part)
            if not isinstance(texts, dict):
                self.fail("invalid")
            en, fr = (str(texts.get("en") or "").strip(), str(texts.get("fr") or "").strip())
            if not (en or fr):
                self.fail("invalid")
            columns[f"highlight_{part}_en"] = (en or fr)[:40]
            columns[f"highlight_{part}_fr"] = (fr or en)[:40]
        columns["highlight_label_first"] = bool(data.get("label_first", True))
        return columns


class PromotionSerializer(serializers.ModelSerializer):
    """A campaign as the homepage shows it (type Promotion)."""

    id = serializers.CharField(source="slug")
    kicker = LocalizedField()
    title = LocalizedField()
    text = LocalizedField()
    cta = LocalizedField()
    highlight = HighlightField()
    href = serializers.CharField(source="link")
    cta_category = serializers.SlugRelatedField(slug_field="slug", read_only=True)
    schedule = LocalizedField(optional=True)

    class Meta:
        model = Campaign
        fields = ["id", "kicker", "highlight", "title", "text", "cta", "image", "href", "tone", "tag", "placement",
                  "cta_category", "schedule"]


class CampaignSerializer(serializers.ModelSerializer):
    """A campaign in the portal (type Campaign), also used to create and edit it."""

    id = serializers.SlugField(source="slug", max_length=80, required=False)
    status = serializers.CharField(source="effective_status", read_only=True)
    kicker = LocalizedField(optional=True, max_length=60)
    title = LocalizedField(max_length=120)
    text = LocalizedField(optional=True, max_length=300)
    cta = LocalizedField(optional=True, max_length=40)
    highlight = HighlightField()
    schedule = LocalizedField(optional=True, max_length=60)
    cta_category = serializers.SlugRelatedField(
        slug_field="slug", queryset=Category.objects.all(), allow_null=True, required=False
    )
    image_id = serializers.CharField(required=False, allow_blank=True)
    href = serializers.CharField(max_length=300, required=False, allow_blank=True)
    link = serializers.CharField(read_only=True, help_text="Where the button leads (href, or the menu category).")

    class Meta:
        model = Campaign
        fields = [
            "id", "status", "tag", "placement", "tone", "kicker", "title", "text", "cta", "highlight", "schedule",
            "cta_category", "image", "image_id", "href", "link", "starts_at", "ends_at", "display_order", "updated_at",
        ]
        read_only_fields = ["updated_at"]
        extra_kwargs = {"image": {"required": False}}

    def validate_id(self, slug):
        if self.instance is not None and slug != self.instance.slug:
            raise serializers.ValidationError("The id of a campaign cannot change.", code="read_only")
        if self.instance is None and Campaign.objects.filter(slug=slug).exists():
            raise serializers.ValidationError("This id is already used.", code="unique")
        return slug

    def validate(self, attrs):
        if attrs.get("image_id"):
            upload = Upload.objects.filter(pk=attrs["image_id"]).first() if _is_uuid(attrs["image_id"]) else None
            if upload is None:
                raise serializers.ValidationError({"image_id": serializers.ErrorDetail("Unknown upload.", "does_not_exist")})
            attrs["image"] = upload.url
        starts = attrs.get("starts_at", getattr(self.instance, "starts_at", None))
        ends = attrs.get("ends_at", getattr(self.instance, "ends_at", None))
        if starts and ends and ends <= starts:
            raise serializers.ValidationError({"ends_at": serializers.ErrorDetail("The end must be after the start.", "invalid")})
        return attrs

    def create(self, validated_data):
        from .services import unique_slug

        validated_data.setdefault("slug", unique_slug(validated_data["title_en"]))
        return Campaign.objects.create(**validated_data)

    def update(self, instance, validated_data):
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save()
        return instance


def _is_uuid(value):
    import uuid

    try:
        uuid.UUID(str(value))
    except ValueError:
        return False
    return True
