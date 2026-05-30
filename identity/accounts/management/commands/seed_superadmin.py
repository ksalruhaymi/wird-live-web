import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from core.services.phone_service import normalize_phone_number

User = get_user_model()


class Command(BaseCommand):
    help = "Create or update super admin user (admin / 12345)"

    def handle(self, *args, **options):
        username = os.getenv("DJANGO_SUPERUSER_USERNAME", "admin")
        password = os.getenv("DJANGO_SUPERUSER_PASSWORD", "12345")
        email = os.getenv("DJANGO_SUPERUSER_EMAIL", "ksalruhaymi@gmail.com")

        full_name = "المدير العام للنظام"
        display_name = "المدير العام للنظام"
        raw_mobile = "0551539188"

        try:
            mobile = normalize_phone_number(raw_mobile, "SA")
        except ValueError:
            mobile = None

        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "email": email,
                "full_name": full_name,
                "mobile": mobile,
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
            },
        )

        # Always ensure credentials and fields are up to date
        user.set_password(password)
        user.email = email
        user.full_name = full_name
        user.mobile = mobile
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.save()

        if created:
            self.stdout.write(self.style.SUCCESS(
                f"Super Admin CREATED → {username} / {password}"
            ))
        else:
            self.stdout.write(self.style.WARNING(
                "Super Admin UPDATED → password reset and data refreshed"
            ))