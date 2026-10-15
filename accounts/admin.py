from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .forms import UserChangeForm, UserCreationForm
from .models import ContentGrant, PendingSignup, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    ordering = ("email",)
    list_display = ("email", "name", "role", "public_id", "status", "assignment", "duty")
    list_filter = ("role", "status", "assignment", "duty")
    search_fields = ("email", "name", "client_code", "staff_id", "phone")
    readonly_fields = ("client_code", "staff_id", "date_joined", "last_login")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("name", "phone", "role", "status", "client_code", "staff_id")}),
        ("Register", {"fields": ("assignment", "duty")}),
        ("Django admin", {"fields": ("is_staff", "is_superuser")}),
        ("Dates", {"fields": ("date_joined", "last_login")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "name", "role", "password1", "password2")}),
    )
    filter_horizontal = ()

    def save_model(self, request, obj, form, change):
        if change:
            super().save_model(request, obj, form, change)
        else:
            obj.save_with_public_id()


@admin.register(ContentGrant)
class ContentGrantAdmin(admin.ModelAdmin):
    list_display = ("manager", "scopes", "starts_at", "expires_at", "revoked_at", "granted_by")
    list_filter = ("revoked_at",)


@admin.register(PendingSignup)
class PendingSignupAdmin(admin.ModelAdmin):
    list_display = ("email", "name", "sent_at", "expires_at", "attempts")
    exclude = ("password", "code_hash")
