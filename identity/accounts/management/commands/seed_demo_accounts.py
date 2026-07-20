"""Create or update protected demo/trial accounts (idempotent)."""

from __future__ import annotations

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.tutoring.models import StudentProfile, TeacherAvailability, TeacherProfile
from identity.accounts.demo_accounts import (
    DEMO_ROLE_ADMIN,
    DEMO_ROLE_STUDENT,
    DEMO_ROLE_TEACHER,
    DEMO_STUDENT_DISPLAY_NAME,
    DEMO_STUDENT_USERNAME,
    DEMO_SUPERVISOR_DISPLAY_NAME,
    DEMO_SUPERVISOR_USERNAME,
    DEMO_TEACHER_DISPLAY_NAME,
    DEMO_TEACHER_USERNAME,
    LEGACY_DEMO_STUDENT_USERNAMES,
    LEGACY_DEMO_SUPERVISOR_USERNAMES,
    LEGACY_DEMO_TEACHER_USERNAMES,
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
        f"{DEMO_SUPERVISOR_USERNAME}, {DEMO_STUDENT_USERNAME}, {DEMO_TEACHER_USERNAME}."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        password = os.getenv("SEED_DEMO_ACCOUNTS_PASSWORD", DEFAULT_PASSWORD)

        self._upsert_supervisor(password)
        self._upsert_student(password)
        self._upsert_teacher(password)

        self.stdout.write(self.style.SUCCESS("Demo accounts seeded."))

    def _find_demo_user(
        self,
        *,
        demo_role: str,
        username: str,
        legacy_usernames: tuple[str, ...],
    ):
        user = (
            User.objects.filter(is_demo_account=True, demo_role=demo_role)
            .order_by("id")
            .first()
        )
        if user is not None:
            return user

        legacy_q = Q(username__iexact=username)
        for legacy in legacy_usernames:
            legacy_q |= Q(username__iexact=legacy)
        return User.objects.filter(legacy_q).order_by("id").first()

    def _ensure_username(self, user, *, new_username: str) -> None:
        if user.username == new_username:
            return
        conflict = (
            User.objects.filter(username__iexact=new_username)
            .exclude(pk=user.pk)
            .exists()
        )
        if conflict:
            raise CommandError(
                f"Cannot rename demo account id={user.pk} "
                f"({user.username!r} → {new_username!r}): "
                f"username {new_username!r} already exists."
            )
        user.username = new_username

    def _upsert_supervisor(self, password: str) -> None:
        user = self._find_demo_user(
            demo_role=DEMO_ROLE_ADMIN,
            username=DEMO_SUPERVISOR_USERNAME,
            legacy_usernames=LEGACY_DEMO_SUPERVISOR_USERNAMES,
        )
        created = user is None
        if created:
            user = User(
                username=DEMO_SUPERVISOR_USERNAME,
                email="demo.supervisor@wird.local",
                full_name=DEMO_SUPERVISOR_DISPLAY_NAME,
                user_type=USER_TYPE_SUPERVISOR,
                is_staff=True,
                is_superuser=False,
                is_active=True,
                is_demo_account=True,
                demo_role=DEMO_ROLE_ADMIN,
            )
            user.set_password(password)
        else:
            self._ensure_username(user, new_username=DEMO_SUPERVISOR_USERNAME)
            user.email = "demo.supervisor@wird.local"
            user.full_name = DEMO_SUPERVISOR_DISPLAY_NAME
            user.user_type = USER_TYPE_SUPERVISOR
            user.is_staff = True
            user.is_superuser = False
            user.is_active = True
            user.is_demo_account = True
            user.demo_role = DEMO_ROLE_ADMIN
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
        user = self._find_demo_user(
            demo_role=DEMO_ROLE_STUDENT,
            username=DEMO_STUDENT_USERNAME,
            legacy_usernames=LEGACY_DEMO_STUDENT_USERNAMES,
        )
        created = user is None
        if created:
            user = User(
                username=DEMO_STUDENT_USERNAME,
                email="demo.student@wird.local",
                full_name=DEMO_STUDENT_DISPLAY_NAME,
                user_type=USER_TYPE_STUDENT,
                is_staff=False,
                is_superuser=False,
                is_active=True,
                is_demo_account=True,
                demo_role=DEMO_ROLE_STUDENT,
            )
            user.set_password(password)
        else:
            self._ensure_username(user, new_username=DEMO_STUDENT_USERNAME)
            user.email = "demo.student@wird.local"
            user.full_name = DEMO_STUDENT_DISPLAY_NAME
            user.user_type = USER_TYPE_STUDENT
            user.is_staff = False
            user.is_superuser = False
            user.is_active = True
            user.is_demo_account = True
            user.demo_role = DEMO_ROLE_STUDENT
        user.save()

        role = Role.objects.filter(slug="student").first()
        if role:
            user.roles.set([role])

        StudentProfile.objects.update_or_create(
            user=user,
            defaults={"display_name": DEMO_STUDENT_DISPLAY_NAME},
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"{'CREATED' if created else 'UPDATED'} {DEMO_STUDENT_USERNAME}"
            )
        )

    def _upsert_teacher(self, password: str) -> None:
        user = self._find_demo_user(
            demo_role=DEMO_ROLE_TEACHER,
            username=DEMO_TEACHER_USERNAME,
            legacy_usernames=LEGACY_DEMO_TEACHER_USERNAMES,
        )
        created = user is None
        if created:
            user = User(
                username=DEMO_TEACHER_USERNAME,
                email="demo.teacher@wird.local",
                full_name=DEMO_TEACHER_DISPLAY_NAME,
                user_type=USER_TYPE_TEACHER,
                is_staff=False,
                is_superuser=False,
                is_active=True,
                is_demo_account=True,
                demo_role=DEMO_ROLE_TEACHER,
            )
            user.set_password(password)
        else:
            self._ensure_username(user, new_username=DEMO_TEACHER_USERNAME)
            user.email = "demo.teacher@wird.local"
            user.full_name = DEMO_TEACHER_DISPLAY_NAME
            user.user_type = USER_TYPE_TEACHER
            user.is_staff = False
            user.is_superuser = False
            user.is_active = True
            user.is_demo_account = True
            user.demo_role = DEMO_ROLE_TEACHER
        user.save()

        role = Role.objects.filter(slug="teacher").first()
        if role:
            user.roles.set([role])

        profile, _ = TeacherProfile.objects.update_or_create(
            user=user,
            defaults={
                "display_name": DEMO_TEACHER_DISPLAY_NAME,
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
