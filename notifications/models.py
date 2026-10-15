from django.conf import settings
from django.db import models


class ClientNotification(models.Model):
    """An order update in the client area (contract §8). Created by the server at each stage change."""

    client = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    order = models.ForeignKey("orders.Order", on_delete=models.CASCADE, related_name="notifications")
    stage = models.CharField(max_length=9)
    title_en = models.CharField(max_length=160)
    title_fr = models.CharField(max_length=160)
    text_en = models.CharField(max_length=400)
    text_fr = models.CharField(max_length=400)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["client", "read_at"])]

    def __str__(self):
        return f"{self.client} {self.title_en}"
