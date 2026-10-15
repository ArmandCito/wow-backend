from django.contrib import admin

from .models import Campaign


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("slug", "title_en", "status", "placement", "starts_at", "ends_at", "display_order")
    list_filter = ("status", "placement", "tag")
    search_fields = ("slug", "title_en", "title_fr")
