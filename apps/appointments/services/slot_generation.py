"""Materialize AppointmentSlot rows from AvailabilityRule within a rolling window."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from apps.appointments.constants import SLOT_GENERATION_WINDOW_DAYS
from apps.appointments.models import (
    AppointmentSlot,
    AvailabilityException,
    AvailabilityRule,
    ExceptionType,
    RecurrenceType,
    SlotStatus,
)
from apps.appointments.services.settings_service import get_or_create_booking_settings


def _teacher_tz(teacher) -> ZoneInfo:
    settings_obj = get_or_create_booking_settings(teacher)
    try:
        return ZoneInfo(settings_obj.timezone or "Asia/Riyadh")
    except Exception:
        return ZoneInfo("Asia/Riyadh")


def _aware(dt_date: date, tm: time, tz: ZoneInfo) -> datetime:
    return timezone.make_aware(datetime.combine(dt_date, tm), tz)


def _rule_applies_on(rule: AvailabilityRule, day: date) -> bool:
    if day < rule.start_date:
        return False
    if rule.end_date and day > rule.end_date:
        return False

    rtype = rule.recurrence_type
    if rtype == RecurrenceType.NONE:
        return day == rule.start_date

    if rtype == RecurrenceType.DAILY:
        delta = (day - rule.start_date).days
        return delta >= 0 and delta % max(rule.recurrence_interval, 1) == 0

    if rtype == RecurrenceType.WEEKLY:
        if day.isoweekday() != rule.start_date.isoweekday():
            return False
        weeks = (day - rule.start_date).days // 7
        return weeks % max(rule.recurrence_interval, 1) == 0

    if rtype == RecurrenceType.WEEKLY_SELECTED:
        days = {int(d) for d in (rule.recurrence_days or [])}
        return day.isoweekday() in days

    if rtype == RecurrenceType.BIWEEKLY:
        if day.isoweekday() != rule.start_date.isoweekday():
            return False
        weeks = (day - rule.start_date).days // 7
        return weeks % 2 == 0

    if rtype == RecurrenceType.MONTHLY:
        if day.day != rule.start_date.day:
            return False
        months = (day.year - rule.start_date.year) * 12 + (
            day.month - rule.start_date.month
        )
        return months >= 0 and months % max(rule.recurrence_interval, 1) == 0

    return False


def _day_closed(exceptions: list[AvailabilityException], day: date) -> bool:
    for exc in exceptions:
        if exc.date != day:
            continue
        if exc.exception_type in {
            ExceptionType.CLOSED_DAY,
            ExceptionType.CANCEL_OCCURRENCE,
        }:
            if exc.start_time is None and exc.end_time is None:
                return True
    return False


def _range_blocked(
    exceptions: list[AvailabilityException],
    day: date,
    start_at: datetime,
    end_at: datetime,
    tz: ZoneInfo,
) -> bool:
    for exc in exceptions:
        if exc.date != day:
            continue
        if exc.exception_type not in {
            ExceptionType.CLOSED_RANGE,
            ExceptionType.CLOSED_DAY,
            ExceptionType.CANCEL_OCCURRENCE,
        }:
            continue
        if exc.start_time is None and exc.end_time is None:
            return True
        if exc.start_time is None or exc.end_time is None:
            continue
        exc_start = _aware(day, exc.start_time, tz)
        exc_end = _aware(day, exc.end_time, tz)
        if start_at < exc_end and end_at > exc_start:
            return True
    return False


def _iter_slot_windows(
    day: date,
    start_time: time,
    end_time: time,
    duration_minutes: int,
    break_minutes: int,
    tz: ZoneInfo,
) -> list[tuple[datetime, datetime]]:
    if duration_minutes <= 0:
        return []
    cursor = _aware(day, start_time, tz)
    window_end = _aware(day, end_time, tz)
    results: list[tuple[datetime, datetime]] = []
    step = timedelta(minutes=duration_minutes + max(break_minutes, 0))
    length = timedelta(minutes=duration_minutes)
    while cursor + length <= window_end:
        results.append((cursor, cursor + length))
        cursor = cursor + step
    return results


def _extra_slots_from_exceptions(
    exceptions: list[AvailabilityException],
    day: date,
    duration_minutes: int,
    break_minutes: int,
    tz: ZoneInfo,
) -> list[tuple[datetime, datetime]]:
    extras: list[tuple[datetime, datetime]] = []
    for exc in exceptions:
        if exc.date != day or exc.exception_type != ExceptionType.ADD_SLOTS:
            continue
        if exc.start_time is None or exc.end_time is None:
            continue
        extras.extend(
            _iter_slot_windows(
                day,
                exc.start_time,
                exc.end_time,
                duration_minutes,
                break_minutes,
                tz,
            )
        )
    return extras


@transaction.atomic
def generate_slots_for_teacher(
    teacher,
    *,
    window_days: int = SLOT_GENERATION_WINDOW_DAYS,
    from_date: date | None = None,
) -> dict:
    """Idempotently materialize slots for the next ``window_days`` days.

    Uses UniqueConstraint + ignore_conflicts so re-runs never duplicate rows.
    """
    get_or_create_booking_settings(teacher)
    tz = _teacher_tz(teacher)
    today = from_date or timezone.localdate()
    end_day = today + timedelta(days=max(window_days, 1) - 1)

    rules = list(
        AvailabilityRule.objects.filter(teacher=teacher, is_active=True).order_by("id")
    )
    exceptions = list(
        AvailabilityException.objects.filter(
            teacher=teacher,
            date__gte=today,
            date__lte=end_day,
        )
    )

    to_create: list[AppointmentSlot] = []
    day = today
    while day <= end_day:
        if _day_closed(exceptions, day):
            day += timedelta(days=1)
            continue

        for rule in rules:
            if not _rule_applies_on(rule, day):
                continue
            windows = _iter_slot_windows(
                day,
                rule.start_time,
                rule.end_time,
                rule.slot_duration_minutes,
                rule.break_minutes,
                tz,
            )
            for start_at, end_at in windows:
                if _range_blocked(exceptions, day, start_at, end_at, tz):
                    continue
                to_create.append(
                    AppointmentSlot(
                        teacher=teacher,
                        source_rule=rule,
                        start_at=start_at,
                        end_at=end_at,
                        status=SlotStatus.AVAILABLE,
                    )
                )

        settings_obj = get_or_create_booking_settings(teacher)
        for start_at, end_at in _extra_slots_from_exceptions(
            exceptions,
            day,
            settings_obj.default_slot_duration_minutes,
            settings_obj.default_break_minutes,
            tz,
        ):
            to_create.append(
                AppointmentSlot(
                    teacher=teacher,
                    source_rule=None,
                    start_at=start_at,
                    end_at=end_at,
                    status=SlotStatus.AVAILABLE,
                )
            )

        day += timedelta(days=1)

    created = 0
    if to_create:
        # Deduplicate within this batch first (same teacher/start/end).
        unique: dict[tuple, AppointmentSlot] = {}
        for slot in to_create:
            key = (slot.teacher_id, slot.start_at, slot.end_at)
            unique[key] = slot
        batch = list(unique.values())
        AppointmentSlot.objects.bulk_create(batch, ignore_conflicts=True)
        created = len(batch)

    # Expire past available slots.
    now = timezone.now()
    expired = AppointmentSlot.objects.filter(
        teacher=teacher,
        status=SlotStatus.AVAILABLE,
        end_at__lte=now,
    ).update(status=SlotStatus.EXPIRED)

    return {
        "teacher_id": teacher.pk,
        "candidates": created,
        "expired": expired,
        "window_start": today.isoformat(),
        "window_end": end_day.isoformat(),
    }


def ensure_teacher_slot_window(teacher, *, min_remaining_days: int = 14) -> dict | None:
    """Generate missing future slots when the teacher's horizon is short."""
    tz_now = timezone.now()
    horizon = tz_now + timedelta(days=SLOT_GENERATION_WINDOW_DAYS)
    latest = (
        AppointmentSlot.objects.filter(
            teacher=teacher,
            start_at__gte=tz_now,
            status=SlotStatus.AVAILABLE,
        )
        .order_by("-start_at")
        .values_list("start_at", flat=True)
        .first()
    )
    if latest and latest >= horizon - timedelta(days=min_remaining_days):
        return None
    return generate_slots_for_teacher(teacher)


def generate_slots_for_all_teachers(*, window_days: int = SLOT_GENERATION_WINDOW_DAYS) -> list[dict]:
    teacher_ids = (
        AvailabilityRule.objects.filter(is_active=True)
        .values_list("teacher_id", flat=True)
        .distinct()
    )
    results = []
    from django.contrib.auth import get_user_model

    User = get_user_model()
    for teacher in User.objects.filter(pk__in=teacher_ids).iterator():
        results.append(generate_slots_for_teacher(teacher, window_days=window_days))
    return results
