"""
python manage.py ensure_superadmin

Creates the owner's account from SUPERADMIN_EMAIL / SUPERADMIN_PASSWORD / SUPERADMIN_NAME when it does
not exist yet. Does nothing otherwise (the password is never overwritten), so it is safe in the
Render build command, where no shell is available on the free plan.
"""

from decouple import config
from django.core.management.base import BaseCommand

from accounts.models import User


class Command(BaseCommand):
    help = "Creates the superadmin from environment variables if missing."

    def handle(self, *args, **options):
        email = config("SUPERADMIN_EMAIL", default="").strip().lower()
        password = config("SUPERADMIN_PASSWORD", default="")
        if not email or not password:
            self.stdout.write("SUPERADMIN_EMAIL / SUPERADMIN_PASSWORD not set: skipped.")
            return
        if User.objects.filter(email=email).exists():
            self.stdout.write(f"{email} already exists: nothing to do.")
            return
        User.objects.create_superuser(email, password, name=config("SUPERADMIN_NAME", default="Owner"))
        self.stdout.write(self.style.SUCCESS(f"Superadmin {email} created."))
