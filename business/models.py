from django.db import models


class BusinessSettings(models.Model):
    """The restaurant's details and checkout rules. A single row (id 1): `BusinessSettings.load()`."""

    name_en = models.CharField(max_length=120, default="WOW Quick Bites")
    name_fr = models.CharField(max_length=120, default="WOW Quick Bites")
    owner = models.CharField(max_length=120, blank=True)
    location_en = models.CharField(max_length=200, blank=True)
    location_fr = models.CharField(max_length=200, blank=True)
    hours_en = models.CharField(max_length=200, blank=True)
    hours_fr = models.CharField(max_length=200, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    socials = models.JSONField(default=list, blank=True, help_text='[{"label": "Instagram", "href": "https://…"}]')

    # Checkout and register rules
    service_fee = models.PositiveIntegerField(default=0, help_text="RWF added to every order.")
    delivery_fee = models.PositiveIntegerField(default=0, help_text="RWF added to delivery orders.")
    queue_window_days = models.PositiveSmallIntegerField(default=3, help_text="Days shown in the register queue.")

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = verbose_name_plural = "business settings"

    def __str__(self):
        return self.name_en

    @classmethod
    def load(cls):
        settings, _ = cls.objects.get_or_create(pk=1)
        return settings

    def fees_for(self, fulfilment):
        return self.service_fee + (self.delivery_fee if fulfilment == "delivery" else 0)
