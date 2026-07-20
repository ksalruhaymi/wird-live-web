from django.conf import settings
from django.utils import timezone

from datetime import timedelta

from apps.tutoring.teacher_services import (
    DEMO_CALL_MAX_SECONDS,
    DEMO_CALL_MESSAGE,
    get_pending_teacher_for_interview,
    get_teacher_user,
    mark_teacher_busy,
    mark_teacher_online,
    teacher_display_name,
    validate_teacher_for_call,
)
from apps.subscription.services import student_can_request_call
from identity.accounts.auth.profile_service import _resolve_profile_image_url
from identity.accounts.user_types import resolve_user_type_slug

from .exceptions import CallProviderError, CallValidationError
from .models import CallRecording, CallSession
from .token_builder import (
    assign_channel_name,
    build_token_for_uid,
    ensure_agora_provider,
    provider_name_for_new_call,
    token_expiry_iso,
    uses_agora_rtc,
)

TEST_CALL_LIFETIME_LIMIT = 3
TEST_CALL_LIFETIME_LIMIT_MESSAGE = "لقد استخدمت الحد الأقصى للاتصالات التجريبية."


def student_display_name(user) -> str:
    profile = getattr(user, "student_profile", None)
    if profile and profile.display_name:
        return profile.display_name
    full = (getattr(user, "full_name", "") or "").strip()
    return full or user.username


def _can_view_call(call: CallSession, user) -> bool:
    return user.id in {call.student_id, call.teacher_id}


def _is_interview_caller(user) -> bool:
    """Admin/supervisor calling a pending teacher for interview (no subscription)."""
    slug = resolve_user_type_slug(user)
    if slug not in {"admin", "supervisor"}:
        return False
    return user.has_permission("management.teachers.view")


def call_to_payload(call: CallSession, viewer=None, request=None) -> dict:
    ensure_agora_provider(call)

    app_id = ""
    if uses_agora_rtc(call):
        app_id = (getattr(settings, "AGORA_APP_ID", "") or "").strip()

    teacher_name = ""
    if call.teacher_id and call.teacher:
        teacher_name = teacher_display_name(call.teacher)

    student_name = ""
    student_profile_image_url = ""
    if call.student:
        student_name = student_display_name(call.student)
        student_profile_image_url = (
            _resolve_profile_image_url(call.student, request) or ""
        )

    teacher_profile_image_url = ""
    if call.teacher_id and call.teacher:
        teacher_profile_image_url = (
            _resolve_profile_image_url(call.teacher, request) or ""
        )

    payload = {
        "id": call.id,
        "session_type": call.session_type,
        "service_type": getattr(call, "service_type", "") or "",
        "provider": call.provider,
        "is_interview_call": bool(getattr(call, "is_interview_call", False)),
        "is_test_call": bool(getattr(call, "is_test_call", False)),
        "app_id": app_id,
        "channel_name": call.channel_name or "",
        "room_name": call.room_name or "",
        "token": "",
        "uid": call.student_id,
        "teacher_id": call.teacher_id,
        "teacher_name": teacher_name,
        "teacher_profile_image_url": teacher_profile_image_url,
        "student_name": student_name,
        "student_profile_image_url": student_profile_image_url,
        "status": call.status,
        "created_at": call.created_at.isoformat() if call.created_at else None,
        "started_at": call.started_at.isoformat() if call.started_at else None,
        "ended_at": call.ended_at.isoformat() if call.ended_at else None,
    }

    from apps.calls.recording_consent import is_test_call_session

    test_call = is_test_call_session(call)
    payload["is_demo_call"] = test_call
    payload["is_test_call"] = test_call
    if test_call:
        payload["demo_message"] = DEMO_CALL_MESSAGE
        payload["demo_max_seconds"] = DEMO_CALL_MAX_SECONDS
        payload["max_duration_seconds"] = DEMO_CALL_MAX_SECONDS
        # Countdown anchors on media-ready (after join/publish + recording start),
        # not session created_at / consent / activation alone.
        timer_anchor = getattr(call, "participant_media_ready_at", None)
        if timer_anchor:
            payload["timer_started_at"] = timer_anchor.isoformat()
            expires = timer_anchor + timedelta(seconds=DEMO_CALL_MAX_SECONDS)
            payload["expires_at"] = expires.isoformat()
        payload["teacher_name"] = "اتصال تجريبي"
        payload["teacher_profile_image_url"] = ""
        payload["participant_media_ready"] = bool(timer_anchor)

    if (
        viewer is not None
        and call.status == CallSession.Status.ACTIVE
        and _can_view_call(call, viewer)
    ):
        payload["uid"] = viewer.id
        payload["token"] = build_token_for_uid(call, viewer.id)
        if uses_agora_rtc(call):
            payload["token_expires_at"] = token_expiry_iso()

    from apps.calls.recording_consent import recording_consent_payload

    payload.update(recording_consent_payload(call, viewer))
    return payload


def _activate_call_session(call: CallSession) -> CallSession:
    """Mark call active and prepare provider.

    Cloud recording does NOT start here. It starts only after consent policy
    is satisfied (both parties for real calls; human caller only for test calls).
    """
    now = timezone.now()
    call.status = CallSession.Status.ACTIVE
    call.started_at = call.started_at or now
    if not call.channel_name:
        assign_channel_name(call)
    ensure_agora_provider(call)
    call.save(update_fields=["status", "started_at", "updated_at"])
    return call


def create_scheduled_call_session(
    *,
    student,
    teacher,
    session_type: str,
) -> CallSession:
    """Create an immediately active call for a booked appointment.

    Skips live presence checks (online/busy). Minutes are still charged via the
    normal end-call path when the session ends.
    """
    if session_type not in CallSession.SessionType.values:
        raise CallValidationError("نوع الاتصال غير صالح.")

    profile = getattr(teacher, "teacher_profile", None)
    if profile is None:
        raise CallValidationError("المعلّم غير موجود.")
    if session_type == CallSession.SessionType.AUDIO and not profile.can_audio:
        raise CallValidationError("هذا المعلّم لا يدعم الاتصال الصوتي.")
    if session_type == CallSession.SessionType.VIDEO and not profile.can_video:
        raise CallValidationError("هذا المعلّم لا يدعم الاتصال المرئي.")

    call = CallSession.objects.create(
        student=student,
        teacher=teacher,
        session_type=session_type,
        provider=provider_name_for_new_call(),
        status=CallSession.Status.PENDING,
        is_interview_call=False,
    )
    assign_channel_name(call)
    mark_teacher_busy(teacher)
    return _activate_call_session(call)


def request_call_session(
    user,
    *,
    session_type: str,
    teacher_id: int,
) -> CallSession:
    if resolve_user_type_slug(user) == "teacher":
        raise CallValidationError("المعلّم لا يمكنه طلب اتصال بمعلّم آخر.")

    if not teacher_id:
        raise CallValidationError("يجب اختيار معلّم.")

    interview_call = _is_interview_caller(user)
    if interview_call:
        teacher = get_pending_teacher_for_interview(teacher_id)
        if teacher is None:
            raise CallValidationError("المعلّم غير موجود أو ليس بانتظار المراجعة.")
    else:
        caller_slug = resolve_user_type_slug(user)
        if caller_slug not in {"student", "admin"}:
            raise CallValidationError("هذا الإجراء للطلاب فقط.")
        teacher = get_teacher_user(teacher_id)
        if teacher is None:
            raise CallValidationError("المعلّم غير موجود أو غير معتمد.")

    if not interview_call:
        can_call, eligibility_message = student_can_request_call(user)
        if not can_call:
            raise CallValidationError(eligibility_message)

    validation_error = validate_teacher_for_call(
        teacher,
        session_type=session_type,
        interview_call=interview_call,
    )
    if validation_error:
        raise CallValidationError(validation_error)

    call = CallSession.objects.create(
        student=user,
        teacher=teacher,
        session_type=session_type,
        provider=provider_name_for_new_call(),
        status=CallSession.Status.PENDING,
        is_interview_call=bool(interview_call),
        is_test_call=False,
    )
    assign_channel_name(call)
    mark_teacher_busy(teacher)

    return call


def counted_test_calls_for_user(user) -> int:
    """Test calls that started for real and created a recording row.

    Sessions that never reached recording creation (setup failure, cancel
    before media/recording) do not consume the lifetime quota.
    """
    return (
        CallSession.objects.filter(
            student=user,
            is_test_call=True,
            recording__isnull=False,
        )
        .distinct()
        .count()
    )


def start_test_call_session(user) -> CallSession:
    """Start a 60s standalone test-call service. No peer User/Teacher."""
    from apps.calls.models import TEST_CALL_MAX_SECONDS

    # Lifetime quota: only sessions that created a recording count.
    if counted_test_calls_for_user(user) >= TEST_CALL_LIFETIME_LIMIT:
        raise CallValidationError(TEST_CALL_LIFETIME_LIMIT_MESSAGE)

    # Block concurrent active/pending test calls for this user.
    active_exists = CallSession.objects.filter(
        student=user,
        is_test_call=True,
        status__in=[
            CallSession.Status.PENDING,
            CallSession.Status.ACTIVE,
            CallSession.Status.ENDING,
        ],
    ).exists()
    if active_exists:
        raise CallValidationError(
            "لديك اتصال تجريبي نشط بالفعل. أنهِه قبل بدء تجربة جديدة.",
        )

    # Soft rate limit: max 5 test calls per hour.
    hour_ago = timezone.now() - timedelta(hours=1)
    recent_count = CallSession.objects.filter(
        student=user,
        is_test_call=True,
        created_at__gte=hour_ago,
    ).count()
    if recent_count >= 5:
        raise CallValidationError(
            "وصلت إلى الحد الأقصى للاتصالات التجريبية مؤقتًا. حاول لاحقًا.",
        )

    _ = TEST_CALL_MAX_SECONDS  # documented max; enforced via DEMO_CALL_MAX_SECONDS
    call = CallSession.objects.create(
        student=user,
        teacher=None,
        session_type=CallSession.SessionType.AUDIO,
        provider=provider_name_for_new_call(),
        status=CallSession.Status.PENDING,
        is_interview_call=False,
        is_test_call=True,
        service_type=CallSession.ServiceType.TEST_CALL,
    )
    assign_channel_name(call)
    # No peer teacher — activate immediately for the independent service.
    return _activate_call_session(call)


def list_incoming_calls(teacher_user) -> list[CallSession]:
    return list(
        CallSession.objects.filter(
            teacher=teacher_user,
            status__in=[
                CallSession.Status.PENDING,
                CallSession.Status.ACTIVE,
            ],
        )
        .select_related("student", "teacher")
        .order_by("-created_at", "-id")
    )


def _demo_call_time_limit_reached(call: CallSession) -> bool:
    if call.status != CallSession.Status.ACTIVE:
        return False
    from apps.calls.recording_consent import is_test_call_session

    if not is_test_call_session(call):
        return False
    # Do not auto-end on activation age alone — wait until media-ready timer starts.
    anchor = getattr(call, "participant_media_ready_at", None)
    if not anchor:
        return False
    return timezone.now() >= anchor + timedelta(seconds=DEMO_CALL_MAX_SECONDS)


def maybe_auto_end_demo_call(call: CallSession, user) -> CallSession:
    if not _demo_call_time_limit_reached(call):
        return call
    ended, _ = end_call_session(call, user)
    return ended or call


def get_call_for_user(call_id: int, user) -> tuple[CallSession | None, str | None]:
    try:
        call = CallSession.objects.select_related("student", "teacher").get(pk=call_id)
    except CallSession.DoesNotExist:
        return None, "المكالمة غير موجودة."
    if not _can_view_call(call, user):
        return None, "غير مصرح بعرض هذه المكالمة."
    call = maybe_auto_end_demo_call(call, user)
    return call, None


def accept_call_session(call: CallSession, teacher_user) -> tuple[CallSession | None, str | None]:
    """Accept a pending call atomically.

    Idempotent when the same teacher re-accepts an already-active call.
    """
    from django.db import transaction

    if resolve_user_type_slug(teacher_user) != "teacher":
        return None, "هذا الإجراء للمعلّمين فقط."
    if call.teacher_id != teacher_user.id:
        return None, "غير مصرح بقبول هذه المكالمة."

    with transaction.atomic():
        locked = (
            CallSession.objects.select_for_update(of=("self",))
            .select_related("student", "teacher")
            .get(pk=call.pk)
        )
        if locked.teacher_id != teacher_user.id:
            return None, "غير مصرح بقبول هذه المكالمة."
        if locked.status == CallSession.Status.ACTIVE:
            # Idempotent re-accept after a successful accept.
            return locked, None
        if locked.status != CallSession.Status.PENDING:
            return None, "المكالمة ليست بانتظار القبول."
        return _activate_call_session(locked), None


def reject_call_session(call: CallSession, teacher_user) -> tuple[CallSession | None, str | None]:
    from django.db import transaction

    if call.teacher_id != teacher_user.id:
        return None, "غير مصرح برفض هذه المكالمة."

    with transaction.atomic():
        locked = (
            CallSession.objects.select_for_update(of=("self",))
            .select_related("student", "teacher")
            .get(pk=call.pk)
        )
        if locked.teacher_id != teacher_user.id:
            return None, "غير مصرح برفض هذه المكالمة."
        if locked.status != CallSession.Status.PENDING:
            return None, "لا يمكن رفض هذه المكالمة."

        locked.status = CallSession.Status.REJECTED
        locked.ended_at = timezone.now()
        locked.save(update_fields=["status", "ended_at", "updated_at"])
        call = locked

    if call.teacher_id:
        mark_teacher_online(call.teacher)
    return call, None


def cancel_pending_call(call: CallSession, student_user) -> tuple[CallSession | None, str | None]:
    from django.db import transaction

    if call.student_id != student_user.id:
        return None, "غير مصرح بإلغاء هذه المكالمة."

    with transaction.atomic():
        locked = (
            CallSession.objects.select_for_update(of=("self",))
            .select_related("student", "teacher")
            .get(pk=call.pk)
        )
        if locked.student_id != student_user.id:
            return None, "غير مصرح بإلغاء هذه المكالمة."
        if locked.status != CallSession.Status.PENDING:
            return None, "لا يمكن إلغاء هذه المكالمة."

        locked.status = CallSession.Status.MISSED
        locked.ended_at = timezone.now()
        locked.save(update_fields=["status", "ended_at", "updated_at"])
        call = locked

    if call.teacher_id:
        mark_teacher_online(call.teacher)
    return call, None


def _call_had_media_ready(call: CallSession) -> bool:
    return bool(
        getattr(call, "student_media_ready_at", None)
        or getattr(call, "teacher_media_ready_at", None)
        or getattr(call, "participant_media_ready_at", None)
    )


_SETUP_FAILURE_REASONS = frozenset(
    {
        "setup_failed",
        "microphone_permission_failed",
        "connection_failed",
        "setup_timeout",
    }
)


def end_call_session(
    call: CallSession,
    user,
    *,
    end_reason: str | None = None,
) -> tuple[CallSession | None, str | None]:
    """End a call quickly and enqueue recording stop asynchronously.

    Idempotent: repeated end requests return the terminal call without
    re-running billing or blocking on Agora.

    Calls that never reached media-ready are marked FAILED (setup failure)
    so they are not treated as successful completed sessions.
    """
    if not _can_view_call(call, user):
        return None, "غير مصرح بإنهاء هذه المكالمة."

    from django.db import transaction

    now = timezone.now()
    reason = (end_reason or "").strip()[:64]
    with transaction.atomic():
        locked = (
            CallSession.objects.select_for_update(of=("self",))
            .select_related("student", "teacher")
            .get(pk=call.pk)
        )
        if locked.status in CallSession.TERMINAL_STATUSES:
            return locked, None

        had_media = _call_had_media_ready(locked)
        setup_failure = (not had_media) or (reason in _SETUP_FAILURE_REASONS)
        if setup_failure:
            locked.status = CallSession.Status.FAILED
            locked.end_reason = reason or "setup_failed"
        else:
            locked.status = CallSession.Status.ENDED
            locked.end_reason = reason or locked.end_reason or "user_end"
        locked.end_requested_at = locked.end_requested_at or now
        locked.ended_at = locked.ended_at or now
        locked.finalized_at = now
        locked.save(
            update_fields=[
                "status",
                "end_requested_at",
                "ended_at",
                "finalized_at",
                "end_reason",
                "updated_at",
            ]
        )
        call = locked

    if call.teacher_id:
        mark_teacher_online(call.teacher)

    recording_pending = False
    if call.status == CallSession.Status.FAILED:
        _mark_setup_failure_recording(call)
        call._recording_pending = False  # type: ignore[attr-defined]
        return call, None

    # Mark recording stop requested in DB, then enqueue Celery (no Agora HTTP here).
    # If enqueue fails, status stays stop_requested for periodic reconcile.
    try:
        from apps.calls.cloud_recording.service import request_stop_cloud_recording
        from apps.calls.tasks import enqueue_stop_and_finalize_recording

        rec = request_stop_cloud_recording(call)
        recording_pending = rec.is_preparing
        if recording_pending or rec.recording_status in {
            CallRecording.RecordingStatus.STOP_REQUESTED,
            CallRecording.RecordingStatus.STOPPING,
            CallRecording.RecordingStatus.PROCESSING,
            CallRecording.RecordingStatus.RECORDING,
            CallRecording.RecordingStatus.STARTING,
        }:
            mode = enqueue_stop_and_finalize_recording(call.id)
            if mode == "deferred":
                import logging

                logging.getLogger(__name__).warning(
                    "recording_stop_deferred call_id=%s status=%s "
                    "(awaiting reconcile)",
                    call.id,
                    rec.recording_status,
                )
    except Exception:
        import logging

        logging.getLogger(__name__).exception(
            "Cloud recording stop enqueue failed for call %s (call not affected)",
            call.id,
        )

    from apps.calls.post_call import ensure_post_call_artifacts

    ensure_post_call_artifacts(call)

    from apps.subscription.services import deduct_call_minutes_for_session

    deduct_call_minutes_for_session(call)

    # Stash for API response enrichment without changing return type callers.
    call._recording_pending = recording_pending  # type: ignore[attr-defined]
    return call, None


def _mark_setup_failure_recording(call: CallSession) -> None:
    """Ensure no playable recording artifact for setup failures."""
    from apps.calls.cloud_recording.service import ensure_recording_row

    try:
        rec = ensure_recording_row(call)
        if rec.recording_status in {
            CallRecording.RecordingStatus.IDLE,
            CallRecording.RecordingStatus.STARTING,
            "",
        } or not rec.recording_status:
            rec.recording_status = CallRecording.RecordingStatus.NO_MEDIA
            rec.recording_error = (call.end_reason or "setup_failed")[:255]
            rec.finalized_at = timezone.now()
            rec.ended_at = call.ended_at or timezone.now()
            rec.save(
                update_fields=[
                    "recording_status",
                    "recording_error",
                    "finalized_at",
                    "ended_at",
                ]
            )
    except Exception:
        import logging

        logging.getLogger(__name__).exception(
            "setup_failure_recording_mark_failed call_id=%s", call.id
        )


# Legacy immediate-start API (delegates to pending request for compatibility).
def create_call_session(
    user,
    *,
    session_type: str,
    teacher_id: int,
) -> CallSession:
    return request_call_session(
        user,
        session_type=session_type,
        teacher_id=teacher_id,
    )
