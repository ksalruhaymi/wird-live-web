from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

from apps.appointments.models import (
    ACTIVE_APPOINTMENT_STATUSES,
    Appointment,
    AppointmentSlot,
    AppointmentStatus,
    SlotStatus,
)
from apps.appointments.services.settings_service import get_or_create_booking_settings
from apps.appointments.services.slot_generation import ensure_teacher_slot_window


def _day_bounds(day, tz_name: str = "Asia/Riyadh"):
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Asia/Riyadh")
    start = timezone.make_aware(datetime.combine(day, time.min), tz)
    end = start + timedelta(days=1)
    return start, end


def available_slots_queryset(teacher, *, now=None):
    now = now or timezone.now()
    settings_obj = get_or_create_booking_settings(teacher)
    if not settings_obj.booking_enabled:
        return AppointmentSlot.objects.none()

    ensure_teacher_slot_window(teacher)
    notice = now + timedelta(minutes=settings_obj.minimum_booking_notice_minutes)
    max_end = now + timedelta(days=settings_obj.maximum_booking_window_days)
    return AppointmentSlot.objects.filter(
        teacher=teacher,
        status=SlotStatus.AVAILABLE,
        start_at__gte=notice,
        start_at__lte=max_end,
        end_at__gt=now,
    ).order_by("start_at", "id")


def nearest_available_slot(teacher):
    return available_slots_queryset(teacher).first()


def available_days(teacher, *, from_date=None, days: int = 30) -> list[str]:
    from_date = from_date or timezone.localdate()
    end = from_date + timedelta(days=max(days, 1) - 1)
    qs = available_slots_queryset(teacher).filter(
        start_at__date__gte=from_date,
        start_at__date__lte=end,
    )
    raw_dates = qs.values_list("start_at", flat=True)
    seen: list[str] = []
    for dt in raw_dates:
        d = timezone.localtime(dt).date().isoformat()
        if d not in seen:
            seen.append(d)
    return seen


def available_slots_for_day(teacher, day) -> list[AppointmentSlot]:
    settings_obj = get_or_create_booking_settings(teacher)
    start, end = _day_bounds(day, settings_obj.timezone)
    return list(
        available_slots_queryset(teacher).filter(start_at__gte=start, start_at__lt=end)
    )


def student_appointments(student, *, bucket: str = "upcoming"):
    now = timezone.now()
    qs = (
        Appointment.objects.filter(student=student)
        .select_related("slot", "teacher", "teacher__teacher_profile", "student", "call_session")
        .order_by("slot__start_at", "id")
    )
    if bucket == "today":
        local = timezone.localdate()
        return qs.filter(slot__start_at__date=local).exclude(
            status__in=[
                AppointmentStatus.CANCELLED_BY_STUDENT,
                AppointmentStatus.CANCELLED_BY_TEACHER,
                AppointmentStatus.REJECTED_BY_TEACHER,
            ]
        )
    if bucket == "upcoming":
        return qs.filter(
            status__in=ACTIVE_APPOINTMENT_STATUSES,
            slot__start_at__gte=now,
        )
    if bucket == "past":
        return qs.filter(
            status__in=[
                AppointmentStatus.COMPLETED,
                AppointmentStatus.EXPIRED,
                AppointmentStatus.NO_SHOW_STUDENT,
                AppointmentStatus.NO_SHOW_TEACHER,
            ]
        ).order_by("-slot__start_at", "-id")
    if bucket == "cancelled":
        return qs.filter(
            status__in=[
                AppointmentStatus.CANCELLED_BY_STUDENT,
                AppointmentStatus.CANCELLED_BY_TEACHER,
                AppointmentStatus.REJECTED_BY_TEACHER,
            ]
        ).order_by("-cancelled_at", "-id")
    return qs


def teacher_appointments(teacher, *, bucket: str = "upcoming"):
    now = timezone.now()
    qs = (
        Appointment.objects.filter(teacher=teacher)
        .select_related("slot", "student", "student__student_profile", "teacher", "call_session")
        .order_by("slot__start_at", "id")
    )
    today = timezone.localdate()
    if bucket == "today":
        return qs.filter(slot__start_at__date=today).exclude(
            status__in=[
                AppointmentStatus.CANCELLED_BY_STUDENT,
                AppointmentStatus.CANCELLED_BY_TEACHER,
                AppointmentStatus.REJECTED_BY_TEACHER,
            ]
        )
    if bucket == "upcoming":
        return qs.filter(
            status__in=ACTIVE_APPOINTMENT_STATUSES,
            slot__start_at__gte=now,
        ).exclude(slot__start_at__date=today)
    if bucket == "completed":
        return qs.filter(status=AppointmentStatus.COMPLETED).order_by("-slot__start_at")
    if bucket == "cancelled":
        return qs.filter(
            status__in=[
                AppointmentStatus.CANCELLED_BY_STUDENT,
                AppointmentStatus.CANCELLED_BY_TEACHER,
                AppointmentStatus.REJECTED_BY_TEACHER,
            ]
        ).order_by("-cancelled_at")
    if bucket == "missed":
        return qs.filter(
            status__in=[
                AppointmentStatus.EXPIRED,
                AppointmentStatus.NO_SHOW_STUDENT,
                AppointmentStatus.NO_SHOW_TEACHER,
            ]
        ).order_by("-slot__start_at")
    return qs


def upcoming_count_for_student(student) -> int:
    return student_appointments(student, bucket="upcoming").count()


def teacher_availability_summary(teacher) -> dict:
    settings_obj = get_or_create_booking_settings(teacher)
    nearest = nearest_available_slot(teacher) if settings_obj.booking_enabled else None
    return {
        "teacher_id": teacher.id,
        "booking_enabled": settings_obj.booking_enabled,
        "nearest_slot": (
            {
                "id": nearest.id,
                "start_at": nearest.start_at.isoformat(),
                "end_at": nearest.end_at.isoformat(),
            }
            if nearest
            else None
        ),
        "has_available_slots": nearest is not None,
    }
