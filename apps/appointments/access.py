"""Dashboard access helpers for appointments (IDOR-safe scoping)."""

from __future__ import annotations

from apps.appointments.models import Appointment, AvailabilityException, AvailabilityRule


def user_can_view_all_appointments(user) -> bool:
    return bool(user and user.has_permission("appointments.view_all"))


def user_can_manage_schedule(user) -> bool:
    return bool(user and user.has_permission("appointments.manage_schedule"))


def user_can_manage_bookings(user) -> bool:
    return bool(user and user.has_permission("appointments.manage_bookings"))


def user_can_override_status(user) -> bool:
    return bool(user and user.has_permission("appointments.override_status"))


def appointments_queryset_for(user):
    qs = Appointment.objects.select_related(
        "slot",
        "teacher",
        "teacher__teacher_profile",
        "student",
        "student__student_profile",
        "call_session",
    )
    if user_can_view_all_appointments(user):
        return qs
    return qs.filter(teacher=user)


def get_appointment_for_user(user, pk: int) -> Appointment | None:
    return appointments_queryset_for(user).filter(pk=pk).first()


def rules_queryset_for(user):
    qs = AvailabilityRule.objects.select_related("teacher")
    if user_can_view_all_appointments(user) and user_can_manage_schedule(user):
        # Supervisors with schedule manage still typically shouldn't edit others'
        # schedule in v1 — only teachers manage own. view_all without being teacher
        # uses empty for schedule pages unless teacher.
        pass
    return qs.filter(teacher=user)


def exceptions_queryset_for(user):
    return AvailabilityException.objects.filter(teacher=user).select_related(
        "teacher", "source_rule"
    )


def schedule_owner(user):
    """Teacher identity used for schedule mutations (always request.user)."""
    return user
