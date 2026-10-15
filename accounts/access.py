"""
Who may do what (contract §3). Same rules as the website (lib/auth/roles.ts):

- client: own orders and notifications only.
- manager: processes orders; content rights only through an active ContentGrant.
- superadmin: everything.
"""

from rest_framework.permissions import BasePermission

from .models import GrantScope, Role

ROLE_PERMISSIONS = {
    Role.CLIENT: set(),
    Role.MANAGER: {"orders:process"},
    Role.SUPERADMIN: {
        "overview:view",
        "orders:process",
        "menu:edit",
        "labels:edit",
        "ads:manage",
        "content:publish",
        "managers:manage",
        "business:edit",
    },
}

# What each delegated scope unlocks for a manager
SCOPE_PERMISSIONS = {
    GrantScope.FOOD: {"menu:edit"},
    GrantScope.DRINKS: {"menu:edit"},
    GrantScope.LABELS: {"labels:edit"},
    GrantScope.ADS: {"ads:manage"},
    GrantScope.PUBLISH: {"content:publish"},
}

MENU_GROUP_SCOPES = {"food": GrantScope.FOOD, "drinks": GrantScope.DRINKS}


def permissions_for(user):
    if not user.is_active:
        return set()
    permissions = set(ROLE_PERMISSIONS[user.role])
    grant = user.active_grant
    if grant:
        for scope in grant.scopes:
            permissions |= SCOPE_PERMISSIONS.get(scope, set())
    return permissions


def editable_menu_groups(user):
    """Menu groups ("food", "drinks") the user may edit."""
    if user.is_superadmin:
        return set(MENU_GROUP_SCOPES)
    grant = user.active_grant
    return {group for group, scope in MENU_GROUP_SCOPES.items() if grant and scope in grant.scopes}


# ───────── DRF permission classes ─────────


def _signed_in(request):
    return bool(request.user and request.user.is_authenticated)


class IsClient(BasePermission):
    def has_permission(self, request, view):
        return _signed_in(request) and request.user.is_client


class IsStaff(BasePermission):
    def has_permission(self, request, view):
        return _signed_in(request) and request.user.is_staff_member


def require(*permissions, any_of=False):
    """`permission_classes = [require("menu:edit")]`, or `require("menu:edit", "labels:edit", any_of=True)`."""

    class Require(BasePermission):
        def has_permission(self, request, view):
            if not _signed_in(request):
                return False
            check = any if any_of else all
            return check(request.user.has_permission(p) for p in permissions)

    Require.__name__ = f"Require({', '.join(permissions)})"
    return Require
