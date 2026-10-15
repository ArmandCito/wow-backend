"""
Accounts: one User table for clients and staff.

- client: signs up on the website (email code), has a permanent client code ("WQB001A").
- manager: invited by the superadmin, processes orders; content rights only through a ContentGrant.
- superadmin: the owner, every permission (also the Django admin at /admin/).

Public ids: a client is identified by its client code, a staff member by its staff id ("eric").
The numeric primary key is never exposed.
"""

import hashlib
import secrets
from datetime import timedelta

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import IntegrityError, models, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.text import slugify


class Role(models.TextChoices):
    CLIENT = "client", "Client"
    MANAGER = "manager", "Manager"
    SUPERADMIN = "superadmin", "Superadmin"


class Status(models.TextChoices):
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"
    INVITED = "invited", "Invited"  # staff invitation not accepted yet


class Assignment(models.TextChoices):
    PICKUP_REGISTER = "pickup-register", "Pickup register"
    BACKUP = "backup", "Backup"
    NONE = "none", "None"


class Duty(models.TextChoices):
    ON = "on", "On duty"
    OFF = "off", "Off duty"


def normalize_email(email):
    return (email or "").strip().lower()


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **fields):
        """A client account (client code assigned). Staff accounts: create_staff()."""
        fields.setdefault("role", Role.CLIENT)
        user = self.model(email=normalize_email(email), **fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save_with_public_id()
        return user

    def create_staff(self, email, name, role=Role.MANAGER, password=None, **fields):
        return self.create_user(email, password, name=name, role=role, **fields)

    def create_superuser(self, email, password, **fields):
        fields.setdefault("name", "Owner")
        return self.create_staff(
            email, role=Role.SUPERADMIN, password=password, is_staff=True, is_superuser=True,
            duty=Duty.ON, **fields,
        )

    def get_by_natural_key(self, email):
        return self.get(email=normalize_email(email))


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=20, blank=True)  # "078 123 4567"
    role = models.CharField(max_length=12, choices=Role.choices, default=Role.CLIENT)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)

    client_code = models.CharField(max_length=7, unique=True, null=True, blank=True)
    staff_id = models.SlugField(max_length=40, unique=True, null=True, blank=True)

    # Staff only: register coverage
    assignment = models.CharField(max_length=16, choices=Assignment.choices, default=Assignment.NONE)
    duty = models.CharField(max_length=3, choices=Duty.choices, default=Duty.OFF)

    is_staff = models.BooleanField(default=False, help_text="Can open the Django admin (superadmin).")
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    class Meta:
        ordering = ["name"]
        indexes = [models.Index(fields=["role", "status"])]
        constraints = [
            models.CheckConstraint(
                condition=Q(role=Role.CLIENT, client_code__isnull=False, staff_id__isnull=True)
                | Q(role__in=[Role.MANAGER, Role.SUPERADMIN], client_code__isnull=True, staff_id__isnull=False),
                name="user_public_id_matches_role",
            ),
        ]

    def __str__(self):
        return f"{self.name} <{self.email}>"

    # ───────── Identity ─────────

    @property
    def public_id(self):
        return self.client_code or self.staff_id

    @property
    def is_active(self):
        # Used by Django (admin, password check) and Simple JWT
        return self.status == Status.ACTIVE

    @property
    def is_client(self):
        return self.role == Role.CLIENT

    @property
    def is_superadmin(self):
        return self.role == Role.SUPERADMIN

    @property
    def is_staff_member(self):
        return self.role in (Role.MANAGER, Role.SUPERADMIN)

    # ───────── Access (computed on every request, never cached in the token) ─────────

    @cached_property
    def active_grant(self):
        if self.role != Role.MANAGER:
            return None
        return self.content_grants.active().first()

    @cached_property
    def effective_permissions(self):
        from .access import permissions_for

        return permissions_for(self)

    def has_permission(self, permission):
        return self.is_active and permission in self.effective_permissions

    # ───────── Public ids ─────────

    def save_with_public_id(self):
        """Saves a new user with its client code or staff id (retries if another request took it)."""
        for _ in range(5):
            if self.role == Role.CLIENT:
                self.client_code, self.staff_id = next_client_code(), None
            else:
                self.client_code, self.staff_id = None, self.staff_id or next_staff_id(self.name)
            try:
                with transaction.atomic():
                    self.save()
                return
            except IntegrityError:
                if User.objects.filter(email=self.email).exists():
                    raise
                self.staff_id = None
        raise IntegrityError("Could not assign a unique public id.")


def client_code(index):
    """0 -> WQB001A … 998 -> WQB999A, 999 -> WQB001B …"""
    letter, number = divmod(index, 999)
    return f"WQB{number + 1:03d}{chr(ord('A') + letter % 26)}"


def next_client_code():
    index = User.objects.filter(role=Role.CLIENT).count()
    while User.objects.filter(client_code=client_code(index)).exists():
        index += 1
    return client_code(index)


def next_staff_id(name):
    base = slugify(name.split()[0] if name.strip() else "staff")[:30] or "staff"
    candidate, suffix = base, 2
    while User.objects.filter(staff_id=candidate).exists():
        candidate, suffix = f"{base}-{suffix}", suffix + 1
    return candidate


# ───────── Sign-up with an email code ─────────


class PendingSignup(models.Model):
    """
    A sign-up waiting for its email code. The account is created only once the code is verified,
    so an unverified email never blocks a real person from signing up later.
    """

    CODE_LENGTH = 6
    LIFETIME = timedelta(minutes=10)
    MAX_ATTEMPTS = 5
    RESEND_DELAY = timedelta(seconds=30)

    email = models.EmailField(unique=True)
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=20, blank=True)
    password = models.CharField(max_length=128)  # hashed, like User.password
    lang = models.CharField(max_length=2, default="en")
    code_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    sent_at = models.DateTimeField()

    def new_code(self):
        code = f"{secrets.randbelow(10 ** self.CODE_LENGTH):0{self.CODE_LENGTH}d}"
        now = timezone.now()
        self.code_hash = _hash(f"{self.email}:{code}")
        self.expires_at = now + self.LIFETIME
        self.sent_at = now
        self.attempts = 0
        return code

    def code_matches(self, code):
        return secrets.compare_digest(self.code_hash, _hash(f"{self.email}:{code}"))

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    def seconds_before_resend(self):
        wait = (self.sent_at + self.RESEND_DELAY - timezone.now()).total_seconds()
        return max(0, int(wait) + (wait % 1 > 0))


# ───────── One-time links (password reset, staff invitation) ─────────


class AccountToken(models.Model):
    class Purpose(models.TextChoices):
        PASSWORD_RESET = "password-reset"
        INVITATION = "invitation"

    LIFETIMES = {Purpose.PASSWORD_RESET: timedelta(hours=1), Purpose.INVITATION: timedelta(days=7)}

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="tokens")
    purpose = models.CharField(max_length=16, choices=Purpose.choices)
    token_hash = models.CharField(max_length=64, unique=True)  # the token itself is only in the email
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def issue(cls, user, purpose):
        """Invalidates the user's previous links for this purpose and returns a new raw token."""
        cls.objects.filter(user=user, purpose=purpose, used_at__isnull=True).update(used_at=timezone.now())
        raw = secrets.token_urlsafe(32)
        cls.objects.create(
            user=user, purpose=purpose, token_hash=_hash(raw), expires_at=timezone.now() + cls.LIFETIMES[purpose]
        )
        return raw

    @classmethod
    def consume(cls, raw, purpose):
        """The user of a valid token (marked used), or None."""
        token = (
            cls.objects.select_for_update()
            .select_related("user")
            .filter(token_hash=_hash(raw or ""), purpose=purpose, used_at__isnull=True, expires_at__gt=timezone.now())
            .first()
        )
        if token is None:
            return None
        token.used_at = timezone.now()
        token.save(update_fields=["used_at"])
        return token.user


def _hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


# ───────── Temporary content rights of a manager ─────────


class GrantScope(models.TextChoices):
    FOOD = "food"
    DRINKS = "drinks"
    LABELS = "labels"
    ADS = "ads"
    PUBLISH = "publish"


class ContentGrantQuerySet(models.QuerySet):
    def current(self):
        """Not revoked and not expired (may start later)."""
        now = timezone.now()
        return self.filter(revoked_at__isnull=True).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))

    def active(self):
        """In force right now."""
        return self.current().filter(starts_at__lte=timezone.now())


class ContentGrant(models.Model):
    """
    Content rights delegated by the superadmin to one manager, for a period (no end = until revoked).
    Never edited: a new grant replaces the previous one, which keeps the history.
    """

    manager = models.ForeignKey(User, on_delete=models.CASCADE, related_name="content_grants")
    granted_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")
    scopes = models.JSONField(default=list)
    starts_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ContentGrantQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.manager} {self.scopes}"

    def revoke(self):
        self.revoked_at = timezone.now()
        self.save(update_fields=["revoked_at"])
