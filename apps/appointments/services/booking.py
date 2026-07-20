from __future__ import annotations

from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.appointments.constants import (
    BOOKING_COST_NOTICE_AR,
    SLOT_ALREADY_BOOKED_MESSAGE,
)
from apps.appointments.exceptions import AppointmentError
from apps.appointments.models import (
    ACTIVE_APPOINTMENT_STATUSES,
    Appointment,
    AppointmentSlot,
    AppointmentStatus,
    AppointmentStatusHistory,
    SessionType,
    SlotStatus,
)
from apps.appointments.services.notifications import notify_appointment_booked
from apps.appointments.services.settings_service import get_or_create_booking_settings
from apps.appointments.services.slot_generation import ensure_teacher_slot_window
from apps.subscription.services import student_can_request_call
from identity.accounts.user_types import resolve_user_type_slug


def _record_status(
    appointment: Appointment,
    *,
    old_status: str,
    new_status: str,
    changed_by,
    note: str = "",
) -> None:
    AppointmentStatusHistory.objects.create(
        appointment=appointment,
        old_status=old_status or "",
        new_status=new_status,
        changed_by=changed_by,
        note=note[:255],
    )


def student_has_overlapping_appointment(student, start_at, end_at, *, exclude_id=None) -> bool:
    qs = Appointment.objects.filter(
        student=student,
        status__in=ACTIVE_APPOINTMENT_STATUSES,
        slot__start_at__lt=end_at,
        slot__end_at__gt=start_at,
    )
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    return qs.exists()


@transaction.atomic
def book_slot(
    *,
    student,
    slot_id: int,
    session_type: str,
    session_type_other: str = "",
    student_notes: str = "",
) -> Appointment:
    if resolve_user_type_slug(student) == "teacher":
        raise AppointmentError("المعلم لا يمكنه حجز مواعيد كطالب.", code="forbidden", status=403)

    can_call, eligibility_message = student_can_request_call(student)
    if not can_call:
        raise AppointmentError(
            eligibility_message or "يلزم اشتراك فعّال برصيد كافٍ لحجز الموعد.",
            code="subscription_required",
            status=403,
        )

    session_type = (session_type or "").strip()
    if session_type not in SessionType.values:
        raise AppointmentError("نوع الجلسة غير صالح.", code="invalid_session_type")

    other = (session_type_other or "").strip()[:120]
    if session_type == SessionType.OTHER and not other:
        raise AppointmentError(
            "يرجى كتابة وصف مختصر عند اختيار «أخرى».",
            code="other_required",
        )

    notes_raw = student_notes or ""
    if len(notes_raw) > 500:
        raise AppointmentError(
            "ملاحظات الطالب أطول من الحد المسموح (500 حرف).",
            code="notes_too_long",
        )
    notes = notes_raw.strip()[:500]

    try:
        slot = (
            AppointmentSlot.objects.select_for_update()
            .select_related("teacher")
            .get(pk=slot_id)
        )
    except AppointmentSlot.DoesNotExist as exc:
        raise AppointmentError("الموعد غير موجود.", code="slot_not_found", status=404) from exc

    teacher = slot.teacher
    from identity.accounts.demo_accounts import can_viewer_see_teacher

    if not can_viewer_see_teacher(student, teacher):
        raise AppointmentError("الموعد غير موجود.", code="slot_not_found", status=404)

    ensure_teacher_slot_window(teacher)
    settings_obj = get_or_create_booking_settings(teacher)

    if not settings_obj.booking_enabled:
        raise AppointmentError(
            "المعلم لا يستقبل حجوزات جديدة حاليًا.",
            code="booking_disabled",
            status=403,
        )

    now = timezone.now()
    if slot.end_at <= now or slot.start_at <= now:
        raise AppointmentError("لا يمكن حجز موعد في الماضي.", code="slot_in_past")

    if slot.status != SlotStatus.AVAILABLE:
        raise AppointmentError(SLOT_ALREADY_BOOKED_MESSAGE, code="slot_unavailable", status=409)

    notice = timedelta(minutes=settings_obj.minimum_booking_notice_minutes)
    if slot.start_at < now + notice:
        raise AppointmentError(
            "لا يمكن حجز هذا الموعد؛ الوقت أقرب من الحد الأدنى المسموح.",
            code="too_soon",
        )

    max_window = timedelta(days=settings_obj.maximum_booking_window_days)
    if slot.start_at > now + max_window:
        raise AppointmentError(
            "هذا الموعد خارج نافذة الحجز المسموحة.",
            code="outside_window",
        )

    allowed = settings_obj.allowed_session_types or list(SessionType.values)
    if session_type not in allowed:
        raise AppointmentError(
            "المعلم لا يقبل هذا النوع من الجلسات.",
            code="session_type_not_allowed",
        )

    if student_has_overlapping_appointment(student, slot.start_at, slot.end_at):
        raise AppointmentError(
            "لديك موعد آخر متداخل مع هذا الوقت.",
            code="student_overlap",
            status=409,
        )

    if settings_obj.max_active_bookings_per_student:
        active_count = Appointment.objects.filter(
            student=student,
            teacher=teacher,
            status__in=ACTIVE_APPOINTMENT_STATUSES,
        ).count()
        if active_count >= settings_obj.max_active_bookings_per_student:
            raise AppointmentError(
                "وصلت إلى الحد الأقصى للمواعيد القادمة مع هذا المعلم.",
                code="max_bookings",
                status=409,
            )

    # v1: always confirm immediately (approval_required reserved for later).
    status = AppointmentStatus.CONFIRMED
    confirmed_at = now

    try:
        appointment = Appointment.objects.create(
            teacher=teacher,
            student=student,
            slot=slot,
            session_type=session_type,
            session_type_other=other if session_type == SessionType.OTHER else "",
            student_notes=notes,
            status=status,
            booked_at=now,
            confirmed_at=confirmed_at,
        )
    except IntegrityError as exc:
        raise AppointmentError(
            SLOT_ALREADY_BOOKED_MESSAGE,
            code="slot_unavailable",
            status=409,
        ) from exc

    slot.status = SlotStatus.RESERVED
    slot.save(update_fields=["status", "updated_at"])

    _record_status(
        appointment,
        old_status="",
        new_status=status,
        changed_by=student,
        note="booked",
    )

    transaction.on_commit(lambda: notify_appointment_booked(appointment))
    return appointment


def booking_cost_notice() -> str:
    return BOOKING_COST_NOTICE_AR
