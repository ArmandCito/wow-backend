"""
Staff administration by the superadmin (contract §10): directory, invitations, content grants,
suspension. Every change is audited, worded like the website (i18n/dictionaries/*/staff.ts).
"""

from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.utils import timezone

from accounts.models import AccountToken, Assignment, ContentGrant, Duty, Role, Status, User
from accounts.services import revoke_sessions
from audit.services import record
from core import emails
from core.errors import Conflict, EmailTaken, ValidationFailed
from core.time import short_date
from orders.models import ACTIVE_STAGES, Order
from orders.services import pick_manager

ASSIGNMENT = {
    Assignment.PICKUP_REGISTER: {"en": "Pickup register", "fr": "Registre des retraits"},
    Assignment.BACKUP: {"en": "Backup", "fr": "Remplacement"},
    Assignment.NONE: {"en": "Unassigned", "fr": "Non affecté"},
}
DUTY = {Duty.ON: {"en": "On duty", "fr": "En service"}, Duty.OFF: {"en": "Off duty", "fr": "Hors service"}}
SCOPES = {
    "food": {"en": "Food upload / edit", "fr": "Importer / modifier les plats"},
    "drinks": {"en": "Drink upload / edit", "fr": "Importer / modifier les boissons"},
    "labels": {"en": "Set / remove NEW", "fr": "Ajouter / retirer NOUVEAU"},
    "ads": {"en": "Manage ads", "fr": "Gérer les publicités"},
    "publish": {"en": "Publish content", "fr": "Publier du contenu"},
}


def managers():
    """Managers with their active order count and current grant (one query each)."""
    return (
        User.objects.filter(role=Role.MANAGER)
        .annotate(active_orders=Count("assigned_orders", filter=Q(assigned_orders__stage__in=ACTIVE_STAGES)))
        .prefetch_related(
            Prefetch(
                "content_grants",
                queryset=ContentGrant.objects.current().select_related("granted_by"),
                to_attr="current_grants",
            )
        )
    )


def _audit(actor, manager, type, text, values=None, data=None):
    record(actor=actor, scope="access", type=type, target=manager, text=text, values=values,
           data={"manager_id": manager.staff_id, **(data or {})})


@transaction.atomic
def update_manager(actor, manager, changes):
    suspended = manager.status == Status.SUSPENDED
    if suspended and (changes.get("duty") == Duty.ON or changes.get("assignment", Assignment.NONE) != Assignment.NONE):
        raise Conflict("A suspended manager cannot be put on duty or assigned.", code="manager_suspended")
    for field, value in changes.items():
        setattr(manager, field, value)
    manager.save(update_fields=list(changes) or None)
    _audit(
        actor, manager, "manager.updated",
        ("Manager updated · {assignment} · {duty}", "Gestionnaire mis à jour · {assignment} · {duty}"),
        {"assignment": ASSIGNMENT[manager.assignment], "duty": DUTY[manager.duty]},
        data={"changes": changes},
    )
    return manager


@transaction.atomic
def suspend(actor, manager):
    """
    Blocks the account at once (every request answers 403 account_suspended), removes its assignment
    and grant, and hands its active orders to another on-duty manager (or leaves them unassigned).
    """
    if manager.status == Status.SUSPENDED:
        return manager
    manager.status, manager.duty, manager.assignment = Status.SUSPENDED, Duty.OFF, Assignment.NONE
    manager.save(update_fields=["status", "duty", "assignment"])
    ContentGrant.objects.filter(manager=manager).current().update(revoked_at=timezone.now())
    revoke_sessions(manager)

    replacement = pick_manager(exclude=manager)
    moved = Order.objects.filter(manager=manager, stage__in=ACTIVE_STAGES).update(manager=replacement)
    _audit(
        actor, manager, "manager.suspended",
        ("Manager access suspended · no assignments", "Accès gestionnaire suspendu · aucune affectation"),
        data={"orders_moved": moved, "to": replacement.staff_id if replacement else None},
    )
    return manager


@transaction.atomic
def reactivate(actor, manager):
    if manager.status != Status.SUSPENDED:
        raise Conflict("Only a suspended manager can be reactivated.")
    manager.status = Status.ACTIVE
    manager.save(update_fields=["status"])
    _audit(actor, manager, "manager.reactivated", ("Manager access restored", "Accès gestionnaire rétabli"))
    return manager


@transaction.atomic
def set_grant(actor, manager, scopes, starts_at=None, expires_at=None):
    """Replaces the manager's grant. Takes effect on the manager's next request."""
    if manager.status != Status.ACTIVE:
        raise Conflict("Content rights can only be given to an active manager.")
    starts_at = starts_at or timezone.now()
    if expires_at and expires_at <= max(starts_at, timezone.now()):
        raise ValidationFailed("The grant must end in the future, after it starts.", details={"expires_at": "invalid"})

    ContentGrant.objects.filter(manager=manager).current().update(revoked_at=timezone.now())
    scopes = [scope for scope in SCOPES if scope in scopes]  # known scopes, fixed order
    grant = ContentGrant.objects.create(
        manager=manager, granted_by=actor, scopes=scopes, starts_at=starts_at, expires_at=expires_at
    )
    expiry = (
        {"en": f"until {short_date(expires_at)}", "fr": f"jusqu’au {short_date(expires_at)}"}
        if expires_at else {"en": "no expiry", "fr": "sans expiration"}
    )
    _audit(
        actor, manager, "grant.created",
        ("Content permissions granted: {scopes} · {expiry}", "Autorisations de contenu accordées : {scopes} · {expiry}"),
        {"scopes": {lang: ", ".join(SCOPES[s][lang] for s in scopes) for lang in ("en", "fr")}, "expiry": expiry},
        data={"scopes": scopes, "expires_at": expires_at.isoformat() if expires_at else None},
    )
    return grant


@transaction.atomic
def revoke_grant(actor, manager):
    revoked = ContentGrant.objects.filter(manager=manager).current().update(revoked_at=timezone.now())
    if revoked:
        _audit(
            actor, manager, "grant.revoked",
            ("Content access revoked. Order access retained.", "Accès au contenu révoqué. Accès aux commandes conservé."),
        )
    return revoked


@transaction.atomic
def invite(actor, name, email, assignment, lang):
    """Creates the manager account (status "invited") and emails the link to choose a password."""
    if User.objects.filter(email=email).exists():
        raise EmailTaken()
    manager = User.objects.create_staff(email, name, status=Status.INVITED, assignment=assignment)
    send_invitation(actor, manager, lang)
    _audit(actor, manager, "manager.invited", ("Invitation sent · {email}", "Invitation envoyée · {email}"),
           {"email": email})
    return manager


def send_invitation(actor, manager, lang):
    if manager.status != Status.INVITED:
        raise Conflict("This manager has already accepted the invitation.")
    raw = AccountToken.issue(manager, AccountToken.Purpose.INVITATION)
    emails.send(
        "staff_invitation", manager.email, lang, name=manager.name, inviter=actor.name,
        link=emails.frontend_link(lang, "/accept-invitation", token=raw),
        days=AccountToken.LIFETIMES[AccountToken.Purpose.INVITATION].days,
    )
