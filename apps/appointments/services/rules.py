"""Create / update availability rules and exceptions."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from apps.appointments.exceptions import AppointmentError
from apps.appointments.models import (
    ACTIVE_APPOINTMENT_STATUSES,
    Appointment,
    AppointmentSlot,
    AvailabilityException,
    AvailabilityRule,
    ExceptionType,
    RecurrenceType,
    SessionType,
    SlotStatus,
)
from apps.appointments.services.cancellation import cancel_by_teacher
from apps.appointments.services.settings_service import get_or_create_booking_settings
from apps.appointments.services.slot_generation import generate_slots_for_teacher


def _parse_time(value) -> time:
    if isinstance(value, time):
        return value
    text = str(value or "").strip()
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    raise AppointmentError("وقت غير صالح.", code="invalid_time")


def _parse_date(value) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    text = str(value or "").strip()
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise AppointmentError("تاريخ غير صالح.", code="invalid_date") from exc


def _validate_window(start_t: time, end_t: time, duration: int, break_m: int) -> None:
    if end_t <= start_t:
        raise AppointmentError("وقت النهاية يجب أن يكون بعد البداية.", code="invalid_window")
    if duration <= 0:
        raise AppointmentError("مدة الجلسة غير صالحة.", code="invalid_duration")
    if break_m < 0:
        raise AppointmentError("وقت الاستراحة غير صالح.", code="invalid_break")
    start_m = start_t.hour * 60 + start_t.minute
    end_m = end_t.hour * 60 + end_t.minute
    if end_m - start_m < duration:
        raise AppointmentError(
            "الفترة أقصر من مدة الجلسة.",
            code="window_too_short",
        )


def _assert_no_overlapping_window(teacher, day: date, start_t: time, end_t: time) -> None:
    settings_obj = get_or_create_booking_settings(teacher)
    try:
        tz = ZoneInfo(settings_obj.timezone or "Asia/Riyadh")
    except Exception:
        tz = ZoneInfo("Asia/Riyadh")
    window_start = timezone.make_aware(datetime.combine(day, start_t), tz)
    window_end = timezone.make_aware(datetime.combine(day, end_t), tz)
    overlap = AppointmentSlot.objects.filter(
        teacher=teacher,
        status__in=[SlotStatus.AVAILABLE, SlotStatus.RESERVED],
        start_at__lt=window_end,
        end_at__gt=window_start,
    ).exists()
    if overlap:
        raise AppointmentError(
            "هذه الفترة تتداخل مع مواعيد موجودة للمعلم.",
            code="teacher_overlap",
            status=409,
        )


@transaction.atomic
def create_availability_rule(teacher, data: dict) -> AvailabilityRule:
    get_or_create_booking_settings(teacher)
    start_date = _parse_date(data.get("start_date"))
    end_date = data.get("end_date")
    end_date = _parse_date(end_date) if end_date else None
    if end_date and end_date < start_date:
        raise AppointmentError(
            "تاريخ النهاية يجب أن يكون بعد تاريخ البداية.",
            code="invalid_date_range",
        )
    start_time = _parse_time(data.get("start_time"))
    end_time = _parse_time(data.get("end_time"))
    duration = int(data.get("slot_duration_minutes") or 30)
    break_m = int(data.get("break_minutes") or 0)
    _validate_window(start_time, end_time, duration, break_m)

    recurrence_type = (data.get("recurrence_type") or RecurrenceType.NONE).strip()
    if recurrence_type not in RecurrenceType.values:
        raise AppointmentError("نوع التكرار غير صالح.", code="invalid_recurrence")

    recurrence_days = data.get("recurrence_days") or []
    if recurrence_type == RecurrenceType.WEEKLY_SELECTED:
        days = sorted({int(d) for d in recurrence_days if 1 <= int(d) <= 7})
        if not days:
            raise AppointmentError(
                "حدد يومًا واحدًا على الأقل للتكرار.",
                code="days_required",
            )
        recurrence_days = days
    else:
        recurrence_days = []

    session_types = data.get("session_types") or list(SessionType.values)
    session_types = [s for s in session_types if s in SessionType.values]
    if not session_types:
        session_types = list(SessionType.values)

    # Guard first occurrence against overlapping existing slots.
    _assert_no_overlapping_window(teacher, start_date, start_time, end_time)

    rule = AvailabilityRule.objects.create(
        teacher=teacher,
        start_date=start_date,
        end_date=end_date,
        start_time=start_time,
        end_time=end_time,
        recurrence_type=recurrence_type,
        recurrence_interval=max(int(data.get("recurrence_interval") or 1), 1),
        recurrence_days=recurrence_days,
        slot_duration_minutes=duration,
        break_minutes=max(break_m, 0),
        session_types=session_types,
        is_active=True,
        internal_notes=(data.get("internal_notes") or "")[:500],
    )
    generate_slots_for_teacher(teacher)
    return rule


def preview_availability_exception(teacher, data: dict) -> dict:
    """Return affected active bookings before applying a closing exception."""
    day = _parse_date(data.get("date"))
    exception_type = (data.get("exception_type") or "").strip()
    if exception_type not in ExceptionType.values:
        raise AppointmentError("نوع الاستثناء غير صالح.", code="invalid_exception")

    start_time = data.get("start_time")
    end_time = data.get("end_time")
    start_t = _parse_time(start_time) if start_time else None
    end_t = _parse_time(end_time) if end_time else None

    if exception_type not in {
        ExceptionType.CLOSED_DAY,
        ExceptionType.CLOSED_RANGE,
        ExceptionType.CANCEL_OCCURRENCE,
    }:
        return {"affected_count": 0, "appointments": []}

    affected = Appointment.objects.filter(
        teacher=teacher,
        status__in=ACTIVE_APPOINTMENT_STATUSES,
        slot__start_at__date=day,
    ).select_related("slot", "student")
    if start_t and end_t:
        tz = ZoneInfo(get_or_create_booking_settings(teacher).timezone or "Asia/Riyadh")
        range_start = timezone.make_aware(datetime.combine(day, start_t), tz)
        range_end = timezone.make_aware(datetime.combine(day, end_t), tz)
        affected = affected.filter(
            slot__start_at__lt=range_end,
            slot__end_at__gt=range_start,
        )
    items = list(affected[:50])
    return {
        "affected_count": affected.count(),
        "appointments": [
            {
                "id": a.id,
                "student_id": a.student_id,
                "status": a.status,
                "start_at": a.slot.start_at.isoformat(),
                "end_at": a.slot.end_at.isoformat(),
            }
            for a in items
        ],
    }


@transaction.atomic
def deactivate_availability_rule(teacher, rule_id: int, *, future_only: bool = True) -> AvailabilityRule:
    try:
        rule = AvailabilityRule.objects.select_for_update().get(pk=rule_id, teacher=teacher)
    except AvailabilityRule.DoesNotExist as exc:
        raise AppointmentError("القاعدة غير موجودة.", code="not_found", status=404) from exc

    rule.is_active = False
    if future_only:
        rule.end_date = timezone.localdate()
    rule.save(update_fields=["is_active", "end_date", "updated_at"])

    now = timezone.now()
    slots_qs = AppointmentSlot.objects.filter(
        source_rule=rule,
        status=SlotStatus.AVAILABLE,
    )
    if future_only:
        slots_qs = slots_qs.filter(start_at__gte=now)
    slots_qs.update(status=SlotStatus.CANCELLED)
    return rule


@transaction.atomic
def add_availability_exception(
    teacher,
    data: dict,
    *,
    cancel_affected_bookings: bool = False,
    cancellation_reason: str = "",
) -> AvailabilityException:
    day = _parse_date(data.get("date"))
    exception_type = (data.get("exception_type") or "").strip()
    if exception_type not in ExceptionType.values:
        raise AppointmentError("نوع الاستثناء غير صالح.", code="invalid_exception")

    start_time = data.get("start_time")
    end_time = data.get("end_time")
    start_t = _parse_time(start_time) if start_time else None
    end_t = _parse_time(end_time) if end_time else None

    if exception_type in {ExceptionType.CLOSED_RANGE, ExceptionType.ADD_SLOTS}:
        if not start_t or not end_t:
            raise AppointmentError("يجب تحديد الفترة.", code="range_required")
        if end_t <= start_t:
            raise AppointmentError("وقت النهاية يجب أن يكون بعد البداية.", code="invalid_window")

    if exception_type in {
        ExceptionType.CLOSED_DAY,
        ExceptionType.CLOSED_RANGE,
        ExceptionType.CANCEL_OCCURRENCE,
    }:
        affected = Appointment.objects.filter(
            teacher=teacher,
            status__in=ACTIVE_APPOINTMENT_STATUSES,
            slot__start_at__date=day,
        ).select_related("slot")
        if start_t and end_t:
            tz = ZoneInfo(get_or_create_booking_settings(teacher).timezone or "Asia/Riyadh")
            range_start = timezone.make_aware(datetime.combine(day, start_t), tz)
            range_end = timezone.make_aware(datetime.combine(day, end_t), tz)
            affected = affected.filter(
                slot__start_at__lt=range_end,
                slot__end_at__gt=range_start,
            )
        affected_list = list(affected)
        if affected_list and not cancel_affected_bookings:
            raise AppointmentError(
                "يوجد حجوزات مؤكدة في هذا اليوم. أكّد الإلغاء لإكمال العملية.",
                code="has_bookings",
                status=409,
            )
        for appt in affected_list:
            cancel_by_teacher(
                appt.pk,
                teacher,
                reason=cancellation_reason or (data.get("reason") or "إجازة / استثناء"),
                reopen_slot=False,
            )

        slots = AppointmentSlot.objects.filter(
            teacher=teacher,
            status=SlotStatus.AVAILABLE,
            start_at__date=day,
        )
        if start_t and end_t:
            tz = ZoneInfo(get_or_create_booking_settings(teacher).timezone or "Asia/Riyadh")
            range_start = timezone.make_aware(datetime.combine(day, start_t), tz)
            range_end = timezone.make_aware(datetime.combine(day, end_t), tz)
            slots = slots.filter(start_at__lt=range_end, end_at__gt=range_start)
        slots.update(status=SlotStatus.BLOCKED)

    exc = AvailabilityException.objects.create(
        teacher=teacher,
        date=day,
        start_time=start_t,
        end_time=end_t,
        exception_type=exception_type,
        reason=(data.get("reason") or "")[:255],
        source_rule_id=data.get("source_rule_id") or None,
    )

    if exception_type == ExceptionType.ADD_SLOTS:
        generate_slots_for_teacher(teacher)

    return exc
