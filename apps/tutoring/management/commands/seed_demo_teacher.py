import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.tutoring.models import TeacherAvailability, TeacherProfile
from identity.accounts.user_types import USER_TYPE_TEACHER
from identity.rbac.models import Role

User = get_user_model()

DEMO_USERNAME = "demo_teacher"
DEMO_EMAIL = "demo.teacher@wird.local"
DEMO_DISPLAY_NAME = "المعلم التجريبي"
DEFAULT_DEMO_PASSWORD = "WirdDemoTeacher-ChangeMe!"


class Command(BaseCommand):
    help = "Create or update the automated demo teacher account (idempotent)."

    @transaction.atomic
    def handle(self, *args, **options):
        password = os.getenv("SEED_DEMO_TEACHER_PASSWORD", DEFAULT_DEMO_PASSWORD)

        user, created = User.objects.get_or_create(
            username=DEMO_USERNAME,
            defaults={
                "email": DEMO_EMAIL,
                "full_name": DEMO_DISPLAY_NAME,
                "user_type": USER_TYPE_TEACHER,
                "is_staff": False,
                "is_superuser": False,
                "is_active": True,
            },
        )

        user.email = DEMO_EMAIL
        user.full_name = DEMO_DISPLAY_NAME
        user.user_type = USER_TYPE_TEACHER
        user.is_staff = False
        user.is_superuser = False
        user.is_active = True
        if created:
            user.set_password(password)
        user.save()

        teacher_role = Role.objects.filter(slug="teacher").first()
        if teacher_role:
            user.roles.set([teacher_role])

        profile, profile_created = TeacherProfile.objects.get_or_create(
            user=user,
            defaults={
                "display_name": DEMO_DISPLAY_NAME,
                "is_approved": True,
                "approval_status": TeacherProfile.ApprovalStatus.APPROVED,
                "can_audio": True,
                "can_video": True,
                "is_demo_teacher": True,
                "auto_accept_calls": True,
            },
        )
        profile.display_name = DEMO_DISPLAY_NAME
        profile.is_approved = True
        profile.approval_status = TeacherProfile.ApprovalStatus.APPROVED
        profile.can_audio = True
        profile.can_video = True
        profile.is_demo_teacher = True
        profile.auto_accept_calls = True
        profile.save()

        availability, _ = TeacherAvailability.objects.get_or_create(
            teacher=user,
            defaults={"status": TeacherAvailability.Status.ONLINE},
        )
        availability.status = TeacherAvailability.Status.ONLINE
        availability.last_seen = timezone.now()
        availability.save(update_fields=["status", "last_seen", "updated_at"])

        if created or profile_created:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Demo teacher CREATED → {DEMO_DISPLAY_NAME} ({DEMO_USERNAME})"
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"Demo teacher UPDATED → {DEMO_DISPLAY_NAME} ({DEMO_USERNAME})"
                )
            )
