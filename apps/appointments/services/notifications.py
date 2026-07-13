from __future__ import annotations

import logging

from django.utils import timezone

from apps.notification.models import Notification, NotificationLevel
from apps.push.services import send_push_notification_to_user

logger = logging.getLogger(__name__)


def _display_name(user) -> str:
    full = (getattr(user, "full_name", "") or "").strip()
    if full:
        return full
    profile = getattr(user, "student_profile", None) or getattr(user, "teacher_profile", None)
    if profile and getattr(profile, "display_name", ""):
        return profile.display_name
    return user.username


def _session_type_label(code: str) -> str:
    from apps.appointments.models import SessionType

    try:
        return SessionType(code).label
    except ValueError:
        return code


def _local_when(dt) -> str:
    local = timezone.localtime(dt)
    return local.strftime("%Y-%m-%d %H:%M")


def _notify(user, *, title: str, message: str, data: dict | None = None) -> None:
    try:
        Notification.objects.create(
            user=user,
            title=title,
            message=message,
            level=NotificationLevel.INFO,
        )
    except Exception:
        logger.exception("Failed to create in-app notification for user=%s", user.pk)
    try:
        send_push_notification_to_user(user, title, message, data=data or {})
    except Exception:
        logger.exception("Failed to send FCM for user=%s", user.pk)


def notify_appointment_booked(appointment) -> None:
    student_name = _display_name(appointment.student)
    label = _session_type_label(appointment.session_type)
    when = _local_when(appointment.slot.start_at)
    title = "حجز موعد جديد"
    body = f"حجز {student_name} موعدًا لـ{label} في {when}."
    _notify(
        appointment.teacher,
        title=title,
        message=body,
        data={"type": "appointment_booked", "appointment_id": str(appointment.pk)},
    )


def notify_appointment_cancelled_by_student(appointment) -> None:
    student_name = _display_name(appointment.student)
    when = _local_when(appointment.slot.start_at)
    title = "إلغاء موعد"
    body = f"ألغى {student_name} موعد {when}."
    if appointment.cancellation_reason:
        body = f"{body} السبب: {appointment.cancellation_reason}"
    _notify(
        appointment.teacher,
        title=title,
        message=body,
        data={"type": "appointment_cancelled", "appointment_id": str(appointment.pk)},
    )


def notify_appointment_cancelled_by_teacher(appointment) -> None:
    teacher_name = _display_name(appointment.teacher)
    when = _local_when(appointment.slot.start_at)
    title = "إلغاء موعد"
    body = f"ألغى المعلم {teacher_name} موعدك في {when}."
    if appointment.cancellation_reason:
        body = f"{body} السبب: {appointment.cancellation_reason}"
    _notify(
        appointment.student,
        title=title,
        message=body,
        data={"type": "appointment_cancelled", "appointment_id": str(appointment.pk)},
    )


def notify_appointment_reminder(appointment, *, kind: str) -> None:
    label = _session_type_label(appointment.session_type)
    when = _local_when(appointment.slot.start_at)
    teacher_name = _display_name(appointment.teacher)
    student_name = _display_name(appointment.student)
    titles = {
        "24h": "تذكير بموعد غدًا",
        "1h": "تذكير: موعدك خلال ساعة",
        "10m": "تذكير: موعدك بعد 10 دقائق",
    }
    title = titles.get(kind, "تذكير بموعد")
    student_body = f"موعد {label} مع المعلم {teacher_name} في {when}."
    teacher_body = f"موعد {label} مع الطالب {student_name} في {when}."
    data = {
        "type": "appointment_reminder",
        "kind": kind,
        "appointment_id": str(appointment.pk),
    }
    _notify(appointment.student, title=title, message=student_body, data=data)
    _notify(appointment.teacher, title=title, message=teacher_body, data=data)
