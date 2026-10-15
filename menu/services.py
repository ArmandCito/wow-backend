"""
Menu editing (contract §9): drafts, publication, scopes of delegated managers.

Changes are handled as plain dicts with model column names, e.g.
{"name_en": "...", "price": 6000, "categories": ["burgers"], "section": None, "is_available": True}.
"""

from django.db import transaction
from django.utils.text import slugify

from accounts.access import editable_menu_groups
from audit.services import record
from core.errors import Conflict, Forbidden
from core.fields import localized
from core.time import rwf

from .models import Category, DrinkSection, MenuItem, OptionGroup, Tag

SCALAR_FIELDS = [
    "name_en", "name_fr", "description_en", "description_fr", "cart_meta_en", "cart_meta_fr",
    "price", "image", "group", "is_new", "is_available",
]
RELATED = {"section": DrinkSection, "pairs_with": MenuItem}
MANY = {"categories": (Category, "slug"), "tags": (Tag, "key"), "option_groups": (OptionGroup, "slug")}


# ───────── Permissions ─────────


def check_can_edit(user, item, changes):
    """
    - menu:edit, limited to the groups of the manager's grant (food and/or drinks);
    - the NEW badge also needs labels:edit; a labels-only grant may change nothing else.
    """
    if "is_new" in changes and not user.has_permission("labels:edit"):
        raise Forbidden("Changing the NEW badge needs the labels permission.")
    if set(changes) <= {"is_new"} and user.has_permission("labels:edit"):
        return
    if not user.has_permission("menu:edit"):
        raise Forbidden("Editing menu items needs the menu permission.")
    groups = {changes.get("group"), item.group if item else None} - {None}
    if not groups <= editable_menu_groups(user):
        raise Forbidden("Your content grant does not cover this part of the menu.")


# ───────── Changes ─────────


def item_values(item):
    """The live values of an item, in the same form as the changes."""
    values = {field: getattr(item, field) for field in SCALAR_FIELDS}
    values["section"] = item.section.slug if item.section else None
    values["pairs_with"] = item.pairs_with.slug if item.pairs_with else None
    for field, (_model, key) in MANY.items():
        values[field] = [getattr(obj, key) for obj in getattr(item, field).all()]
    return values


def apply_changes(item, changes):
    for field in SCALAR_FIELDS:
        if field in changes:
            setattr(item, field, changes[field])
    for field, model in RELATED.items():
        if field in changes:
            slug = changes[field]
            setattr(item, field, model.objects.filter(slug=slug).first() if slug else None)
    item.save()
    for field, (model, key) in MANY.items():
        if field in changes:
            objects = {getattr(obj, key): obj for obj in model.objects.filter(**{f"{key}__in": changes[field]})}
            getattr(item, field).set([objects[value] for value in changes[field] if value in objects])


def draft_as_input(item):
    """The pending version of a published item, shaped like MenuItemInput (None without changes)."""
    if not item.draft:
        return None
    values = {**item_values(item), **item.draft}
    data = {"id": item.slug}
    for base in ("name", "description", "cart_meta"):
        data[base] = {lang: values.get(f"{base}_{lang}", "") for lang in ("en", "fr")}
    for field in ("price", "image", "group", "section", "categories", "tags", "option_groups", "pairs_with", "is_new"):
        data[field] = values.get(field)
    data["available"] = values.get("is_available")
    return data


def unique_slug(text):
    base = slugify(text)[:70] or "item"
    slug, suffix = base, 2
    while MenuItem.objects.filter(slug=slug).exists():
        slug, suffix = f"{base}-{suffix}", suffix + 1
    return slug


# ───────── Use cases ─────────


@transaction.atomic
def create_item(user, changes):
    check_can_edit(user, None, changes)
    slug = changes.pop("slug", None) or unique_slug(changes["name_en"])
    item = MenuItem(slug=slug, is_published=False, updated_by=user)
    apply_changes(item, changes)
    _audit_draft(user, item, changes)
    return item


@transaction.atomic
def update_item(user, item, changes):
    check_can_edit(user, item, changes)
    if item.is_published:
        # The website keeps the published version until POST …/publish
        item.draft = {**(item.draft or {}), **changes}
        item.updated_by = user
        item.save(update_fields=["draft", "updated_by", "updated_at"])
    else:
        item.updated_by = user
        apply_changes(item, changes)
    _audit_draft(user, item, changes)
    return item


@transaction.atomic
def publish_item(user, item):
    if not user.has_permission("content:publish"):
        raise Forbidden("Publishing needs the publish permission.")
    if item.deleted_at:
        raise Conflict("Restore the item before publishing it.")
    changes = item.draft or {}
    item.draft = None
    item.is_published = True
    item.updated_by = user
    apply_changes(item, changes)
    record(
        actor=user, scope="content", type="menu.published", data={"item_id": item.slug},
        text=("{item} published · {price}{badge}", "{item} publié · {price}{badge}"),
        values={"item": localized(item, "name"), "price": rwf(item.price), "badge": _badge(item.is_new)},
    )
    return item


@transaction.atomic
def discard_draft(user, item):
    check_can_edit(user, item, {})
    item.draft = None
    item.save(update_fields=["draft", "updated_at"])
    return item


@transaction.atomic
def delete_item(user, item):
    check_can_edit(user, item, {})
    item.soft_delete()
    record(
        actor=user, scope="content", type="menu.deleted", data={"item_id": item.slug},
        text=("{item} removed from the menu", "{item} retiré du menu"), values={"item": localized(item, "name")},
    )


@transaction.atomic
def restore_item(user, item):
    check_can_edit(user, item, {})
    item.deleted_at = None
    item.save(update_fields=["deleted_at", "updated_at"])
    return item


def _badge(is_new):
    return {"en": " · NEW enabled", "fr": " · NOUVEAU activé"} if is_new else ""


def _audit_draft(user, item, changes):
    name = {"en": changes.get("name_en", item.name_en), "fr": changes.get("name_fr", item.name_fr)}
    record(
        actor=user, scope="content", type="menu.draft", data={"item_id": item.slug, "fields": sorted(changes)},
        text=("{item} draft updated · {price}{badge}", "Brouillon de {item} mis à jour · {price}{badge}"),
        values={"item": name, "price": rwf(changes.get("price", item.price)), "badge": _badge(changes.get("is_new"))},
    )
