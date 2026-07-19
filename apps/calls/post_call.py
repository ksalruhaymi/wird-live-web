from django.utils import timezone

from apps.calls.services import student_display_name
from apps.tutoring.teacher_services import teacher_display_name

from .models import CallRecording, CallSession, SessionEvaluation
from .rating_service import ensure_peer_ratings


def _duration_seconds(call: CallSession) -> int:
    if call.started_at and call.ended_at:
        return max(0, int((call.ended_at - call.started_at).total_seconds()))
    return 0


def ensure_post_call_artifacts(call: CallSession) -> None:
    """Create evaluation + recording placeholders when a call ends."""
    if call.status != CallSession.Status.ENDED or not call.teacher_id:
        return

    from apps.calls.recording_consent import is_test_call_session

    # Test calls: recording only — no SessionEvaluation / peer ratings.
    if not getattr(call, "is_interview_call", False) and not is_test_call_session(
        call
    ):
        SessionEvaluation.objects.get_or_create(
            call_session=call,
            defaults={
                "student_id": call.student_id,
                "teacher_id": call.teacher_id,
                "status": SessionEvaluation.Status.PENDING,
            },
        )

        ensure_peer_ratings(call)

    rec, created = CallRecording.objects.get_or_create(
        call_session=call,
        defaults={
            "student_id": call.student_id,
            "teacher_id": call.teacher_id,
            "session_type": call.session_type,
            "started_at": call.started_at,
            "ended_at": call.ended_at or timezone.now(),
            "duration_seconds": _duration_seconds(call),
        },
    )
    if not created:
        updates = []
        if call.ended_at and rec.ended_at != call.ended_at:
            rec.ended_at = call.ended_at
            updates.append("ended_at")
        duration = _duration_seconds(call)
        if duration and rec.duration_seconds != duration:
            rec.duration_seconds = duration
            updates.append("duration_seconds")
        if updates:
            rec.save(update_fields=updates)


def evaluation_to_payload(ev: SessionEvaluation) -> dict:
    call = ev.call_session
    return {
        "id": ev.id,
        "call_id": call.id,
        "status": ev.status,
        "focus_level": ev.focus_level,
        "pages_count": ev.pages_count,
        "surah": ev.surah,
        "memorization": ev.memorization,
        "consolidation": ev.consolidation,
        "teacher_id": ev.teacher_id,
        "teacher_name": teacher_display_name(ev.teacher),
        "student_name": student_display_name(ev.student),
        "session_type": call.session_type,
        "call_date": call.created_at.isoformat() if call.created_at else None,
        "started_at": call.started_at.isoformat() if call.started_at else None,
        "ended_at": call.ended_at.isoformat() if call.ended_at else None,
        "duration_seconds": _duration_seconds(call),
        "created_at": ev.created_at.isoformat() if ev.created_at else None,
    }


def recording_to_payload(rec: CallRecording, viewer) -> dict:
    if viewer.id == rec.student_id:
        other_name = teacher_display_name(rec.teacher)
    else:
        other_name = student_display_name(rec.student)

    from apps.calls.recording_consent import is_test_call_session
    from apps.calls.recording_storage import (
        is_playable_object_key,
        object_key_for_recording,
    )

    call = getattr(rec, "call_session", None)
    is_test = bool(call is not None and is_test_call_session(call))
    if is_test:
        other_name = "تسجيل الاتصال التجريبي"

    status = rec.recording_status or CallRecording.RecordingStatus.IDLE
    # Canonical playable terminal: completed + supported final media key.
    key = object_key_for_recording(rec)
    is_playable = (
        status == CallRecording.RecordingStatus.COMPLETED
        and is_playable_object_key(key)
    )
    has_recording = is_playable
    is_terminal = status in CallRecording.TERMINAL_STATUSES
    user_message = _recording_user_message(status, is_playable)
    next_refresh = 0 if is_terminal else (8 if status == "processing" else 3)
    return {
        "id": rec.id,
        "call_id": rec.call_session_id,
        "call_status": getattr(rec.call_session, "status", ""),
        "session_type": rec.session_type,
        "type": rec.session_type,
        "other_party_name": other_name,
        "is_test_call": is_test,
        "has_recording": has_recording,
        "recording_status": status,
        "is_terminal": is_terminal,
        "is_playable": is_playable,
        "is_preparing": status in CallRecording.PREPARING_STATUSES,
        "failure_code": rec.failure_code or "",
        "user_message": user_message,
        "can_retry_reconciliation": status
        in {
            CallRecording.RecordingStatus.FAILED,
            CallRecording.RecordingStatus.EXPIRED,
            CallRecording.RecordingStatus.PROCESSING,
            CallRecording.RecordingStatus.STOPPING,
        }
        and not is_playable,
        "next_refresh_after_seconds": next_refresh,
        "processing_started_at": (
            rec.processing_started_at.isoformat()
            if getattr(rec, "processing_started_at", None)
            else None
        ),
        "ready_at": (
            rec.ready_at.isoformat() if getattr(rec, "ready_at", None) else None
        ),
        "duration_seconds": rec.duration_seconds,
        "started_at": rec.started_at.isoformat() if rec.started_at else None,
        "ended_at": rec.ended_at.isoformat() if rec.ended_at else None,
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
    }


def _recording_user_message(status: str, is_playable: bool) -> str:
    if is_playable or status == CallRecording.RecordingStatus.COMPLETED:
        return ""
    return {
        CallRecording.RecordingStatus.RECORDING: "المكالمة ما زالت جارية",
        CallRecording.RecordingStatus.STARTING: "جاري بدء التسجيل",
        CallRecording.RecordingStatus.STOP_REQUESTED: "جاري إنهاء التسجيل",
        CallRecording.RecordingStatus.STOPPING: "جاري إنهاء التسجيل",
        CallRecording.RecordingStatus.PROCESSING: "جاري تجهيز التسجيل",
        CallRecording.RecordingStatus.NO_MEDIA: "لم يتم إنشاء تسجيل لهذه المكالمة",
        CallRecording.RecordingStatus.FAILED: "تعذر تجهيز التسجيل",
        CallRecording.RecordingStatus.EXPIRED: "انتهت جلسة التسجيل قبل اكتمال المعالجة",
        CallRecording.RecordingStatus.SKIPPED: "لا يوجد تسجيل لهذه المكالمة",
        CallRecording.RecordingStatus.CANCELLED: "تم إلغاء التسجيل",
    }.get(status, "جاري تجهيز التسجيل")
