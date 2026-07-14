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
    """Web monitoring: only users with view_all see appointments."""
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
    return qs.none()


def get_appointment_for_user(user, pk: int) -> Appointment | None:
    return appointments_queryset_for(user).filter(pk=pk).first()


def rules_queryset_for(user):
    """Schedule rules are managed from mobile; web no longer lists them."""
    return AvailabilityRule.objects.none()


def exceptions_queryset_for(user):
    return AvailabilityException.objects.none()


def schedule_owner(user):
    """Teacher identity used for schedule mutations (always request.user)."""
    return user
