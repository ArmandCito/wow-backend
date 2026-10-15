from django.contrib import admin

from .models import Order, OrderLine


class OrderLineInline(admin.TabularInline):
    model = OrderLine
    extra = 0
    can_delete = False
    readonly_fields = ("item_slug", "name_en", "quantity", "choices", "note", "unit_price", "total")
    exclude = ("item", "name_fr", "choice_details")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("public_id", "placed_at", "contact_name", "client", "stage", "payment_status", "total", "manager")
    list_filter = ("stage", "payment_status", "fulfilment", "guest")
    search_fields = ("contact_name", "contact_phone", "client__client_code")
    readonly_fields = ("subtotal", "fees", "total", "history", "placed_at")
    inlines = [OrderLineInline]
