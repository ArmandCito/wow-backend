from django.contrib import admin

from .models import Category, DrinkSection, MenuItem, OptionChoice, OptionGroup, Tag

# The superadmin manages categories, sections, tags and option groups here (/admin/).
# Menu items are edited from the website portal (drafts and publication).


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("slug", "name_en", "name_fr", "icon", "display_order", "is_active")
    list_editable = ("display_order", "is_active")
    prepopulated_fields = {"slug": ("name_en",)}


@admin.register(DrinkSection)
class DrinkSectionAdmin(admin.ModelAdmin):
    list_display = ("slug", "name_en", "name_fr", "display_order")
    list_editable = ("display_order",)
    prepopulated_fields = {"slug": ("name_en",)}


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("key", "label_en", "label_fr")


class OptionChoiceInline(admin.TabularInline):
    model = OptionChoice
    extra = 1
    prepopulated_fields = {"slug": ("name_en",)}


@admin.register(OptionGroup)
class OptionGroupAdmin(admin.ModelAdmin):
    list_display = ("slug", "name_en", "kind", "required", "max_choices", "display_order")
    prepopulated_fields = {"slug": ("name_en",)}
    inlines = [OptionChoiceInline]


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ("slug", "name_en", "group", "price", "is_available", "is_published", "is_new", "deleted_at")
    list_filter = ("group", "is_published", "is_available", "is_new", "categories")
    search_fields = ("slug", "name_en", "name_fr")
    filter_horizontal = ("categories", "tags", "option_groups")
    readonly_fields = ("draft", "created_at", "updated_at", "updated_by")
