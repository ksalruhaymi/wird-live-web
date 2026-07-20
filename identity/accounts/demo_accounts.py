"""Protected demo/trial accounts and demo-teacher visibility rules."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models import Q, QuerySet
from django.http import Http404

User = get_user_model()

DEMO_ROLE_ADMIN = User.DemoRole.ADMIN
DEMO_ROLE_STUDENT = User.DemoRole.STUDENT
DEMO_ROLE_TEACHER = User.DemoRole.TEACHER

DEMO_SUPERVISOR_USERNAME = "super"
DEMO_STUDENT_USERNAME = "student"
DEMO_TEACHER_USERNAME = "teacher"

DEMO_SUPERVISOR_DISPLAY_NAME = "مشرف - اختبار"
DEMO_STUDENT_DISPLAY_NAME = "طالب - اختبار"
DEMO_TEACHER_DISPLAY_NAME = "معلم - اختبار"

# Previous usernames kept for safe rename / seed lookup.
LEGACY_DEMO_SUPERVISOR_USERNAMES = ("demo_supervisor",)
LEGACY_DEMO_STUDENT_USERNAMES = ("demo_student",)
LEGACY_DEMO_TEACHER_USERNAMES = ("demo_teacher",)


def is_demo_account(user) -> bool:
    return bool(user is not None and getattr(user, "is_demo_account", False))


def is_demo_teacher_account(user) -> bool:
    return (
        is_demo_account(user)
        and getattr(user, "demo_role", None) == DEMO_ROLE_TEACHER
    )


def is_demo_student_account(user) -> bool:
    return (
        is_demo_account(user)
        and getattr(user, "demo_role", None) == DEMO_ROLE_STUDENT
    )


def is_demo_supervisor_account(user) -> bool:
    return (
        is_demo_account(user)
        and getattr(user, "demo_role", None) == DEMO_ROLE_ADMIN
    )


def can_viewer_see_teacher(viewer, teacher) -> bool:
    """
    Visibility for a teacher User.

    Non-demo teachers are always visible at this layer (other gates apply elsewhere).
    Demo teachers are visible only to:
      - is_superuser=True viewers
      - the protected demo student account
    """
    if teacher is None:
        return False
    if not is_demo_teacher_account(teacher):
        return True
    if viewer is None or not getattr(viewer, "is_authenticated", False):
        return False
    if getattr(viewer, "is_superuser", False):
        return True
    return is_demo_student_account(viewer)


def exclude_hidden_demo_teachers(qs: QuerySet, viewer) -> QuerySet:
    """Filter a User queryset of teachers for the given viewer."""
    if viewer is not None and (
        getattr(viewer, "is_superuser", False) or is_demo_student_account(viewer)
    ):
        return qs
    return qs.exclude(is_demo_account=True, demo_role=DEMO_ROLE_TEACHER)


def demo_teacher_visibility_q(viewer) -> Q:
    """Q object usable in teacher User filters."""
    if viewer is not None and (
        getattr(viewer, "is_superuser", False) or is_demo_student_account(viewer)
    ):
        return Q()
    return ~Q(is_demo_account=True, demo_role=DEMO_ROLE_TEACHER)


def get_visible_teacher_or_404(viewer, teacher_id: int):
    """
    Resolve a teacher by id for the viewer.

    Returns 404 when missing or when the teacher is a demo teacher the viewer
    is not allowed to see (does not leak existence).
    """
    teacher = (
        User.objects.select_related("teacher_profile", "teacher_availability")
        .filter(pk=teacher_id, teacher_profile__isnull=False)
        .first()
    )
    if teacher is None or not can_viewer_see_teacher(viewer, teacher):
        raise Http404("المعلّم غير موجود.")
    return teacher


def get_visible_teacher_or_none(viewer, teacher_id: int):
    try:
        return get_visible_teacher_or_404(viewer, teacher_id)
    except Http404:
        return None
