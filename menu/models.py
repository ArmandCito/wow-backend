"""
The catalogue (contract §4). Every public id is a readable slug ("wow-toasted-burger", "burgers",
"extra-cheese"), the same ids the website uses in its URLs and its cart.

Prices are integers in RWF. Texts exist in English and French (`*_en` / `*_fr` columns).
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class Ordered(models.Model):
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        abstract = True
        ordering = ["display_order", "id"]


class Category(Ordered):
    slug = models.SlugField(unique=True)
    name_en = models.CharField(max_length=80)
    name_fr = models.CharField(max_length=80)
    icon = models.CharField(max_length=40, blank=True, help_text="Icon name used by the website.")
    is_active = models.BooleanField(default=True)

    class Meta(Ordered.Meta):
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name_en


class DrinkSection(Ordered):
    slug = models.SlugField(unique=True)
    name_en = models.CharField(max_length=80)
    name_fr = models.CharField(max_length=80)
    note_en = models.CharField(max_length=120, blank=True)
    note_fr = models.CharField(max_length=120, blank=True)

    def __str__(self):
        return self.name_en


class Tag(models.Model):
    key = models.SlugField(unique=True)
    label_en = models.CharField(max_length=40)
    label_fr = models.CharField(max_length=40)

    class Meta:
        ordering = ["key"]

    def __str__(self):
        return self.key


class OptionGroup(Ordered):
    """Customisation of a dish: paid extras ("add") or ingredients to leave out ("remove")."""

    class Kind(models.TextChoices):
        ADD = "add"
        REMOVE = "remove"

    slug = models.SlugField(unique=True)
    name_en = models.CharField(max_length=80)
    name_fr = models.CharField(max_length=80)
    hint_en = models.CharField(max_length=160, blank=True)
    hint_fr = models.CharField(max_length=160, blank=True)
    kind = models.CharField(max_length=6, choices=Kind.choices, default=Kind.ADD)
    required = models.BooleanField(default=False, help_text="At least one choice must be picked.")
    max_choices = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Empty = no limit.")

    def __str__(self):
        return self.name_en


class OptionChoice(Ordered):
    group = models.ForeignKey(OptionGroup, on_delete=models.CASCADE, related_name="choices")
    slug = models.SlugField(unique=True, help_text="Unique across all groups: the cart stores choice ids.")
    name_en = models.CharField(max_length=80)
    name_fr = models.CharField(max_length=80)
    price = models.PositiveIntegerField(default=0, help_text="Extra cost in RWF, 0 when included.")
    is_available = models.BooleanField(default=True)

    def __str__(self):
        return self.name_en


class MenuItemQuerySet(models.QuerySet):
    def alive(self):
        return self.filter(deleted_at__isnull=True)

    def public(self):
        """What the website shows: published and not deleted (unavailable items are shown greyed)."""
        return self.alive().filter(is_published=True)

    def with_relations(self):
        return self.select_related("section", "pairs_with").prefetch_related(
            "categories", "tags", "option_groups"
        )


class MenuItem(Ordered):
    """
    A dish or a drink.

    Editing workflow (contract §9): a new item is a draft until published. Changes to a published
    item are kept in `draft` (same shape as the API input) and only reach the website when
    published, so photo, price, availability and badge change together.
    """

    class Group(models.TextChoices):
        FOOD = "food"
        DRINKS = "drinks"

    slug = models.SlugField(max_length=80, unique=True)
    name_en = models.CharField(max_length=120)
    name_fr = models.CharField(max_length=120)
    description_en = models.TextField(blank=True)
    description_fr = models.TextField(blank=True)
    cart_meta_en = models.CharField(max_length=120, blank=True)
    cart_meta_fr = models.CharField(max_length=120, blank=True)
    price = models.PositiveIntegerField(help_text="RWF")
    image = models.CharField(max_length=500, blank=True, help_text="Absolute URL, or a path served by the website.")
    group = models.CharField(max_length=6, choices=Group.choices, default=Group.FOOD)
    section = models.ForeignKey(DrinkSection, null=True, blank=True, on_delete=models.SET_NULL, related_name="items")
    categories = models.ManyToManyField(Category, blank=True, related_name="items")
    tags = models.ManyToManyField(Tag, blank=True, related_name="items")
    option_groups = models.ManyToManyField(OptionGroup, blank=True, related_name="items")
    pairs_with = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    is_new = models.BooleanField(default=False)
    is_available = models.BooleanField(default=True, help_text="False = shown greyed, cannot be ordered.")

    is_published = models.BooleanField(default=False)
    draft = models.JSONField(null=True, blank=True, help_text="Unpublished changes of a published item.")
    deleted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    objects = MenuItemQuerySet.as_manager()

    class Meta(Ordered.Meta):
        indexes = [models.Index(fields=["is_published", "deleted_at", "group"])]

    def __str__(self):
        return self.name_en

    @property
    def state(self):
        return "published" if self.is_published and not self.draft else "draft"

    def soft_delete(self):
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at", "updated_at"])
