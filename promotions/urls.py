from core.routing import route

from . import views

SLUG = r"(?P<slug>[-\w]+)"

urlpatterns = [
    route("promotions", views.PromotionListView.as_view(), "promotions"),
    route("admin/campaigns", views.CampaignListView.as_view(), "campaigns"),
    route(f"admin/campaigns/{SLUG}", views.CampaignDetailView.as_view(), "campaign"),
    route(f"admin/campaigns/{SLUG}/publish", views.CampaignPublishView.as_view(), "campaign-publish"),
    route(f"admin/campaigns/{SLUG}/pause", views.CampaignPauseView.as_view(), "campaign-pause"),
    route(f"admin/campaigns/{SLUG}/resume", views.CampaignResumeView.as_view(), "campaign-resume"),
    route(f"admin/campaigns/{SLUG}/cancel-schedule", views.CampaignCancelScheduleView.as_view(), "campaign-cancel-schedule"),
]
