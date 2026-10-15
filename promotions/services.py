"""Campaign workflow: draft → (scheduled →) published ⇄ paused. Every step is audited."""

from django.utils import timezone
from django.utils.text import slugify

from audit.services import record
from core.errors import Conflict, Forbidden
from core.fields import localized

from .models import Campaign

Status = Campaign.Status

AUDIT = {
    "saved": ("Ad “{title}” saved as draft", "Publicité « {title} » enregistrée en brouillon"),
    "updated": ("Ad “{title}” updated", "Publicité « {title} » modifiée"),
    "published": ("Ad “{title}” published", "Publicité « {title} » publiée"),
    "scheduled": ("Ad “{title}” scheduled", "Publicité « {title} » programmée"),
    "paused": ("Ad “{title}” paused", "Publicité « {title} » mise en pause"),
    "resumed": ("Ad “{title}” resumed", "Publicité « {title} » relancée"),
    "deleted": ("Ad “{title}” deleted", "Publicité « {title} » supprimée"),
    "unscheduled": ("Ad “{title}” schedule cancelled", "Programmation de la publicité « {title} » annulée"),
}


def unique_slug(title):
    base = slugify(title)[:70] or "campaign"
    slug, suffix = base, 2
    while Campaign.objects.filter(slug=slug).exists():
        slug, suffix = f"{base}-{suffix}", suffix + 1
    return slug


def audit(user, campaign, event):
    record(
        actor=user, scope="content", type=f"campaign.{event}", data={"campaign_id": campaign.slug},
        text=AUDIT[event], values={"title": localized(campaign, "title")},
    )


def check_can_edit(user, campaign):
    """A live campaign changes on the website at once: editing it also needs the publish permission."""
    if campaign.status != Status.DRAFT and not user.has_permission("content:publish"):
        raise Forbidden("Editing a live campaign needs the publish permission.")


def live_status(campaign):
    """published, or scheduled when the start date is in the future."""
    if campaign.starts_at and campaign.starts_at > timezone.now():
        return Status.SCHEDULED
    return Status.PUBLISHED


def refresh_status(campaign):
    """After a date change, a live campaign is scheduled or published according to its start."""
    if campaign.status in (Status.SCHEDULED, Status.PUBLISHED) and campaign.status != live_status(campaign):
        campaign.status = live_status(campaign)
        campaign.save(update_fields=["status", "updated_at"])


def publish(user, campaign):
    if campaign.status not in (Status.DRAFT, Status.PAUSED):
        raise Conflict("Only a draft or a paused campaign can be published.")
    if campaign.ends_at and campaign.ends_at <= timezone.now():
        raise Conflict("This campaign has already ended: change its end date first.")
    campaign.status = live_status(campaign)
    campaign.save(update_fields=["status", "updated_at"])
    audit(user, campaign, "scheduled" if campaign.status == Status.SCHEDULED else "published")
    return campaign


def pause(user, campaign):
    if campaign.status not in (Status.PUBLISHED, Status.SCHEDULED):
        raise Conflict("Only a live or scheduled campaign can be paused.")
    campaign.status = Status.PAUSED
    campaign.save(update_fields=["status", "updated_at"])
    audit(user, campaign, "paused")
    return campaign


def resume(user, campaign):
    if campaign.status != Status.PAUSED:
        raise Conflict("Only a paused campaign can be resumed.")
    campaign.status = live_status(campaign)
    campaign.save(update_fields=["status", "updated_at"])
    audit(user, campaign, "resumed")
    return campaign


def cancel_schedule(user, campaign):
    if campaign.effective_status != Status.SCHEDULED:
        raise Conflict("Only a campaign that has not started yet can be unscheduled.")
    campaign.status = Status.DRAFT
    campaign.save(update_fields=["status", "updated_at"])
    audit(user, campaign, "unscheduled")
    return campaign


def delete(user, campaign):
    if campaign.status != Status.DRAFT:
        raise Conflict("Only drafts can be deleted: pause the campaign instead.")
    audit(user, campaign, "deleted")
    campaign.delete()
