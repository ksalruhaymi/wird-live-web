from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.appointments.exceptions import AppointmentError
from apps.appointments.models import (
    ACTIVE_APPOINTMENT_STATUSES,
    Appointment,
    AppointmentStatus,
    AppointmentStatusHistory,
    SlotStatus,
)
from apps.appointments.services.notifications import (
    notify_appointment_cancelled_by_student,
    notify_appointment_cancelled_by_teacher,
)
from apps.appointments.services.settings_service import get_or_create_booking_settings


def _record_status(appointment, *, old_status, new_status, changed_by, note=""):
    AppointmentStatusHistory.objects.create(
        appointment=appointment,
        old_status=old_status or "",
        new_status=new_status,
        changed_by=changed_by,
        note=(note or "")[:255],
    )


@transaction.atomic
def cancel_by_student(appointment_id: int, student, *, reason: str = "") -> Appointment:
    try:
        appointment = (
            Appointment.objects.select_for_update()
            .select_related("slot", "teacher")
            .get(pk=appointment_id, student=student)
        )
    except Appointment.DoesNotExist as exc:
        raise AppointmentError("الموعد غير موجود.", code="not_found", status=404) from exc

    if appointment.status not in ACTIVE_APPOINTMENT_STATUSES:
        raise AppointmentError("لا يمكن إلغاء هذا الموعد.", code="invalid_status")

    if appointment.status == AppointmentStatus.IN_PROGRESS:
        raise AppointmentError("لا يمكن إلغاء موعد جارٍ.", code="in_progress")

    settings_obj = get_or_create_booking_settings(appointment.teacher)
    now = timezone.now()
    deadline = appointment.slot.start_at - timedelta(
        minutes=settings_obj.cancellation_deadline_minutes
    )
    if now > deadline:
        raise AppointmentError(
            "لا يمكنك إلغاء الموعد بعد انتهاء مهلة الإلغاء.",
            code="cancel_deadline",
            status=403,
        )

    old = appointment.status
    appointment.status = AppointmentStatus.CANCELLED_BY_STUDENT
    appointment.cancelled_at = now
    appointment.cancellation_reason = (reason or "").strip()[:255]
    appointment.cancelled_by = student
    appointment.save(
        update_fields=[
            "status",
            "cancelled_at",
            "cancellation_reason",
            "cancelled_by",
            "updated_at",
        ]
    )
    _record_status(
        appointment,
        old_status=old,
        new_status=appointment.status,
        changed_by=student,
        note=appointment.cancellation_reason,
    )

    slot = appointment.slot
    if slot.end_at > now and slot.status == SlotStatus.RESERVED:
        slot.status = SlotStatus.AVAILABLE
        slot.save(update_fields=["status", "updated_at"])

    transaction.on_commit(
        lambda: notify_appointment_cancelled_by_student(appointment)
    )
    return appointment


@transaction.atomic
def cancel_by_teacher(
    appointment_id: int,
    teacher,
    *,
    reason: str = "",
    reopen_slot: bool = False,
) -> Appointment:
    try:
        appointment = (
            Appointment.objects.select_for_update()
            .select_related("slot", "student")
            .get(pk=appointment_id, teacher=teacher)
        )
    except Appointment.DoesNotExist as exc:
        raise AppointmentError("الموعد غير موجود.", code="not_found", status=404) from exc

    if appointment.status not in ACTIVE_APPOINTMENT_STATUSES:
        raise AppointmentError("لا يمكن إلغاء هذا الموعد.", code="invalid_status")

    now = timezone.now()
    old = appointment.status
    appointment.status = AppointmentStatus.CANCELLED_BY_TEACHER
    appointment.cancelled_at = now
    appointment.cancellation_reason = (reason or "").strip()[:255]
    appointment.cancelled_by = teacher
    appointment.save(
        update_fields=[
            "status",
            "cancelled_at",
            "cancellation_reason",
            "cancelled_by",
            "updated_at",
        ]
    )
    _record_status(
        appointment,
        old_status=old,
        new_status=appointment.status,
        changed_by=teacher,
        note=appointment.cancellation_reason,
    )

    slot = appointment.slot
    if reopen_slot and slot.end_at > now and slot.status == SlotStatus.RESERVED:
        slot.status = SlotStatus.AVAILABLE
        slot.save(update_fields=["status", "updated_at"])
    elif slot.status == SlotStatus.RESERVED:
        slot.status = SlotStatus.CANCELLED
        slot.save(update_fields=["status", "updated_at"])

    transaction.on_commit(
        lambda: notify_appointment_cancelled_by_teacher(appointment)
    )
    return appointment


@transaction.atomic
def mark_appointment_status(
    appointment_id: int,
    actor,
    *,
    new_status: str,
    note: str = "",
) -> Appointment:
    allowed = {
        AppointmentStatus.COMPLETED,
        AppointmentStatus.NO_SHOW_STUDENT,
        AppointmentStatus.NO_SHOW_TEACHER,
        AppointmentStatus.EXPIRED,
    }
    if new_status not in allowed:
        raise AppointmentError("حالة غير مسموحة.", code="invalid_status")

    try:
        appointment = (
            Appointment.objects.select_for_update()
            .select_related("slot")
            .get(pk=appointment_id, teacher=actor)
        )
    except Appointment.DoesNotExist as exc:
        raise AppointmentError("الموعد غير موجود.", code="not_found", status=404) from exc

    if appointment.status not in {
        AppointmentStatus.CONFIRMED,
        AppointmentStatus.IN_PROGRESS,
        AppointmentStatus.EXPIRED,
    }:
        raise AppointmentError("لا يمكن تحديث حالة هذا الموعد.", code="invalid_status")

    old = appointment.status
    now = timezone.now()
    appointment.status = new_status
    if new_status == AppointmentStatus.COMPLETED:
        appointment.completed_at = now
    appointment.save(update_fields=["status", "completed_at", "updated_at"])
    _record_status(
        appointment,
        old_status=old,
        new_status=new_status,
        changed_by=actor,
        note=note,
    )
    return appointment
