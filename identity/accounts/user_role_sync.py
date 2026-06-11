"""Sync accounts_user.user_type and domain profiles from RBAC role assignments."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q

from apps.tutoring.models import StudentProfile, TeacherAvailability, TeacherProfile
from identity.accounts.user_types import (
    USER_TYPE_ADMIN,
    USER_TYPE_STUDENT,
    USER_TYPE_SUPERVISOR,
    USER_TYPE_TEACHER,
)
from identity.rbac.models import Role

User = get_user_model()

CONFLICTING_PRIMARY_ROLES_MESSAGE = (
    "لا يمكن الجمع بين دور الطالب ودور المعلم في نفس الحساب."
)

_ACTIVE_STUDENT = Q(user_type=USER_TYPE_STUDENT) | Q(roles__slug="student")
_ACTIVE_TEACHER = Q(user_type=USER_TYPE_TEACHER) | Q(roles__slug="teacher")

# Archived profiles: show only when the account is not supervisor-only / other primary type.
_LEGACY_STUDENT_PROFILE = (
    Q(student_profile__isnull=False)
    & ~Q(user_type=USER_TYPE_SUPERVISOR)
    & ~Q(user_type=USER_TYPE_TEACHER)
    & ~Q(roles__slug="teacher")
)
_LEGACY_TEACHER_PROFILE = (
    Q(teacher_profile__isnull=False)
    & ~Q(user_type=USER_TYPE_SUPERVISOR)
    & ~Q(user_type=USER_TYPE_STUDENT)
    & ~Q(roles__slug="student")
)


def teacher_users_queryset():
    """
    Dashboard teachers tab.

    Active teachers (type/role) always appear. Orphan TeacherProfile alone may
  appear for legacy rows, but not after conversion to supervisor-only (user_type=3).
    """
    return (
        User.objects.filter(_ACTIVE_TEACHER | _LEGACY_TEACHER_PROFILE)
        .distinct()
        .select_related("teacher_profile", "teacher_availability")
    )


def student_users_queryset():
    """
    Dashboard students tab.

    Active students (type/role) always appear. Orphan StudentProfile alone may
  appear for legacy rows, but not after conversion to supervisor-only (user_type=3).
    """
    return (
        User.objects.filter(_ACTIVE_STUDENT | _LEGACY_STUDENT_PROFILE)
        .distinct()
        .select_related("student_profile", "subscription_balance")
    )


def is_dashboard_student(user) -> bool:
    return student_users_queryset().filter(pk=user.pk).exists()


def is_dashboard_teacher(user) -> bool:
    return teacher_users_queryset().filter(pk=user.pk).exists()


def supervisor_users_queryset():
    """
    Dashboard supervisors tab.

    Any account with the supervisor RBAC role, including student+supervisor or
    teacher+supervisor. Also includes legacy rows with user_type=supervisor only.
    """
    return (
        User.objects.filter(
            Q(roles__slug="supervisor") | Q(user_type=USER_TYPE_SUPERVISOR)
        )
        .distinct()
        .prefetch_related("roles")
    )


def _display_name_for_user(user) -> str:
    full = (getattr(user, "full_name", None) or "").strip()
    if full:
        return full
    return user.username


def ensure_student_profile(user) -> StudentProfile:
    profile, _ = StudentProfile.objects.get_or_create(
        user=user,
        defaults={"display_name": _display_name_for_user(user)},
    )
    if not profile.display_name:
        profile.display_name = _display_name_for_user(user)
        profile.save(update_fields=["display_name", "updated_at"])
    return profile


def ensure_teacher_profile(user) -> TeacherProfile:
    profile, created = TeacherProfile.objects.get_or_create(
        user=user,
        defaults={
            "display_name": _display_name_for_user(user),
            "is_approved": False,
            "approval_status": TeacherProfile.ApprovalStatus.PENDING,
            "can_audio": True,
            "can_video": True,
        },
    )
    if not profile.display_name:
        profile.display_name = _display_name_for_user(user)
        profile.save(update_fields=["display_name", "updated_at"])
    if created:
        TeacherAvailability.objects.get_or_create(
            teacher=user,
            defaults={"status": TeacherAvailability.Status.OFFLINE},
        )
    return profile


def _resolve_user_type_from_role_slugs(role_slugs: set[str], *, is_superuser: bool) -> int | None:
    if is_superuser or "admin" in role_slugs:
        return USER_TYPE_ADMIN
    if "teacher" in role_slugs:
        return USER_TYPE_TEACHER
    if "student" in role_slugs:
        return USER_TYPE_STUDENT
    if "supervisor" in role_slugs:
        return USER_TYPE_SUPERVISOR
    return None


def sync_user_type_and_profiles(user, *, role_slugs: set[str] | None = None) -> None:
    """
    Align user_type (and optional profiles) with assigned RBAC roles.

    Does not assign roles; call after roles.set().
    Does not delete existing StudentProfile / TeacherProfile.
    """
    if role_slugs is None:
        role_slugs = set(user.roles.values_list("slug", flat=True))

    if "student" in role_slugs and "teacher" in role_slugs:
        raise ValueError(CONFLICTING_PRIMARY_ROLES_MESSAGE)

    new_type = _resolve_user_type_from_role_slugs(
        role_slugs,
        is_superuser=bool(getattr(user, "is_superuser", False)),
    )
    if new_type is None:
        return

    if user.user_type != new_type:
        user.user_type = new_type
        user.save(update_fields=["user_type"])

    if new_type == USER_TYPE_STUDENT:
        ensure_student_profile(user)
    elif new_type == USER_TYPE_TEACHER:
        ensure_teacher_profile(user)


@transaction.atomic
def apply_user_roles(user, roles: list[Role]) -> tuple[bool, str | None]:
    """
    Persist RBAC roles and sync user_type / profiles.

    Returns (success, error_message).
    """
    role_slugs = {role.slug for role in roles}

    if "student" in role_slugs and "teacher" in role_slugs:
        return False, CONFLICTING_PRIMARY_ROLES_MESSAGE

    user.roles.set(roles)
    try:
        sync_user_type_and_profiles(user, role_slugs=role_slugs)
    except ValueError as exc:
        transaction.set_rollback(True)
        return False, str(exc)
    return True, None
