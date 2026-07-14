"""Month/day calendar helpers for simplified teacher & student UX."""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from apps.appointments.exceptions import AppointmentError
from apps.appointments.models import (
    ACTIVE_APPOINTMENT_STATUSES,
    Appointment,
    AppointmentSlot,
    AvailabilityRule,
    RecurrenceType,
    SessionType,
    SlotStatus,
)
from apps.appointments.services.payloads import appointment_to_payload, slot_to_payload
from apps.appointments.services.queries import (
    _day_bounds,
    available_slots_queryset,
)
from apps.appointments.services.rules import (
    _assert_no_overlapping_window,
    _parse_date,
    _parse_time,
    _validate_window,
)
from apps.appointments.services.settings_service import get_or_create_booking_settings
from apps.appointments.services.slot_generation import (
    ensure_teacher_slot_window,
    generate_slots_for_teacher,
)

ALLOWED_SLOT_DURATIONS = frozenset({15, 20, 30, 45, 60})


def _parse_month(raw: str | None) -> tuple[int, int]:
    text = (raw or "").strip()
    if not text:
        today = timezone.localdate()
        return today.year, today.month
    try:
        year_s, month_s = text.split("-", 1)
        year, month = int(year_s), int(month_s)
    except (TypeError, ValueError) as exc:
        raise AppointmentError("صيغة الشهر غير صالحة. استخدم YYYY-MM.", code="invalid_month") from exc
    if month < 1 or month > 12:
        raise AppointmentError("شهر غير صالح.", code="invalid_month")
    return year, month


def _teacher_tz_name(teacher) -> str:
    return get_or_create_booking_settings(teacher).timezone or "Asia/Riyadh"


def teacher_calendar_month(teacher, *, month: str | None = None) -> dict:
    """Aggregate available + booked counts for every day in a calendar month."""
    year, mon = _parse_month(month)
    ensure_teacher_slot_window(teacher)
    tz_name = _teacher_tz_name(teacher)
    first = date(year, mon, 1)
    last = date(year, mon, calendar.monthrange(year, mon)[1])
    start, _ = _day_bounds(first, tz_name)
    _, end = _day_bounds(last, tz_name)

    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("Asia/Riyadh")

    available_by_day: dict[str, int] = {}
    reserved_by_day: dict[str, int] = {}
    for row in AppointmentSlot.objects.filter(
        teacher=teacher,
        start_at__gte=start,
        start_at__lt=end,
        status__in=[SlotStatus.AVAILABLE, SlotStatus.RESERVED],
    ).only("start_at", "status"):
        day_key = timezone.localtime(row.start_at, tz).date().isoformat()
        if row.status == SlotStatus.AVAILABLE:
            available_by_day[day_key] = available_by_day.get(day_key, 0) + 1
        elif row.status == SlotStatus.RESERVED:
            reserved_by_day[day_key] = reserved_by_day.get(day_key, 0) + 1

    booked_by_day: dict[str, int] = {}
    for row in Appointment.objects.filter(
        teacher=teacher,
        status__in=ACTIVE_APPOINTMENT_STATUSES,
        slot__start_at__gte=start,
        slot__start_at__lt=end,
    ).select_related("slot"):
        day_key = timezone.localtime(row.slot.start_at, tz).date().isoformat()
        booked_by_day[day_key] = booked_by_day.get(day_key, 0) + 1

    days = []
    cursor = first
    while cursor <= last:
        key = cursor.isoformat()
        available_count = available_by_day.get(key, 0)
        booked_count = booked_by_day.get(key, reserved_by_day.get(key, 0))
        days.append(
            {
                "date": key,
                "available_count": available_count,
                "booked_count": booked_count,
                "has_availability": available_count > 0,
                "has_bookings": booked_count > 0,
            }
        )
        cursor += timedelta(days=1)

    settings_obj = get_or_create_booking_settings(teacher)
    return {
        "month": f"{year:04d}-{mon:02d}",
        "booking_enabled": settings_obj.booking_enabled,
        "days": days,
    }


def student_calendar_month(teacher, *, month: str | None = None) -> dict:
    """Bookable days only within the teacher's booking window for one month."""
    year, mon = _parse_month(month)
    settings_obj = get_or_create_booking_settings(teacher)
    tz_name = settings_obj.timezone or "Asia/Riyadh"
    first = date(year, mon, 1)
    last = date(year, mon, calendar.monthrange(year, mon)[1])
    message = ""
    days_out: list[dict] = []

    if not settings_obj.booking_enabled:
        message = "المعلم لا يستقبل حجوزات جديدة حاليًا"
        cursor = first
        while cursor <= last:
            days_out.append(
                {
                    "date": cursor.isoformat(),
                    "available_count": 0,
                    "booked_count": 0,
                    "has_availability": False,
                    "has_bookings": False,
                }
            )
            cursor += timedelta(days=1)
        return {
            "month": f"{year:04d}-{mon:02d}",
            "booking_enabled": False,
            "message": message,
            "days": days_out,
            "maximum_booking_window_days": settings_obj.maximum_booking_window_days,
        }

    start, _ = _day_bounds(first, tz_name)
    _, end = _day_bounds(last, tz_name)
    qs = available_slots_queryset(teacher).filter(
        start_at__gte=start,
        start_at__lt=end,
    )
    counts: dict[str, int] = {}
    for slot in qs.only("start_at"):
        key = timezone.localtime(slot.start_at, ZoneInfo(tz_name)).date().isoformat()
        counts[key] = counts.get(key, 0) + 1

    cursor = first
    today = timezone.localdate()
    while cursor <= last:
        key = cursor.isoformat()
        available_count = counts.get(key, 0) if cursor >= today else 0
        days_out.append(
            {
                "date": key,
                "available_count": available_count,
                "booked_count": 0,
                "has_availability": available_count > 0,
                "has_bookings": False,
            }
        )
        cursor += timedelta(days=1)

    if not any(d["has_availability"] for d in days_out):
        message = "لا توجد مواعيد متاحة حاليًا"

    return {
        "month": f"{year:04d}-{mon:02d}",
        "booking_enabled": True,
        "message": message,
        "days": days_out,
        "maximum_booking_window_days": settings_obj.maximum_booking_window_days,
    }


def teacher_day_schedule(teacher, day: date, *, request=None) -> dict:
    """All slots for a day (available + booked) with appointment details when present."""
    ensure_teacher_slot_window(teacher)
    tz_name = _teacher_tz_name(teacher)
    start, end = _day_bounds(day, tz_name)
    slots = list(
        AppointmentSlot.objects.filter(
            teacher=teacher,
            start_at__gte=start,
            start_at__lt=end,
            status__in=[
                SlotStatus.AVAILABLE,
                SlotStatus.RESERVED,
                SlotStatus.BLOCKED,
            ],
        ).order_by("start_at", "id")
    )
    appointments = {
        a.slot_id: a
        for a in Appointment.objects.filter(
            teacher=teacher,
            slot_id__in=[s.id for s in slots],
            status__in=ACTIVE_APPOINTMENT_STATUSES,
        ).select_related(
            "slot",
            "student",
            "student__student_profile",
            "teacher",
            "teacher__teacher_profile",
            "call_session",
        )
    }

    items = []
    for slot in slots:
        appt = appointments.get(slot.id)
        items.append(
            {
                "slot": slot_to_payload(slot),
                "is_booked": appt is not None,
                "appointment": (
                    appointment_to_payload(appt, viewer=teacher, request=request)
                    if appt
                    else None
                ),
            }
        )

    return {
        "date": day.isoformat(),
        "items": items,
        "available_count": sum(1 for s in slots if s.status == SlotStatus.AVAILABLE),
        "booked_count": sum(1 for _ in appointments.values()),
    }


@transaction.atomic
def create_availability_for_dates(teacher, data: dict) -> list[AvailabilityRule]:
    """Create single-day (non-recurring) rules for one or more dates, then generate slots once."""
    get_or_create_booking_settings(teacher)
    raw_dates = data.get("dates")
    if not raw_dates:
        if data.get("date"):
            raw_dates = [data.get("date")]
        else:
            raise AppointmentError("حدد يومًا واحدًا على الأقل.", code="dates_required")

    if not isinstance(raw_dates, (list, tuple)):
        raise AppointmentError("قائمة التواريخ غير صالحة.", code="invalid_dates")

    parsed_dates: list[date] = []
    for raw in raw_dates:
        parsed_dates.append(_parse_date(raw))
    parsed_dates = sorted(set(parsed_dates))
    if not parsed_dates:
        raise AppointmentError("حدد يومًا واحدًا على الأقل.", code="dates_required")

    today = timezone.localdate()
    for day in parsed_dates:
        if day < today:
            raise AppointmentError(
                "لا يمكن إضافة أوقات في تاريخ مضى.",
                code="past_date",
            )

    months = {(d.year, d.month) for d in parsed_dates}
    if len(months) > 1:
        raise AppointmentError(
            "اختر أيامًا من نفس الشهر فقط، أو انتقل للشهر الآخر.",
            code="mixed_months",
        )

    start_time = _parse_time(data.get("start_time"))
    end_time = _parse_time(data.get("end_time"))
    duration = int(data.get("slot_duration_minutes") or 30)
    break_m = int(data.get("break_minutes") or 0)
    if duration not in ALLOWED_SLOT_DURATIONS:
        raise AppointmentError(
            "مدة الجلسة غير مدعومة. اختر 15 أو 20 أو 30 أو 45 أو 60 دقيقة.",
            code="invalid_duration",
        )
    _validate_window(start_time, end_time, duration, break_m)

    session_types = data.get("session_types") or list(SessionType.values)
    session_types = [s for s in session_types if s in SessionType.values]
    if not session_types:
        session_types = list(SessionType.values)

    rules: list[AvailabilityRule] = []
    for day in parsed_dates:
        _assert_no_overlapping_window(teacher, day, start_time, end_time)
        rules.append(
            AvailabilityRule.objects.create(
                teacher=teacher,
                start_date=day,
                end_date=day,
                start_time=start_time,
                end_time=end_time,
                recurrence_type=RecurrenceType.NONE,
                recurrence_interval=1,
                recurrence_days=[],
                slot_duration_minutes=duration,
                break_minutes=max(break_m, 0),
                session_types=session_types,
                is_active=True,
                internal_notes=(data.get("internal_notes") or "")[:500],
            )
        )

    generate_slots_for_teacher(teacher)
    return rules


@transaction.atomic
def cancel_available_slot(teacher, slot_id: int) -> AppointmentSlot:
    try:
        slot = AppointmentSlot.objects.select_for_update().get(
            pk=slot_id, teacher=teacher
        )
    except AppointmentSlot.DoesNotExist as exc:
        raise AppointmentError("الفترة غير موجودة.", code="not_found", status=404) from exc

    if slot.status == SlotStatus.RESERVED:
        raise AppointmentError(
            "لا يمكن حذف موعد محجوز مباشرة. ألغِ الحجز أولًا.",
            code="slot_booked",
            status=409,
        )
    if slot.status != SlotStatus.AVAILABLE:
        raise AppointmentError(
            "لا يمكن حذف هذه الفترة.",
            code="slot_not_available",
            status=409,
        )
    slot.status = SlotStatus.CANCELLED
    slot.save(update_fields=["status", "updated_at"])
    return slot


@transaction.atomic
def clear_day_available_slots(teacher, day: date) -> int:
    """Cancel all unbooked available slots on a day. Does not touch reserved/booked."""
    tz_name = _teacher_tz_name(teacher)
    start, end = _day_bounds(day, tz_name)
    updated = AppointmentSlot.objects.filter(
        teacher=teacher,
        status=SlotStatus.AVAILABLE,
        start_at__gte=start,
        start_at__lt=end,
    ).update(status=SlotStatus.CANCELLED)
    return int(updated)
