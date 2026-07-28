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
    """True for standalone test-call service."""
    if getattr(call, "is_test_call", False):
        return True
    return getattr(call, "service_type", "") == CallSession.ServiceType.TEST_CALL


def is_demo_protected_call(call: CallSession) -> bool:
    """Deprecated alias: means test call session."""
    return is_test_call_session(call)


def consent_version_for_call(call: CallSession) -> str:
    if is_test_call_session(call):
        return TEST_CALL_RECORDING_CONSENT_VERSION
    return RECORDING_CONSENT_VERSION


def user_has_account_recording_consent(user, version: str) -> bool:
    """True when the account has accepted this consent policy version."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    version = (version or "").strip()
    if not version:
        return False
    if version == TEST_CALL_RECORDING_CONSENT_VERSION:
        return (
            getattr(user, "test_call_recording_consent_version", "") or ""
        ).strip() == version
    if version == RECORDING_CONSENT_VERSION:
        return (
            getattr(user, "call_recording_consent_version", "") or ""
        ).strip() == version
    return False


def save_account_recording_consent(user, version: str) -> None:
    """Persist account-level consent for the given policy version."""
    version = (version or "").strip()
    if not version:
        raise CallValidationError("نسخة الموافقة غير صالحة.")
    now = timezone.now()
    if version == TEST_CALL_RECORDING_CONSENT_VERSION:
        user.test_call_recording_consent_version = version
        user.test_call_recording_consent_at = now
        user.save(
            update_fields=[
                "test_call_recording_consent_version",
                "test_call_recording_consent_at",
            ]
        )
        return
    if version == RECORDING_CONSENT_VERSION:
        user.call_recording_consent_version = version
        user.call_recording_consent_at = now
        user.save(
            update_fields=[
                "call_recording_consent_version",
                "call_recording_consent_at",
            ]
        )
        return
    raise CallValidationError("نسخة الموافقة غير معروفة.")


def revoke_account_recording_consent(user, *, version: str | None = None) -> None:
    """Clear account-level recording consent (all or one version)."""
    version = (version or "").strip()
    updates: list[str] = []
    if not version or version == RECORDING_CONSENT_VERSION:
        user.call_recording_consent_version = ""
        user.call_recording_consent_at = None
        updates.extend(
            ["call_recording_consent_version", "call_recording_consent_at"]
        )
    if not version or version == TEST_CALL_RECORDING_CONSENT_VERSION:
        user.test_call_recording_consent_version = ""
        user.test_call_recording_consent_at = None
        updates.extend(
            [
                "test_call_recording_consent_version",
                "test_call_recording_consent_at",
            ]
        )
    if updates:
        user.save(update_fields=updates)


def account_recording_consent_payload(user) -> dict:
    """Profile/me fields for mobile skip-dialog logic."""
    real_version = (getattr(user, "call_recording_consent_version", "") or "").strip()
    test_version = (
        getattr(user, "test_call_recording_consent_version", "") or ""
    ).strip()
    return {
        "recording_consent": {
            "given": real_version == RECORDING_CONSENT_VERSION,
            "version": real_version,
            "current_version": RECORDING_CONSENT_VERSION,
            "needs_reconsent": real_version != RECORDING_CONSENT_VERSION,
            "consented_at": (
                user.call_recording_consent_at.isoformat()
                if getattr(user, "call_recording_consent_at", None)
                else None
            ),
        },
        "test_call_recording_consent": {
            "given": test_version == TEST_CALL_RECORDING_CONSENT_VERSION,
            "version": test_version,
            "current_version": TEST_CALL_RECORDING_CONSENT_VERSION,
            "needs_reconsent": test_version != TEST_CALL_RECORDING_CONSENT_VERSION,
            "consented_at": (
                user.test_call_recording_consent_at.isoformat()
                if getattr(user, "test_call_recording_consent_at", None)
                else None
            ),
        },
    }


def test_call_requires_caller_consent_only(call: CallSession) -> bool:
    return is_test_call_session(call)


def user_has_recording_consent(call: CallSession, user) -> bool:
    """True only with an explicit per-call agree row for this session.

    Account-level consent must not satisfy recording start for calls that
    show the opt-in dialog. Missing row = still waiting; decline = False.
    """
    if not _is_participant(call, user):
        return False
    version = consent_version_for_call(call)
    return CallRecordingConsent.objects.filter(
        call_session=call,
        user_id=user.id,
        consent_given=True,
        consent_version=version,
    ).exists()


def any_participant_declined_recording(call: CallSession) -> bool:
    """True when at least one participant explicitly declined (no who)."""
    version = consent_version_for_call(call)
    user_ids = [call.student_id]
    if call.teacher_id:
        user_ids.append(call.teacher_id)
    return CallRecordingConsent.objects.filter(
        call_session=call,
        user_id__in=[uid for uid in user_ids if uid],
        consent_given=False,
        consent_version=version,
    ).exists()


def both_parties_have_recording_consent(call: CallSession) -> bool:
    """Both parties must have explicit consent_given=True for this call."""
    if not call.student_id or not call.teacher_id:
        return False
    version = consent_version_for_call(call)
    student_ok = CallRecordingConsent.objects.filter(
        call_session=call,
        user_id=call.student_id,
        consent_given=True,
        consent_version=version,
    ).exists()
    teacher_ok = CallRecordingConsent.objects.filter(
        call_session=call,
        user_id=call.teacher_id,
        consent_given=True,
        consent_version=version,
    ).exists()
    return student_ok and teacher_ok


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
    consent_given: bool = True,
) -> CallRecordingConsent:
    call = CallSession.objects.select_related("student", "teacher").get(pk=call.pk)
    if call.status != CallSession.Status.ACTIVE:
        raise CallValidationError("لا يمكن تسجيل الموافقة إلا أثناء مكالمة نشطة.")
    if not _is_participant(call, user):
        raise CallValidationError("غير مصرح لك بالموافقة على هذه المكالمة.")

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

    given = bool(consent_given)
    with transaction.atomic():
        consent, created = CallRecordingConsent.objects.get_or_create(
            call_session=call,
            user=user,
            defaults={
                "consent_given": given,
                "consented_at": now,
                "consent_version": version,
                "platform": plat,
            },
        )
        if not created:
            consent.consent_given = given
            consent.consented_at = now
            consent.consent_version = version
            updates = ["consent_given", "consented_at", "consent_version"]
            if plat and not consent.platform:
                consent.platform = plat
                updates.append("platform")
            consent.save(update_fields=updates)

    # Only persist account-level consent when the user explicitly agrees.
    if given:
        save_account_recording_consent(user, version)
        # Consent alone must NEVER start Cloud Recording — wait for media-ready.
        logger.info(
            "recording_consent_ready call_id=%s user_id=%s is_test=%s "
            "(defer recording until media-ready)",
            call.id,
            user.id,
            is_test_call_session(call),
        )
        maybe_start_recording_if_consents_ready(call)
    else:
        logger.info(
            "recording_consent_declined call_id=%s user_id=%s is_test=%s",
            call.id,
            user.id,
            is_test_call_session(call),
        )
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
        # Neutral flag: do not reveal which participant declined.
        "recording_declined_by_participant": any_participant_declined_recording(
            call
        ),
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
