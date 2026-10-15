"""
Homepage campaigns (contract §9 Campaigns). A published campaign inside its date window is a
promotion of the homepage (GET /promotions, contract §4).
"""

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class CampaignQuerySet(models.QuerySet):
    def live(self):
        """Shown on the website right now."""
        now = timezone.now()
        return self.filter(
            Q(status=Campaign.Status.PUBLISHED) | Q(status=Campaign.Status.SCHEDULED, starts_at__lte=now),
            Q(starts_at__isnull=True) | Q(starts_at__lte=now),
            Q(ends_at__isnull=True) | Q(ends_at__gt=now),
        )


class Campaign(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft"
        SCHEDULED = "scheduled"
        PUBLISHED = "published"
        PAUSED = "paused"

    class Tag(models.TextChoices):
        PROMOTION = "promotion"
        NEW = "new"
        OFFER = "offer"

    class Placement(models.TextChoices):
        HOME_OFFERS = "home-offers"
        HOME_HERO = "home-hero"

    class Tone(models.TextChoices):
        YELLOW = "yellow"
        PLAIN = "plain"

    slug = models.SlugField(max_length=80, unique=True)
    status = models.CharField(max_length=9, choices=Status.choices, default=Status.DRAFT)
    tag = models.CharField(max_length=9, choices=Tag.choices, default=Tag.PROMOTION)
    placement = models.CharField(max_length=11, choices=Placement.choices, default=Placement.HOME_OFFERS)
    tone = models.CharField(max_length=6, choices=Tone.choices, default=Tone.PLAIN)

    kicker_en = models.CharField(max_length=60, blank=True)
    kicker_fr = models.CharField(max_length=60, blank=True)
    title_en = models.CharField(max_length=120)
    title_fr = models.CharField(max_length=120)
    text_en = models.CharField(max_length=300, blank=True)
    text_fr = models.CharField(max_length=300, blank=True)
    cta_en = models.CharField(max_length=40, blank=True)
    cta_fr = models.CharField(max_length=40, blank=True)
    # Big block "SAVE RWF / 1,000" (label first) or "FREE / DELIVERY"; empty label = no block
    highlight_label_en = models.CharField(max_length=40, blank=True)
    highlight_label_fr = models.CharField(max_length=40, blank=True)
    highlight_value_en = models.CharField(max_length=40, blank=True)
    highlight_value_fr = models.CharField(max_length=40, blank=True)
    highlight_label_first = models.BooleanField(default=True)
    schedule_en = models.CharField(max_length=60, blank=True, help_text='Short line under the card, e.g. "Weekdays".')
    schedule_fr = models.CharField(max_length=60, blank=True)

    image = models.CharField(max_length=500, blank=True)
    image_id = models.CharField(max_length=36, blank=True)
    cta_category = models.ForeignKey("menu.Category", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    href = models.CharField(max_length=300, blank=True, help_text="Link of the button. Empty = the menu (or its category).")

    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    display_order = models.PositiveIntegerField(default=0)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CampaignQuerySet.as_manager()

    class Meta:
        ordering = ["display_order", "-created_at"]

    def __str__(self):
        return self.title_en

    @property
    def effective_status(self):
        """A scheduled campaign whose start has passed reads as published."""
        if self.status == self.Status.SCHEDULED and self.starts_at and self.starts_at <= timezone.now():
            return self.Status.PUBLISHED
        return self.status

    @property
    def link(self):
        if self.href:
            return self.href
        return f"/menu?category={self.cta_category.slug}" if self.cta_category else "/menu"
