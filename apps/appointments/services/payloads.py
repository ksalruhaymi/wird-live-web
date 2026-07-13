from __future__ import annotations

from django.utils import timezone

from apps.appointments.constants import BOOKING_COST_NOTICE_AR
from apps.appointments.models import SessionType
from apps.appointments.services.call_link import call_window_bounds, can_start_call_now
from apps.calls.services import call_to_payload, student_display_name
from apps.tutoring.teacher_services import teacher_display_name
from identity.accounts.auth.profile_service import _resolve_profile_image_url


def settings_to_payload(settings_obj) -> dict:
    return {
        "teacher_id": settings_obj.teacher_id,
        "booking_enabled": settings_obj.booking_enabled,
        "approval_required": settings_obj.approval_required,
        "default_slot_duration_minutes": settings_obj.default_slot_duration_minutes,
        "default_break_minutes": settings_obj.default_break_minutes,
        "minimum_booking_notice_minutes": settings_obj.minimum_booking_notice_minutes,
        "maximum_booking_window_days": settings_obj.maximum_booking_window_days,
        "cancellation_deadline_minutes": settings_obj.cancellation_deadline_minutes,
        "max_active_bookings_per_student": settings_obj.max_active_bookings_per_student,
        "allowed_session_types": settings_obj.allowed_session_types or [],
        "timezone": settings_obj.timezone,
        "booking_cost_notice": BOOKING_COST_NOTICE_AR,
    }


def rule_to_payload(rule) -> dict:
    return {
        "id": rule.id,
        "start_date": rule.start_date.isoformat(),
        "end_date": rule.end_date.isoformat() if rule.end_date else None,
        "start_time": rule.start_time.strftime("%H:%M"),
        "end_time": rule.end_time.strftime("%H:%M"),
        "recurrence_type": rule.recurrence_type,
        "recurrence_interval": rule.recurrence_interval,
        "recurrence_days": rule.recurrence_days or [],
        "slot_duration_minutes": rule.slot_duration_minutes,
        "break_minutes": rule.break_minutes,
        "session_types": rule.session_types or [],
        "is_active": rule.is_active,
        "internal_notes": rule.internal_notes,
    }


def slot_to_payload(slot) -> dict:
    duration = int((slot.end_at - slot.start_at).total_seconds() // 60)
    return {
        "id": slot.id,
        "teacher_id": slot.teacher_id,
        "start_at": slot.start_at.isoformat(),
        "end_at": slot.end_at.isoformat(),
        "status": slot.status,
        "duration_minutes": duration,
        "source_rule_id": slot.source_rule_id,
    }


def appointment_to_payload(appointment, *, viewer=None, request=None) -> dict:
    slot = appointment.slot
    teacher = appointment.teacher
    student = appointment.student
    opens_at, closes_at = call_window_bounds(appointment)
    payload = {
        "id": appointment.id,
        "status": appointment.status,
        "session_type": appointment.session_type,
        "session_type_label": SessionType(appointment.session_type).label
        if appointment.session_type in SessionType.values
        else appointment.session_type,
        "session_type_other": appointment.session_type_other,
        "student_notes": appointment.student_notes,
        "teacher_notes": appointment.teacher_notes,
        "booked_at": appointment.booked_at.isoformat() if appointment.booked_at else None,
        "confirmed_at": appointment.confirmed_at.isoformat()
        if appointment.confirmed_at
        else None,
        "cancelled_at": appointment.cancelled_at.isoformat()
        if appointment.cancelled_at
        else None,
        "cancellation_reason": appointment.cancellation_reason,
        "started_at": appointment.started_at.isoformat() if appointment.started_at else None,
        "completed_at": appointment.completed_at.isoformat()
        if appointment.completed_at
        else None,
        "slot": slot_to_payload(slot),
        "teacher": {
            "id": teacher.id,
            "name": teacher_display_name(teacher),
            "profile_image_url": _resolve_profile_image_url(teacher, request) or "",
        },
        "student": {
            "id": student.id,
            "name": student_display_name(student),
            "profile_image_url": _resolve_profile_image_url(student, request) or "",
        },
        "call_window": {
            "opens_at": opens_at.isoformat(),
            "closes_at": closes_at.isoformat(),
            "can_start_now": can_start_call_now(appointment),
        },
        "call_session_id": appointment.call_session_id,
        "booking_cost_notice": BOOKING_COST_NOTICE_AR,
    }
    if appointment.call_session_id and appointment.call_session:
        payload["call"] = call_to_payload(appointment.call_session, viewer=viewer, request=request)
    return payload


def session_types_payload() -> list[dict]:
    return [{"code": c.value, "label": c.label} for c in SessionType]
