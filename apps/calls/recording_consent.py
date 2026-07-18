"""Call recording consent and gated cloud-recording start."""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from apps.calls.exceptions import CallValidationError
from apps.calls.models import (
    RECORDING_CONSENT_VERSION,
    CallRecording,
    CallRecordingConsent,
    CallSession,
)

logger = logging.getLogger(__name__)


def _is_participant(call: CallSession, user) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return user.id in {call.student_id, call.teacher_id}


def is_demo_protected_call(call: CallSession) -> bool:
    """True when either participant is a demo / protected demo teacher account."""
    from apps.tutoring.teacher_services import is_demo_teacher

    student = getattr(call, "student", None)
    teacher = getattr(call, "teacher", None)
    if teacher is not None and is_demo_teacher(teacher):
        return True
    if student is not None and is_demo_teacher(student):
        return True
    return False


def user_has_recording_consent(call: CallSession, user) -> bool:
    if not _is_participant(call, user):
        return False
    return CallRecordingConsent.objects.filter(
        call_session=call,
        user_id=user.id,
        consent_given=True,
        consent_version=RECORDING_CONSENT_VERSION,
    ).exists()


def both_parties_have_recording_consent(call: CallSession) -> bool:
    if not call.student_id or not call.teacher_id:
        return False
    given = set(
        CallRecordingConsent.objects.filter(
            call_session=call,
            consent_given=True,
            consent_version=RECORDING_CONSENT_VERSION,
            user_id__in=[call.student_id, call.teacher_id],
        ).values_list("user_id", flat=True)
    )
    return call.student_id in given and call.teacher_id in given


def record_call_recording_consent(
    call: CallSession,
    user,
    *,
    platform: str = "",
) -> CallRecordingConsent:
    call = CallSession.objects.select_related("student", "teacher").get(pk=call.pk)
    if is_demo_protected_call(call):
        raise CallValidationError(
            "التسجيل غير مسموح للمكالمات التجريبية.",
        )
    if call.status != CallSession.Status.ACTIVE:
        raise CallValidationError("لا يمكن تسجيل الموافقة إلا أثناء مكالمة نشطة.")
    if not _is_participant(call, user):
        raise CallValidationError("غير مصرح لك بالموافقة على هذه المكالمة.")

    now = timezone.now()
    plat = (platform or "").strip().lower()[:32]
    with transaction.atomic():
        consent, created = CallRecordingConsent.objects.get_or_create(
            call_session=call,
            user=user,
            defaults={
                "consent_given": True,
                "consented_at": now,
                "consent_version": RECORDING_CONSENT_VERSION,
                "platform": plat,
            },
        )
        if not created:
            # Idempotent: keep first server timestamp; refresh platform if empty.
            updates = []
            if not consent.consent_given:
                consent.consent_given = True
                updates.append("consent_given")
            if not consent.consented_at:
                consent.consented_at = now
                updates.append("consented_at")
            if plat and not consent.platform:
                consent.platform = plat
                updates.append("platform")
            if consent.consent_version != RECORDING_CONSENT_VERSION:
                consent.consent_version = RECORDING_CONSENT_VERSION
                updates.append("consent_version")
            if updates:
                consent.save(update_fields=updates)

    maybe_start_recording_if_consents_ready(call)
    return consent


def maybe_start_recording_if_consents_ready(call: CallSession) -> bool:
    """Start Agora cloud recording only after both parties consented."""
    call = CallSession.objects.select_related("student", "teacher").get(pk=call.pk)
    if call.status != CallSession.Status.ACTIVE:
        return False
    if is_demo_protected_call(call):
        logger.info(
            "Cloud recording blocked for demo-protected call_id=%s",
            call.id,
        )
        return False
    if not both_parties_have_recording_consent(call):
        return False

    try:
        rec = call.recording
        if rec.recording_status in {
            CallRecording.RecordingStatus.RECORDING,
            CallRecording.RecordingStatus.STARTING,
            CallRecording.RecordingStatus.STOP_REQUESTED,
            CallRecording.RecordingStatus.STOPPING,
            CallRecording.RecordingStatus.PROCESSING,
            CallRecording.RecordingStatus.COMPLETED,
        }:
            return True
    except CallRecording.DoesNotExist:
        pass

    from apps.calls.cloud_recording.service import start_cloud_recording_for_call

    try:
        start_cloud_recording_for_call(call)
        return True
    except Exception:
        logger.exception(
            "Cloud recording start after consent failed call_id=%s", call.id
        )
        return False


def recording_consent_payload(call: CallSession, viewer) -> dict:
    demo_protected = is_demo_protected_call(call)
    my_consent = False
    if viewer is not None and not demo_protected:
        my_consent = user_has_recording_consent(call, viewer)
    both = False if demo_protected else both_parties_have_recording_consent(call)
    rec_status = ""
    recording_active = False
    if not demo_protected:
        try:
            rec = call.recording
            rec_status = rec.recording_status or ""
            recording_active = rec_status == CallRecording.RecordingStatus.RECORDING
        except CallRecording.DoesNotExist:
            pass
    return {
        "recording_consent_version": RECORDING_CONSENT_VERSION,
        "recording_consent_required": not demo_protected,
        "my_recording_consent_given": my_consent,
        "both_parties_recording_consent": both,
        "recording_status": rec_status,
        "recording_active": recording_active,
        "recording_allowed": not demo_protected,
        "is_demo_call": demo_protected,
    }
