from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    """
    Append-only trail of staff activity (contract §10 Audit): order transitions, content changes and
    access changes. `text` is a ready-to-display sentence in both languages; `type` + `data` keep the
    raw facts for filtering.
    """

    class Scope(models.TextChoices):
        ORDERS = "orders"
        CONTENT = "content"
        ACCESS = "access"

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    scope = models.CharField(max_length=10, choices=Scope.choices)
    type = models.CharField(max_length=40)
    target = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    data = models.JSONField(default=dict)
    text_en = models.CharField(max_length=300)
    text_fr = models.CharField(max_length=300)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-id"]
        indexes = [models.Index(fields=["scope", "-id"])]

    def __str__(self):
        return f"{self.created_at:%Y-%m-%d %H:%M} {self.type}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise PermissionError("Audit events cannot be changed.")
        super().save(*args, **kwargs)
