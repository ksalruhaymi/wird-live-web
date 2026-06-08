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

    if not getattr(call, "is_interview_call", False):
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

    from apps.calls.recording_storage import object_key_for_recording

    has_recording = bool(object_key_for_recording(rec)) and (
        rec.recording_status == rec.RecordingStatus.COMPLETED
    )
    return {
        "id": rec.id,
        "call_id": rec.call_session_id,
        "session_type": rec.session_type,
        "type": rec.session_type,
        "other_party_name": other_name,
        "has_recording": has_recording,
        "duration_seconds": rec.duration_seconds,
        "started_at": rec.started_at.isoformat() if rec.started_at else None,
        "ended_at": rec.ended_at.isoformat() if rec.ended_at else None,
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
    }
