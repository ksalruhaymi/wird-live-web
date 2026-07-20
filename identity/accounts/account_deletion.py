"""Self-serve account deletion for mobile store compliance."""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.calls.models import CallRecording, CallSession
from apps.calls.recording_storage import (
    delete_recording_object,
    delete_recording_prefix,
    object_key_for_recording,
    prefix_for_recording_objects,
)
from identity.accounts.user_types import resolve_user_type_slug

logger = logging.getLogger(__name__)
User = get_user_model()


class AccountDeletionError(Exception):
    def __init__(self, message: str, *, status: int = 400):
        self.message = message
        self.status = status
        super().__init__(message)


def _is_protected_account(user) -> bool:
    if getattr(user, "is_superuser", False):
        return True
    slug = (resolve_user_type_slug(user) or "").strip().lower()
    return slug in {"admin", "supervisor"}


def verify_account_deletion_credentials(user, *, password: str, confirmation: str) -> None:
    confirmation = (confirmation or "").strip()
    if confirmation not in {"حذف", "DELETE"}:
        raise AccountDeletionError(
            "يجب كتابة حذف لتأكيد حذف الحساب.",
            status=400,
        )
    if _is_protected_account(user):
        raise AccountDeletionError(
            "لا يمكن حذف هذا الحساب من التطبيق.",
            status=403,
        )
    if user.has_usable_password():
        if not password or not user.check_password(password):
            raise AccountDeletionError(
                "كلمة المرور غير صحيحة.",
                status=403,
            )


def _end_active_calls_for_user(user) -> None:
    from apps.calls.services import end_call_session

    qs = CallSession.objects.filter(
        status__in=[CallSession.Status.ACTIVE, CallSession.Status.ENDING, CallSession.Status.PENDING]
    ).filter(models_q_student_or_teacher(user))
    for call in qs.select_related("student", "teacher"):
        try:
            end_call_session(call, user)
        except Exception:
            logger.exception("account_delete_end_call_failed call_id=%s", call.id)
            call.status = CallSession.Status.CANCELLED
            call.ended_at = timezone.now()
            call.save(update_fields=["status", "ended_at", "updated_at"])


def models_q_student_or_teacher(user):
    from django.db.models import Q

    return Q(student_id=user.id) | Q(teacher_id=user.id)


def _collect_and_delete_user_recordings(user) -> dict:
    """Policy: deleting either participant removes that call recording + R2 files."""
    recordings = list(
        CallRecording.objects.filter(
            models_q_student_or_teacher(user)
        ).select_related("call_session")
    )
    r2_deleted = 0
    r2_failed = 0
    for rec in recordings:
        prefix = prefix_for_recording_objects(rec)
        key = object_key_for_recording(rec)
        try:
            if prefix:
                deleted, failed = delete_recording_prefix(prefix)
                r2_deleted += deleted
                r2_failed += len(failed)
            elif key:
                delete_recording_object(key)
                r2_deleted += 1
        except Exception:
            r2_failed += 1
            logger.exception(
                "account_delete_r2_failed recording_id=%s", rec.id
            )
        rec.delete()
    return {"recordings_removed": len(recordings), "r2_deleted": r2_deleted, "r2_failed": r2_failed}


def delete_user_account(user, *, password: str = "", confirmation: str = "") -> dict:
    verify_account_deletion_credentials(
        user, password=password, confirmation=confirmation
    )
    user_id = user.id
    username = user.username

    _end_active_calls_for_user(user)
    stats = _collect_and_delete_user_recordings(user)

    with transaction.atomic():
        # Remove dependent rows that would block hard delete.
        from apps.appointments.models import Appointment

        Appointment.objects.filter(
            models_q_student_or_teacher_appointment(user)
        ).delete()

        # Clear FKs pointing at user where SET_NULL is safer already handled by model.
        CallSession.objects.filter(student_id=user_id).delete()
        CallSession.objects.filter(teacher_id=user_id).update(teacher=None)

        # Profiles
        for rel in ("student_profile", "teacher_profile"):
            profile = getattr(user, rel, None)
            if profile is not None:
                profile.delete()

        user.delete()

    logger.info(
        "account_deleted user_id=%s username_len=%s recordings=%s r2_deleted=%s r2_failed=%s",
        user_id,
        len(username or ""),
        stats["recordings_removed"],
        stats["r2_deleted"],
        stats["r2_failed"],
    )
    return {"ok": True, **stats}


def hard_delete_user_account(user) -> dict:
    """
    Hard-delete a user and related call/appointment/profile data.

    Used by admin trial cleanup. Does not verify self-serve password/confirmation.
    """
    user_id = user.id
    username = user.username

    _end_active_calls_for_user(user)
    stats = _collect_and_delete_user_recordings(user)

    with transaction.atomic():
        from apps.appointments.models import Appointment

        Appointment.objects.filter(
            models_q_student_or_teacher_appointment(user)
        ).delete()

        CallSession.objects.filter(student_id=user_id).delete()
        CallSession.objects.filter(teacher_id=user_id).update(teacher=None)

        for rel in ("student_profile", "teacher_profile"):
            profile = getattr(user, rel, None)
            if profile is not None:
                profile.delete()

        user.delete()

    logger.info(
        "account_hard_deleted user_id=%s username=%s recordings=%s "
        "r2_deleted=%s r2_failed=%s",
        user_id,
        username,
        stats["recordings_removed"],
        stats["r2_deleted"],
        stats["r2_failed"],
    )
    return {"ok": True, "user_id": user_id, "username": username, **stats}


def models_q_student_or_teacher_appointment(user):
    from django.db.models import Q

    return Q(student_id=user.id) | Q(teacher_id=user.id)
