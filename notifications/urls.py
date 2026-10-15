from core.routing import route

from . import views

urlpatterns = [
    route("me/notifications", views.NotificationListView.as_view(), "my-notifications"),
    route("me/notifications/read", views.NotificationReadView.as_view(), "my-notifications-read"),
]
