"""
Order use cases: checkout, register transitions, payment confirmation, assignment.

The server is the only source of prices: the cart sends item and choice ids, never amounts.
"""

from django.db import transaction
from django.db.models import Count, Q

from accounts.models import Assignment, Duty, Role, Status, User
from audit.services import record
from business.models import BusinessSettings
from core.errors import (
    Conflict,
    Forbidden,
    InvalidTransition,
    ItemUnavailable,
    NotAssigned,
    NotFound,
    ValidationFailed,
)
from core.fields import localized
from core.time import iso, now
from menu.models import MenuItem, OptionChoice
from notifications.services import notify_stage

from .models import ACTIVE_STAGES, TRANSITIONS, Order, OrderLine, PaymentMethod, PaymentStatus, Stage

# ───────── Checkout ─────────


def price_lines(cart_lines):
    """
    Checks every cart line against the live menu and returns the priced lines.
    Raises ItemUnavailable (409, details.itemIds) or ValidationFailed (422) for bad choices.
    """
    slugs = {line["item_id"] for line in cart_lines}
    items = {
        item.slug: item
        for item in MenuItem.objects.public().filter(slug__in=slugs).prefetch_related("option_groups")
    }
    unavailable = sorted(slug for slug in slugs if slug not in items or not items[slug].is_available)
    if unavailable:
        raise ItemUnavailable(details={"item_ids": unavailable})

    choice_slugs = {slug for line in cart_lines for slug in line["choices"]}
    choices = {c.slug: c for c in OptionChoice.objects.filter(slug__in=choice_slugs, is_available=True).select_related("group")}

    priced, problems = [], {}
    for index, line in enumerate(cart_lines):
        item = items[line["item_id"]]
        groups = {group.id: group for group in item.option_groups.all()}
        picked = [choices.get(slug) for slug in dict.fromkeys(line["choices"])]

        if any(choice is None or choice.group_id not in groups for choice in picked):
            problems[f"lines.{index}.choices"] = "invalid_choice"
            continue
        per_group = count_by_group(picked)
        for group in groups.values():
            count = per_group.get(group.id, 0)
            if group.required and count == 0:
                problems[f"lines.{index}.choices"] = "required_option_missing"
            elif group.max_choices and count > group.max_choices:
                problems[f"lines.{index}.choices"] = "too_many_choices"

        unit = item.price + sum(choice.price for choice in picked)
        priced.append({
            "item": item,
            "quantity": line["quantity"],
            "choices": [choice.slug for choice in picked],
            "choice_details": [
                {"id": choice.slug, "name": localized(choice, "name"), "price": choice.price} for choice in picked
            ],
            "note": line.get("note", "").strip(),
            "unit_price": unit,
            "total": unit * line["quantity"],
        })

    if problems:
        raise ValidationFailed("Some options are not valid for these items.", details=problems)
    return priced


def count_by_group(choices):
    counts = {}
    for choice in choices:
        counts[choice.group_id] = counts.get(choice.group_id, 0) + 1
    return counts


def contact_for(user, contact):
    """Name and phone of the order: the checkout form, completed from the client's profile."""
    if user is None:
        missing = {field: "required" for field in ("name", "phone") if not contact.get(field)}
        if missing:
            raise ValidationFailed(
                "Guests give a name and a phone number.", details={f"contact.{f}": c for f, c in missing.items()}
            )
        return contact["name"], contact["phone"], contact.get("email", "")
    phone = contact.get("phone") or user.phone
    if not phone:
        raise ValidationFailed("A phone number is needed for the order.", details={"contact.phone": "required"})
    return contact.get("name") or user.name, phone, contact.get("email") or user.email


@transaction.atomic
def place_order(user, data):
    """`user` is the signed-in client, or None for a guest ("Continue without signing in")."""
    if user is not None and not user.is_client:
        raise Forbidden("Staff accounts cannot place orders.")

    lines = price_lines(data["lines"])
    name, phone, email = contact_for(user, data["contact"])
    if user is not None and not user.phone:
        user.phone = phone  # the phone asked at checkout completes the profile
        user.save(update_fields=["phone"])

    business = BusinessSettings.load()
    subtotal = sum(line["total"] for line in lines)
    fees = business.fees_for(data["fulfilment"])
    placed_at = now()

    order = Order.objects.create(
        client=user,
        guest=user is None,
        contact_name=name,
        contact_phone=phone,
        contact_email=email,
        manager=pick_manager(),
        fulfilment=data["fulfilment"],
        address=data["address"],
        payment=data["payment"],
        notes=data["notes"],
        subtotal=subtotal,
        fees=fees,
        total=subtotal + fees,
        placed_at=placed_at,
        history={Stage.NEW: iso(placed_at)},
    )
    OrderLine.objects.bulk_create([
        OrderLine(
            order=order,
            item=line["item"],
            item_slug=line["item"].slug,
            name_en=line["item"].name_en,
            name_fr=line["item"].name_fr,
            quantity=line["quantity"],
            choices=line["choices"],
            choice_details=line["choice_details"],
            note=line["note"],
            unit_price=line["unit_price"],
            total=line["total"],
        )
        for line in lines
    ])

    notify_stage(order)
    record(
        actor=None, scope="orders", type="order.placed", target=user,
        data={"order_id": order.public_id, "client_code": customer_label(order), "total": order.total},
        text=("{order} placed · {customer}", "{order} passée · {customer}"),
        values={"order": order.public_id, "customer": customer_label(order)},
    )
    return order


# ───────── Register ─────────


def pick_manager(exclude=None):
    """
    Manager in charge of a new order: the on-duty pickup-register manager with the fewest active
    orders, else an on-duty backup, else any on-duty manager; None when nobody is on duty
    (the superadmin then assigns it).
    """
    managers = (
        User.objects.filter(role=Role.MANAGER, status=Status.ACTIVE, duty=Duty.ON)
        .exclude(pk=getattr(exclude, "pk", None))
        .annotate(load=Count("assigned_orders", filter=Q(assigned_orders__stage__in=ACTIVE_STAGES)))
        .order_by("load", "id")
    )
    for assignment in (Assignment.PICKUP_REGISTER, Assignment.BACKUP, None):
        candidates = managers if assignment is None else managers.filter(assignment=assignment)
        manager = candidates.first()
        if manager:
            return manager
    return None


def check_can_act(order, actor):
    """The superadmin acts on every order; a manager on the orders assigned to them."""
    if actor.is_superadmin:
        return
    if order.manager_id is None:
        order.manager = actor  # an unassigned order is taken by the first manager who acts on it
        return
    if order.manager_id != actor.id:
        raise NotAssigned()


STAGE_AUDIT = {
    Stage.ACCEPTED: ("{order} accepted · {customer}", "{order} acceptée · {customer}"),
    Stage.PREPARING: ("{order} moved to Preparing · {customer}", "{order} passée en préparation · {customer}"),
    Stage.READY: ("{order} marked Ready · {customer}", "{order} marquée comme prête · {customer}"),
    Stage.COMPLETED: ("{order} completed · {customer}", "{order} terminée · {customer}"),
    Stage.CANCELLED: ("{order} cancelled · {customer}", "{order} annulée · {customer}"),
}


@transaction.atomic
def transition(order_id, to, actor):
    order = _locked(order_id)
    check_can_act(order, actor)
    if to not in TRANSITIONS.get(order.stage, set()):
        raise InvalidTransition(details={"from": order.stage, "to": to})

    order.stage = to
    order.history = {**order.history, to: iso(now())}
    if to == Stage.COMPLETED and order.payment == PaymentMethod.PAY_ON_PICKUP:
        order.payment_status = PaymentStatus.PAID
    elif to == Stage.CANCELLED and order.payment_status == PaymentStatus.PENDING:
        order.payment_status = PaymentStatus.NOT_CHARGED
    order.save()

    notify_stage(order)
    record(
        actor=actor, scope="orders", type="order.transition", target=order.client,
        data={"order_id": order.public_id, "to": to, "client_code": customer_label(order)},
        text=STAGE_AUDIT[to], values={"order": order.public_id, "customer": customer_label(order)},
    )
    return order


@transaction.atomic
def confirm_payment(order_id, actor):
    """Mobile Money is checked by staff (no payment gateway yet): marks the order paid."""
    order = _locked(order_id)
    check_can_act(order, actor)
    if order.stage == Stage.CANCELLED:
        raise Conflict("A cancelled order cannot be paid.")
    if order.payment_status != PaymentStatus.PAID:
        order.payment_status = PaymentStatus.PAID
        order.save()
        record(
            actor=actor, scope="orders", type="order.paid", target=order.client,
            data={"order_id": order.public_id, "payment": order.payment},
            text=("{order} payment confirmed · {customer}", "{order} paiement confirmé · {customer}"),
            values={"order": order.public_id, "customer": customer_label(order)},
        )
    return order


@transaction.atomic
def assign(order_id, manager_id, actor):
    """Superadmin only: gives an order to another manager."""
    order = _locked(order_id)
    manager = User.objects.filter(staff_id=manager_id, role=Role.MANAGER, status=Status.ACTIVE).first()
    if manager is None:
        raise ValidationFailed("Unknown or inactive manager.", details={"manager_id": "does_not_exist"})
    order.manager = manager
    order.save()
    record(
        actor=actor, scope="orders", type="order.assigned", target=manager,
        data={"order_id": order.public_id, "manager_id": manager.staff_id},
        text=("{order} assigned to {manager}", "{order} confiée à {manager}"),
        values={"order": order.public_id, "manager": manager.name},
    )
    return order


def _locked(order_id):
    order = Order.objects.select_for_update().by_public_id(order_id).first()
    if order is None:
        raise NotFound()
    return order


def customer_label(order):
    """Client code, or "Guest · Aline" for orders without an account."""
    return order.client.client_code if order.client else f"Guest · {order.contact_name}"
