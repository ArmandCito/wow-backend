from core.routing import route

from . import views

urlpatterns = [
    route("business", views.BusinessView.as_view(), "business"),
    route("admin/business", views.BusinessAdminView.as_view(), "business-admin"),
]
