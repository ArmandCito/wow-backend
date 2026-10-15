from core.routing import route

from . import views

SLUG = r"(?P<slug>[-\w]+)"

urlpatterns = [
    route("menu", views.CatalogueView.as_view(), "catalogue"),
    route("menu/items", views.MenuItemListView.as_view(), "menu-items"),
    route(f"menu/items/{SLUG}", views.MenuItemDetailView.as_view(), "menu-item"),
    route("menu/categories", views.CategoryListView.as_view(), "menu-categories"),
    route("menu/drink-sections", views.DrinkSectionListView.as_view(), "menu-drink-sections"),
    route("menu/tags", views.TagListView.as_view(), "menu-tags"),
    route("menu/option-groups", views.OptionGroupListView.as_view(), "menu-option-groups"),
    route("admin/menu/items", views.AdminMenuItemListView.as_view(), "admin-menu-items"),
    route(f"admin/menu/items/{SLUG}", views.AdminMenuItemDetailView.as_view(), "admin-menu-item"),
    route(f"admin/menu/items/{SLUG}/publish", views.AdminMenuItemPublishView.as_view(), "admin-menu-item-publish"),
    route(f"admin/menu/items/{SLUG}/draft", views.AdminMenuItemDraftView.as_view(), "admin-menu-item-draft"),
    route(f"admin/menu/items/{SLUG}/restore", views.AdminMenuItemRestoreView.as_view(), "admin-menu-item-restore"),
]
