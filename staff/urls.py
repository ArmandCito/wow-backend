from audit.views import AuditListView
from core.routing import route

from . import views

STAFF_ID = r"(?P<staff_id>[-\w]+)"

urlpatterns = [
    route("admin/managers", views.ManagerListView.as_view(), "managers"),
    route(f"admin/managers/{STAFF_ID}", views.ManagerDetailView.as_view(), "manager"),
    route(f"admin/managers/{STAFF_ID}/suspend", views.ManagerSuspendView.as_view(), "manager-suspend"),
    route(f"admin/managers/{STAFF_ID}/reactivate", views.ManagerReactivateView.as_view(), "manager-reactivate"),
    route(f"admin/managers/{STAFF_ID}/grant", views.ManagerGrantView.as_view(), "manager-grant"),
    route(f"admin/managers/{STAFF_ID}/resend-invitation", views.InvitationResendView.as_view(), "manager-invitation-resend"),
    route("admin/invitations", views.InvitationView.as_view(), "invitations"),
    route("admin/overview", views.OverviewView.as_view(), "overview"),
    route("admin/audit", AuditListView.as_view(), "audit"),
]
