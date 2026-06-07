import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from identity.accounts.user_types import USER_TYPE_ADMIN
from identity.rbac.models import Role

User = get_user_model()

ADMIN_USERNAME = "admin"
ADMIN_EMAIL = "admin@wird.me"
DEFAULT_ADMIN_PASSWORD = "WirdAdmin-ChangeMe!"


class Command(BaseCommand):
    help = "Create or update the primary admin user (idempotent)."

    @transaction.atomic
    def handle(self, *args, **options):
        username = os.getenv("DJANGO_SUPERUSER_USERNAME", ADMIN_USERNAME).strip()
        email = os.getenv("DJANGO_SUPERUSER_EMAIL", ADMIN_EMAIL).strip()
        password = os.getenv("DJANGO_SUPERUSER_PASSWORD", DEFAULT_ADMIN_PASSWORD)

        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "email": email,
                "user_type": USER_TYPE_ADMIN,
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
            },
        )

        user.email = email
        user.user_type = USER_TYPE_ADMIN
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        if created:
            user.set_password(password)
        user.save()

        admin_role = Role.objects.filter(slug="admin").first()
        if admin_role:
            user.roles.set([admin_role])

        if created:
            self.stdout.write(
                self.style.SUCCESS(f"Admin CREATED → {username} ({email})")
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"Admin UPDATED → {username} ({email}); password unchanged"
                )
            )
