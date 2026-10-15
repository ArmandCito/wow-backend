from rest_framework import serializers

from core.fields import LocalizedField
from core.models import Upload

from .models import Category, DrinkSection, MenuItem, OptionChoice, OptionGroup, Tag

# ───────── Public catalogue (contract §4) ─────────


class CategorySerializer(serializers.ModelSerializer):
    id = serializers.CharField(source="slug")
    name = LocalizedField()

    class Meta:
        model = Category
        fields = ["id", "name", "icon"]


class DrinkSectionSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source="slug")
    name = LocalizedField()
    note = LocalizedField(optional=True)

    class Meta:
        model = DrinkSection
        fields = ["id", "name", "note"]


class OptionChoiceSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source="slug")
    name = LocalizedField()

    class Meta:
        model = OptionChoice
        fields = ["id", "name", "price"]


class OptionGroupSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source="slug")
    name = LocalizedField()
    hint = LocalizedField(optional=True)
    max = serializers.IntegerField(source="max_choices", allow_null=True)
    choices = serializers.SerializerMethodField()

    class Meta:
        model = OptionGroup
        fields = ["id", "name", "hint", "kind", "required", "max", "choices"]

    def get_choices(self, group) -> list[dict]:
        # Only what can be ordered (prefetched in views as `available_choices`)
        choices = getattr(group, "available_choices", None)
        if choices is None:
            choices = group.choices.filter(is_available=True)
        return OptionChoiceSerializer(choices, many=True).data


class MenuItemSerializer(serializers.ModelSerializer):
    """A dish or drink as the website shows it (type MenuItem)."""

    id = serializers.CharField(source="slug")
    name = LocalizedField()
    description = LocalizedField()
    cart_meta = LocalizedField(optional=True)
    section = serializers.SlugRelatedField(slug_field="slug", read_only=True)
    categories = serializers.SlugRelatedField(slug_field="slug", many=True, read_only=True)
    tags = serializers.SlugRelatedField(slug_field="key", many=True, read_only=True)
    option_groups = serializers.SlugRelatedField(slug_field="slug", many=True, read_only=True)
    pairs_with = serializers.SlugRelatedField(slug_field="slug", read_only=True)
    available = serializers.BooleanField(source="is_available")

    class Meta:
        model = MenuItem
        fields = [
            "id", "name", "description", "cart_meta", "price", "image", "group", "section", "categories",
            "tags", "is_new", "available", "option_groups", "pairs_with",
        ]


# ───────── Portal: editing (contract §9) ─────────

LIST_FIELDS = {"categories": Category, "tags": Tag, "option_groups": OptionGroup}
LOOKUP = {Category: "slug", Tag: "key", OptionGroup: "slug", DrinkSection: "slug", MenuItem: "slug"}


def missing_ids(model, ids):
    found = set(model.objects.filter(**{f"{LOOKUP[model]}__in": ids}).values_list(LOOKUP[model], flat=True))
    return [value for value in ids if value not in found]


class MenuItemInputSerializer(serializers.Serializer):
    """
    MenuItemInput. Validated data is stored as is in `MenuItem.draft` (plain JSON: column names,
    related objects by id), then applied by menu.services.apply_changes().
    """

    id = serializers.SlugField(source="slug", max_length=80, required=False,
                               help_text="URL slug, created from the English name when omitted (create only).")
    name = LocalizedField(max_length=120)
    description = LocalizedField(optional=True)
    cart_meta = LocalizedField(optional=True, max_length=120)
    price = serializers.IntegerField(min_value=0, max_value=10_000_000)
    group = serializers.ChoiceField(choices=MenuItem.Group.choices)
    section = serializers.SlugField(allow_null=True, required=False)
    categories = serializers.ListField(child=serializers.SlugField(), required=False)
    tags = serializers.ListField(child=serializers.SlugField(), required=False)
    option_groups = serializers.ListField(child=serializers.SlugField(), required=False)
    pairs_with = serializers.SlugField(allow_null=True, required=False)
    is_new = serializers.BooleanField(required=False)
    available = serializers.BooleanField(source="is_available", required=False)
    image = serializers.CharField(max_length=500, allow_blank=True, required=False,
                                  help_text="Image URL. Prefer imageId after POST /admin/uploads.")
    image_id = serializers.UUIDField(required=False, write_only=True)

    def validate_id(self, slug):
        if self.instance is not None:
            raise serializers.ValidationError("The id of an item cannot change.", code="read_only")
        if MenuItem.objects.filter(slug=slug).exists():
            raise serializers.ValidationError("This id is already used.", code="unique")
        return slug

    def validate_section(self, slug):
        if slug and missing_ids(DrinkSection, [slug]):
            raise serializers.ValidationError("Unknown drink section.", code="does_not_exist")
        return slug

    def validate_pairs_with(self, slug):
        if slug and missing_ids(MenuItem, [slug]):
            raise serializers.ValidationError("Unknown menu item.", code="does_not_exist")
        if slug and self.instance is not None and slug == self.instance.slug:
            raise serializers.ValidationError("An item cannot be paired with itself.", code="invalid")
        return slug

    def validate(self, attrs):
        for field, model in LIST_FIELDS.items():
            if field in attrs:
                attrs[field] = list(dict.fromkeys(attrs[field]))  # unique, order kept
                if missing_ids(model, attrs[field]):
                    raise serializers.ValidationError(
                        {field: serializers.ErrorDetail(f"Unknown ids: {missing_ids(model, attrs[field])}", "does_not_exist")}
                    )

        if "image_id" in attrs:
            upload = Upload.objects.filter(pk=attrs.pop("image_id")).first()
            if upload is None:
                raise serializers.ValidationError({"image_id": serializers.ErrorDetail("Unknown upload.", "does_not_exist")})
            attrs["image"] = upload.url

        group = attrs.get("group", getattr(self.instance, "group", None))
        if group == MenuItem.Group.FOOD and ("group" in attrs or attrs.get("section")):
            attrs["section"] = None  # drink sections only apply to drinks
        return attrs


class AdminMenuItemSerializer(MenuItemSerializer):
    """An item in the portal: the live values, its state and the pending changes."""

    state = serializers.CharField(read_only=True)
    draft = serializers.SerializerMethodField()
    updated_at = serializers.DateTimeField(read_only=True)
    deleted = serializers.SerializerMethodField()

    class Meta(MenuItemSerializer.Meta):
        fields = MenuItemSerializer.Meta.fields + ["state", "draft", "updated_at", "deleted"]

    def get_draft(self, item) -> dict | None:
        from .services import draft_as_input

        return draft_as_input(item)

    def get_deleted(self, item) -> bool:
        return item.deleted_at is not None
