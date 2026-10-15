from django.contrib import admin

from .models import ClientNotification


@admin.register(ClientNotification)
class ClientNotificationAdmin(admin.ModelAdmin):
    list_display = ("created_at", "client", "order", "stage", "title_en", "read_at")
    list_filter = ("stage",)
    search_fields = ("client__email", "client__client_code")
