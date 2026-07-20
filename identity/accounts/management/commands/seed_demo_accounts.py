"""Create or update protected demo/trial accounts (idempotent)."""

from __future__ import annotations

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.tutoring.models import StudentProfile, TeacherAvailability, TeacherProfile
from identity.accounts.demo_accounts import (
    DEMO_ROLE_ADMIN,
    DEMO_ROLE_STUDENT,
    DEMO_ROLE_TEACHER,
    DEMO_STUDENT_USERNAME,
    DEMO_SUPERVISOR_USERNAME,
    DEMO_TEACHER_USERNAME,
)
from identity.accounts.user_types import (
    USER_TYPE_STUDENT,
    USER_TYPE_SUPERVISOR,
    USER_TYPE_TEACHER,
)
from identity.rbac.models import Role

User = get_user_model()

DEFAULT_PASSWORD = "WirdDemo-ChangeMe!"


class Command(BaseCommand):
    help = (
        "Create or update protected demo accounts: "
        "demo_supervisor, demo_student, demo_teacher."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        password = os.getenv("SEED_DEMO_ACCOUNTS_PASSWORD", DEFAULT_PASSWORD)

        self._upsert_supervisor(password)
        self._upsert_student(password)
        self._upsert_teacher(password)

        self.stdout.write(self.style.SUCCESS("Demo accounts seeded."))

    def _upsert_supervisor(self, password: str) -> None:
        user, created = User.objects.get_or_create(
            username=DEMO_SUPERVISOR_USERNAME,
            defaults={
                "email": "demo.supervisor@wird.local",
                "full_name": "مشرف تجريبي",
                "user_type": USER_TYPE_SUPERVISOR,
                "is_staff": True,
                "is_superuser": False,
                "is_active": True,
                "is_demo_account": True,
                "demo_role": DEMO_ROLE_ADMIN,
            },
        )
        user.email = "demo.supervisor@wird.local"
        user.full_name = "مشرف تجريبي"
        user.user_type = USER_TYPE_SUPERVISOR
        user.is_staff = True
        user.is_superuser = False
        user.is_active = True
        user.is_demo_account = True
        user.demo_role = DEMO_ROLE_ADMIN
        if created:
            user.set_password(password)
        user.save()

        role = Role.objects.filter(slug="supervisor").first()
        if role:
            user.roles.set([role])

        self.stdout.write(
            self.style.SUCCESS(
                f"{'CREATED' if created else 'UPDATED'} {DEMO_SUPERVISOR_USERNAME}"
            )
        )

    def _upsert_student(self, password: str) -> None:
        user, created = User.objects.get_or_create(
            username=DEMO_STUDENT_USERNAME,
            defaults={
                "email": "demo.student@wird.local",
                "full_name": "طالب تجريبي",
                "user_type": USER_TYPE_STUDENT,
                "is_staff": False,
                "is_superuser": False,
                "is_active": True,
                "is_demo_account": True,
                "demo_role": DEMO_ROLE_STUDENT,
            },
        )
        user.email = "demo.student@wird.local"
        user.full_name = "طالب تجريبي"
        user.user_type = USER_TYPE_STUDENT
        user.is_staff = False
        user.is_superuser = False
        user.is_active = True
        user.is_demo_account = True
        user.demo_role = DEMO_ROLE_STUDENT
        if created:
            user.set_password(password)
        user.save()

        role = Role.objects.filter(slug="student").first()
        if role:
            user.roles.set([role])

        StudentProfile.objects.update_or_create(
            user=user,
            defaults={"display_name": "طالب تجريبي"},
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"{'CREATED' if created else 'UPDATED'} {DEMO_STUDENT_USERNAME}"
            )
        )

    def _upsert_teacher(self, password: str) -> None:
        user, created = User.objects.get_or_create(
            username=DEMO_TEACHER_USERNAME,
            defaults={
                "email": "demo.teacher@wird.local",
                "full_name": "معلم تجريبي",
                "user_type": USER_TYPE_TEACHER,
                "is_staff": False,
                "is_superuser": False,
                "is_active": True,
                "is_demo_account": True,
                "demo_role": DEMO_ROLE_TEACHER,
            },
        )
        user.email = "demo.teacher@wird.local"
        user.full_name = "معلم تجريبي"
        user.user_type = USER_TYPE_TEACHER
        user.is_staff = False
        user.is_superuser = False
        user.is_active = True
        user.is_demo_account = True
        user.demo_role = DEMO_ROLE_TEACHER
        if created:
            user.set_password(password)
        user.save()

        role = Role.objects.filter(slug="teacher").first()
        if role:
            user.roles.set([role])

        profile, _ = TeacherProfile.objects.update_or_create(
            user=user,
            defaults={
                "display_name": "معلم تجريبي",
                "is_approved": True,
                "approval_status": TeacherProfile.ApprovalStatus.APPROVED,
                "approved_at": timezone.now(),
                "can_audio": True,
                "can_video": True,
                "auto_accept_calls": True,
            },
        )
        if profile.approval_status != TeacherProfile.ApprovalStatus.APPROVED:
            profile.approval_status = TeacherProfile.ApprovalStatus.APPROVED
            profile.is_approved = True
            profile.approved_at = timezone.now()
            profile.save(
                update_fields=[
                    "approval_status",
                    "is_approved",
                    "approved_at",
                    "updated_at",
                ]
            )

        TeacherAvailability.objects.get_or_create(
            teacher=user,
            defaults={"status": TeacherAvailability.Status.ONLINE},
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"{'CREATED' if created else 'UPDATED'} {DEMO_TEACHER_USERNAME}"
            )
        )
