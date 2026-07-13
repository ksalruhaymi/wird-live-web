from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.appointments.constants import (
    CALL_WINDOW_AFTER_START_MINUTES,
    CALL_WINDOW_BEFORE_MINUTES,
)
from apps.appointments.exceptions import AppointmentError
from apps.appointments.models import (
    Appointment,
    AppointmentStatus,
    AppointmentStatusHistory,
)
from apps.appointments.services.notifications import notify_appointment_reminder
from apps.calls.exceptions import CallProviderError, CallValidationError
from apps.calls.models import CallSession
from apps.calls.services import create_scheduled_call_session
from apps.subscription.services import student_can_request_call


def call_window_bounds(appointment: Appointment) -> tuple:
    start = appointment.slot.start_at
    opens_at = start - timedelta(minutes=CALL_WINDOW_BEFORE_MINUTES)
    closes_at = start + timedelta(minutes=CALL_WINDOW_AFTER_START_MINUTES)
    return opens_at, closes_at


def can_start_call_now(appointment: Appointment, *, now=None) -> bool:
    now = now or timezone.now()
    if appointment.status not in {
        AppointmentStatus.CONFIRMED,
        AppointmentStatus.IN_PROGRESS,
    }:
        return False
    opens_at, closes_at = call_window_bounds(appointment)
    return opens_at <= now <= closes_at


@transaction.atomic
def start_appointment_call(
    user,
    appointment_id: int,
    *,
    session_type: str = CallSession.SessionType.AUDIO,
) -> tuple[Appointment, CallSession]:
    try:
        appointment = (
            Appointment.objects.select_for_update(of=("self",))
            .select_related(
                "slot",
                "student",
                "teacher",
                "teacher__teacher_profile",
            )
            .get(pk=appointment_id)
        )
        # Nullable OneToOne — load separately (cannot FOR UPDATE outer join).
        if appointment.call_session_id:
            appointment.call_session = CallSession.objects.filter(
                pk=appointment.call_session_id
            ).first()
        else:
            appointment.call_session = None
    except Appointment.DoesNotExist as exc:
        raise AppointmentError("الموعد غير موجود.", code="not_found", status=404) from exc

    if user.id not in {appointment.student_id, appointment.teacher_id}:
        raise AppointmentError("غير مصرح.", code="forbidden", status=403)

    if not can_start_call_now(appointment):
        raise AppointmentError(
            "سيصبح زر الاتصال متاحًا قبل الموعد بعشر دقائق وحتى عشر دقائق بعد البداية.",
            code="outside_call_window",
            status=403,
        )

    session_type = (session_type or CallSession.SessionType.AUDIO).strip().lower()
    if session_type not in CallSession.SessionType.values:
        raise AppointmentError("نوع الاتصال غير صالح.", code="invalid_session_type")

    existing = appointment.call_session
    if existing and existing.status in {
        CallSession.Status.PENDING,
        CallSession.Status.ACTIVE,
    }:
        return appointment, existing

    can_call, message = student_can_request_call(appointment.student)
    if not can_call:
        raise AppointmentError(
            message or "رصيد الطالب غير كافٍ لبدء الاتصال.",
            code="subscription_required",
            status=403,
        )

    try:
        call = create_scheduled_call_session(
            student=appointment.student,
            teacher=appointment.teacher,
            session_type=session_type,
        )
    except CallValidationError as exc:
        raise AppointmentError(exc.message, code="call_validation", status=400) from exc
    except CallProviderError as exc:
        raise AppointmentError(exc.message, code="call_provider", status=503) from exc

    appointment.call_session = call
    old = appointment.status
    update_fields = ["call_session", "updated_at"]
    if appointment.status == AppointmentStatus.CONFIRMED:
        appointment.status = AppointmentStatus.IN_PROGRESS
        appointment.started_at = timezone.now()
        update_fields.extend(["status", "started_at"])
        AppointmentStatusHistory.objects.create(
            appointment=appointment,
            old_status=old,
            new_status=appointment.status,
            changed_by=user,
            note="call_started",
        )
    appointment.save(update_fields=update_fields)
    return appointment, call


def process_due_reminders(*, now=None) -> dict:
    """Send 24h / 1h / 10m reminders once each. Safe to run every few minutes."""
    now = now or timezone.now()
    sent = {"24h": 0, "1h": 0, "10m": 0}
    active = {
        AppointmentStatus.CONFIRMED,
        AppointmentStatus.PENDING_APPROVAL,
    }

    windows = [
        ("24h", "reminder_24h_sent_at", timedelta(hours=24), timedelta(hours=23, minutes=50)),
        ("1h", "reminder_1h_sent_at", timedelta(hours=1), timedelta(minutes=50)),
        ("10m", "reminder_10m_sent_at", timedelta(minutes=10), timedelta(minutes=5)),
    ]

    for kind, field, ahead_max, ahead_min in windows:
        lower = now + ahead_min
        upper = now + ahead_max
        qs = (
            Appointment.objects.filter(
                status__in=active,
                slot__start_at__gte=lower,
                slot__start_at__lte=upper,
            )
            .filter(Q(**{f"{field}__isnull": True}))
            .select_related("slot", "student", "teacher")
        )
        for appointment in qs:
            notify_appointment_reminder(appointment, kind=kind)
            setattr(appointment, field, now)
            appointment.save(update_fields=[field, "updated_at"])
            sent[kind] += 1

    return sent


def expire_missed_appointments(*, now=None) -> int:
    """Mark confirmed appointments whose call window closed without a call as expired."""
    now = now or timezone.now()
    cutoff = now - timedelta(minutes=CALL_WINDOW_AFTER_START_MINUTES)
    qs = list(
        Appointment.objects.filter(
            status=AppointmentStatus.CONFIRMED,
            call_session__isnull=True,
            slot__start_at__lt=cutoff,
        ).select_related("slot")
    )
    count = 0
    for appointment in qs:
        old = appointment.status
        appointment.status = AppointmentStatus.EXPIRED
        appointment.save(update_fields=["status", "updated_at"])
        AppointmentStatusHistory.objects.create(
            appointment=appointment,
            old_status=old,
            new_status=appointment.status,
            changed_by=None,
            note="auto_expired",
        )
        count += 1
    return count
