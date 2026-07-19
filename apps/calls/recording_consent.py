"""Call recording consent and gated cloud-recording start."""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from apps.calls.exceptions import CallValidationError
from apps.calls.models import (
    RECORDING_CONSENT_VERSION,
    TEST_CALL_RECORDING_CONSENT_VERSION,
    CallRecording,
    CallRecordingConsent,
    CallSession,
)

logger = logging.getLogger(__name__)


def _is_participant(call: CallSession, user) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return user.id in {call.student_id, call.teacher_id}


def is_test_call_session(call: CallSession) -> bool:
    """True for standalone test-call service (and legacy demo-teacher sessions)."""
    if getattr(call, "is_test_call", False):
        return True
    if getattr(call, "service_type", "") == CallSession.ServiceType.TEST_CALL:
        return True
    from apps.tutoring.teacher_services import is_demo_teacher

    teacher = getattr(call, "teacher", None)
    return teacher is not None and is_demo_teacher(teacher)


def is_demo_protected_call(call: CallSession) -> bool:
    """Deprecated alias: means test call session."""
    return is_test_call_session(call)


def consent_version_for_call(call: CallSession) -> str:
    if is_test_call_session(call):
        return TEST_CALL_RECORDING_CONSENT_VERSION
    return RECORDING_CONSENT_VERSION


def test_call_requires_caller_consent_only(call: CallSession) -> bool:
    return is_test_call_session(call)


def user_has_recording_consent(call: CallSession, user) -> bool:
    if not _is_participant(call, user):
        return False
    version = consent_version_for_call(call)
    return CallRecordingConsent.objects.filter(
        call_session=call,
        user_id=user.id,
        consent_given=True,
        consent_version=version,
    ).exists()


def both_parties_have_recording_consent(call: CallSession) -> bool:
    if not call.student_id or not call.teacher_id:
        return False
    version = RECORDING_CONSENT_VERSION
    given = set(
        CallRecordingConsent.objects.filter(
            call_session=call,
            consent_given=True,
            consent_version=version,
            user_id__in=[call.student_id, call.teacher_id],
        ).values_list("user_id", flat=True)
    )
    return call.student_id in given and call.teacher_id in given


def recording_consents_satisfied(call: CallSession) -> bool:
    if is_test_call_session(call):
        if not call.student_id:
            return False
        return CallRecordingConsent.objects.filter(
            call_session=call,
            user_id=call.student_id,
            consent_given=True,
            consent_version=TEST_CALL_RECORDING_CONSENT_VERSION,
        ).exists()
    return both_parties_have_recording_consent(call)


def test_call_media_ready(call: CallSession) -> bool:
    return bool(getattr(call, "participant_media_ready_at", None))


def both_parties_media_ready(call: CallSession) -> bool:
    """True when student and teacher have both joined and published audio."""
    return bool(
        getattr(call, "student_media_ready_at", None)
        and getattr(call, "teacher_media_ready_at", None)
    )


def parties_media_ready(call: CallSession) -> bool:
    if is_test_call_session(call):
        return test_call_media_ready(call)
    return both_parties_media_ready(call)


def recording_start_prerequisites_met(call: CallSession) -> bool:
    """Consent + media-ready before cloud recording may start.

    Real calls require both parties' consent and both media-ready.
    Test calls require caller consent + caller media-ready.
    """
    if not recording_consents_satisfied(call):
        return False
    return parties_media_ready(call)


def record_call_recording_consent(
    call: CallSession,
    user,
    *,
    platform: str = "",
) -> CallRecordingConsent:
    from apps.tutoring.teacher_services import is_demo_teacher

    call = CallSession.objects.select_related("student", "teacher").get(pk=call.pk)
    if call.status != CallSession.Status.ACTIVE:
        raise CallValidationError("لا يمكن تسجيل الموافقة إلا أثناء مكالمة نشطة.")
    if not _is_participant(call, user):
        raise CallValidationError("غير مصرح لك بالموافقة على هذه المكالمة.")

    if is_demo_teacher(user):
        raise CallValidationError(
            "لا تُطلب موافقة من الطرف الآلي للاتصال التجريبي.",
        )

    if is_test_call_session(call):
        if user.id != call.student_id:
            raise CallValidationError(
                "موافقة التسجيل للاتصال التجريبي مطلوبة من المستخدم الذي يبدأ التجربة فقط.",
            )
        version = TEST_CALL_RECORDING_CONSENT_VERSION
    else:
        version = RECORDING_CONSENT_VERSION

    now = timezone.now()
    plat = (platform or "").strip().lower()[:32]
    if plat == "demo_system":
        raise CallValidationError("منصة الموافقة غير صالحة.")

    with transaction.atomic():
        consent, created = CallRecordingConsent.objects.get_or_create(
            call_session=call,
            user=user,
            defaults={
                "consent_given": True,
                "consented_at": now,
                "consent_version": version,
                "platform": plat,
            },
        )
        if not created:
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
            if consent.consent_version != version:
                consent.consent_version = version
                updates.append("consent_version")
            if updates:
                consent.save(update_fields=updates)

    # Consent alone must NEVER start Cloud Recording — wait for media-ready.
    logger.info(
        "recording_consent_ready call_id=%s user_id=%s is_test=%s "
        "(defer recording until media-ready)",
        call.id,
        user.id,
        is_test_call_session(call),
    )
    # If both consents + media-ready already exist (e.g. late consent), try start.
    maybe_start_recording_if_consents_ready(call)
    return consent


def mark_participant_media_ready(
    call: CallSession,
    user,
    *,
    agora_uid: int | None = None,
) -> CallSession:
    """Mark participant media ready after Agora join + publish.

    - Test calls: student (caller) only; sets participant_media_ready_at.
    - Real calls: student or teacher; sets the matching side timestamp.
    Recording starts only when consent + media-ready prerequisites are met.
    Idempotent: repeated calls do not start a second Agora recording.
    """
    call = CallSession.objects.select_related("student", "teacher").get(pk=call.pk)
    if call.status != CallSession.Status.ACTIVE:
        raise CallValidationError("المكالمة ليست نشطة.")
    if not _is_participant(call, user):
        raise CallValidationError("غير مصرح بإرسال جاهزية الوسائط لهذه المكالمة.")
    if not user_has_recording_consent(call, user):
        raise CallValidationError("يجب الموافقة على تسجيل المكالمة أولاً.")

    is_test = is_test_call_session(call)
    if is_test and user.id != call.student_id:
        raise CallValidationError("غير مصرح بإرسال جاهزية الوسائط لهذه المكالمة.")

    uid_log = int(agora_uid) if agora_uid is not None else None
    with transaction.atomic():
        locked = (
            CallSession.objects.select_for_update(of=("self",))
            .select_related("student", "teacher")
            .get(pk=call.pk)
        )
        if locked.status != CallSession.Status.ACTIVE:
            raise CallValidationError("المكالمة ليست نشطة.")
        now = timezone.now()
        updates: list[str] = []

        if is_test:
            if locked.participant_media_ready_at is None:
                locked.participant_media_ready_at = now
                updates.append("participant_media_ready_at")
            if locked.student_media_ready_at is None:
                locked.student_media_ready_at = now
                updates.append("student_media_ready_at")
        elif user.id == locked.student_id:
            if locked.student_media_ready_at is None:
                locked.student_media_ready_at = now
                updates.append("student_media_ready_at")
        elif user.id == locked.teacher_id:
            if locked.teacher_media_ready_at is None:
                locked.teacher_media_ready_at = now
                updates.append("teacher_media_ready_at")

        if updates:
            updates.append("updated_at")
            locked.save(update_fields=updates)
            logger.info(
                "media_ready_received call_id=%s user_id=%s agora_uid=%s fields=%s",
                locked.id,
                user.id,
                uid_log,
                updates,
            )
        else:
            logger.info(
                "media_ready_idempotent call_id=%s user_id=%s agora_uid=%s",
                locked.id,
                user.id,
                uid_log,
            )
        call = locked

    started = maybe_start_recording_if_consents_ready(call)
    logger.info(
        "media_ready_recording_start call_id=%s started=%s both_ready=%s",
        call.id,
        started,
        parties_media_ready(call),
    )
    return CallSession.objects.select_related("student", "teacher").get(pk=call.pk)


def maybe_start_recording_if_consents_ready(call: CallSession) -> bool:
    """Start Agora cloud recording when consent + media-ready prerequisites are met."""
    call = CallSession.objects.select_related("student", "teacher").get(pk=call.pk)
    if call.status != CallSession.Status.ACTIVE:
        return False
    if not recording_start_prerequisites_met(call):
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
            "Cloud recording start after consent/media-ready failed call_id=%s",
            call.id,
        )
        return False


def recording_consent_payload(call: CallSession, viewer) -> dict:
    is_test = is_test_call_session(call)
    version = consent_version_for_call(call)
    my_consent = False
    if viewer is not None:
        my_consent = user_has_recording_consent(call, viewer)
    consent_ok = recording_consents_satisfied(call)
    media_ready = parties_media_ready(call)
    rec_status = ""
    recording_active = False
    try:
        rec = call.recording
        rec_status = rec.recording_status or ""
        recording_active = rec_status == CallRecording.RecordingStatus.RECORDING
    except CallRecording.DoesNotExist:
        pass

    return {
        "recording_consent_version": version,
        "recording_consent_required": True,
        "my_recording_consent_given": my_consent,
        "both_parties_recording_consent": consent_ok,
        "consent_ready": consent_ok,
        "participant_media_ready": media_ready,
        "student_media_ready": bool(getattr(call, "student_media_ready_at", None)),
        "teacher_media_ready": bool(getattr(call, "teacher_media_ready_at", None)),
        "recording_status": rec_status,
        "recording_active": recording_active,
        "recording_allowed": True,
        "is_demo_call": is_test,
        "is_test_call": is_test,
        "test_call_caller_consent_only": is_test,
    }
