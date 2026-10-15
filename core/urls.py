from .routing import route
from .views import UploadView

urlpatterns = [
    route("admin/uploads", UploadView.as_view(), "uploads"),
]
