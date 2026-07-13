from __future__ import annotations

from apps.appointments.constants import (
    DEFAULT_BREAK_MINUTES,
    DEFAULT_CANCELLATION_DEADLINE_MINUTES,
    DEFAULT_MAXIMUM_BOOKING_WINDOW_DAYS,
    DEFAULT_MINIMUM_BOOKING_NOTICE_MINUTES,
    DEFAULT_SLOT_DURATION_MINUTES,
)
from apps.appointments.models import DEFAULT_ALLOWED_SESSION_TYPES, TeacherBookingSettings


def get_or_create_booking_settings(teacher) -> TeacherBookingSettings:
    settings_obj, created = TeacherBookingSettings.objects.get_or_create(
        teacher=teacher,
        defaults={
            "booking_enabled": True,
            "approval_required": False,
            "default_slot_duration_minutes": DEFAULT_SLOT_DURATION_MINUTES,
            "default_break_minutes": DEFAULT_BREAK_MINUTES,
            "minimum_booking_notice_minutes": DEFAULT_MINIMUM_BOOKING_NOTICE_MINUTES,
            "maximum_booking_window_days": DEFAULT_MAXIMUM_BOOKING_WINDOW_DAYS,
            "cancellation_deadline_minutes": DEFAULT_CANCELLATION_DEADLINE_MINUTES,
            "allowed_session_types": list(DEFAULT_ALLOWED_SESSION_TYPES),
            "timezone": "Asia/Riyadh",
        },
    )
    if created is False and not settings_obj.allowed_session_types:
        settings_obj.allowed_session_types = list(DEFAULT_ALLOWED_SESSION_TYPES)
        settings_obj.save(update_fields=["allowed_session_types", "updated_at"])
    return settings_obj


def update_booking_settings(teacher, **fields) -> TeacherBookingSettings:
    settings_obj = get_or_create_booking_settings(teacher)
    allowed = {
        "booking_enabled",
        "approval_required",
        "default_slot_duration_minutes",
        "default_break_minutes",
        "minimum_booking_notice_minutes",
        "maximum_booking_window_days",
        "cancellation_deadline_minutes",
        "max_active_bookings_per_student",
        "allowed_session_types",
        "timezone",
    }
    update_fields = []
    for key, value in fields.items():
        if key not in allowed:
            continue
        setattr(settings_obj, key, value)
        update_fields.append(key)
    if update_fields:
        update_fields.append("updated_at")
        settings_obj.save(update_fields=update_fields)
    return settings_obj
