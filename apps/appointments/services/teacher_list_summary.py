"""Batch booking summaries for teacher cards (avoids N+1 from the mobile list)."""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from apps.appointments.models import AppointmentSlot, SlotStatus, TeacherBookingSettings


def booking_card_summaries_for_teachers(teacher_ids: list[int]) -> dict[int, dict]:
    """Return a compact booking summary per teacher in 2 queries total."""
    if not teacher_ids:
        return {}

    now = timezone.now()
    settings_rows = TeacherBookingSettings.objects.filter(teacher_id__in=teacher_ids)
    settings_map = {row.teacher_id: row for row in settings_rows}

    slots = (
        AppointmentSlot.objects.filter(
            teacher_id__in=teacher_ids,
            status=SlotStatus.AVAILABLE,
            start_at__gt=now,
            end_at__gt=now,
        )
        .order_by("start_at", "id")
        .only("id", "teacher_id", "start_at", "end_at", "status")
    )

    nearest: dict[int, AppointmentSlot | None] = {}
    for slot in slots:
        tid = slot.teacher_id
        if tid in nearest:
            continue
        settings = settings_map.get(tid)
        if settings is None:
            # Lazy defaults: treat as enabled with default notice.
            nearest[tid] = slot
            continue
        if not settings.booking_enabled:
            nearest[tid] = None
            continue
        notice = now + timedelta(minutes=settings.minimum_booking_notice_minutes)
        max_end = now + timedelta(days=settings.maximum_booking_window_days)
        if slot.start_at < notice or slot.start_at > max_end:
            continue
        nearest[tid] = slot

    result: dict[int, dict] = {}
    for tid in teacher_ids:
        settings = settings_map.get(tid)
        enabled = True if settings is None else bool(settings.booking_enabled)
        slot = nearest.get(tid)
        if tid not in nearest and settings is not None and not settings.booking_enabled:
            slot = None
        if not enabled:
            result[tid] = {
                "booking_enabled": False,
                "has_available_slots": False,
                "nearest_slot": None,
                "message_code": "booking_paused",
            }
            continue
        if slot is None:
            result[tid] = {
                "booking_enabled": True,
                "has_available_slots": False,
                "nearest_slot": None,
                "message_code": "no_slots",
            }
            continue
        result[tid] = {
            "booking_enabled": True,
            "has_available_slots": True,
            "nearest_slot": {
                "id": slot.id,
                "start_at": slot.start_at.isoformat(),
                "end_at": slot.end_at.isoformat(),
            },
            "message_code": "has_slot",
        }
    return result
