from django.db.models import Avg, F

from apps.maqraa.teacher_services import teacher_display_name

from .models import CallPeerRating, CallSession
from .services import student_display_name


def _duration_seconds(call: CallSession) -> int:
    if call.started_at and call.ended_at:
        return max(0, int((call.ended_at - call.started_at).total_seconds()))
    return 0


def _validate_score(value) -> int | None:
    try:
        score = int(value)
    except (TypeError, ValueError):
        return None
    if 1 <= score <= 5:
        return score
    return None


def ensure_peer_ratings(call: CallSession) -> None:
    """Create pending peer ratings for student and teacher when a call ends."""
    if call.status != CallSession.Status.ENDED or not call.teacher_id:
        return

    CallPeerRating.objects.get_or_create(
        call_session=call,
        rater_id=call.student_id,
        defaults={
            "rated_id": call.teacher_id,
            "rater_role": CallPeerRating.RaterRole.STUDENT,
            "status": CallPeerRating.Status.PENDING,
        },
    )
    CallPeerRating.objects.get_or_create(
        call_session=call,
        rater_id=call.teacher_id,
        defaults={
            "rated_id": call.student_id,
            "rater_role": CallPeerRating.RaterRole.TEACHER,
            "status": CallPeerRating.Status.PENDING,
        },
    )


def rating_to_payload(rating: CallPeerRating) -> dict:
    call = rating.call_session
    if rating.rater_role == CallPeerRating.RaterRole.STUDENT:
        peer_name = teacher_display_name(rating.rated)
        peer_role = "teacher"
    else:
        peer_name = student_display_name(rating.rated)
        peer_role = "student"

    return {
        "id": rating.id,
        "call_id": call.id,
        "status": rating.status,
        "rater_role": rating.rater_role,
        "peer_name": peer_name,
        "peer_role": peer_role,
        "competence": rating.competence,
        "clarity": rating.clarity,
        "audio_quality": rating.audio_quality,
        "teacher_id": call.teacher_id,
        "teacher_name": teacher_display_name(call.teacher) if call.teacher else "",
        "student_name": student_display_name(call.student),
        "session_type": call.session_type,
        "call_date": call.created_at.isoformat() if call.created_at else None,
        "started_at": call.started_at.isoformat() if call.started_at else None,
        "ended_at": call.ended_at.isoformat() if call.ended_at else None,
        "duration_seconds": _duration_seconds(call),
        "created_at": rating.created_at.isoformat() if rating.created_at else None,
    }


def teacher_rating_percents(teacher_ids: list[int]) -> dict[int, int]:
    """Average student→teacher star scores as 0–100 percent per teacher."""
    if not teacher_ids:
        return {}

    rows = (
        CallPeerRating.objects.filter(
            rated_id__in=teacher_ids,
            rater_role=CallPeerRating.RaterRole.STUDENT,
            status=CallPeerRating.Status.COMPLETED,
            competence__isnull=False,
            clarity__isnull=False,
            audio_quality__isnull=False,
        )
        .values("rated_id")
        .annotate(
            avg_stars=Avg(
                (F("competence") + F("clarity") + F("audio_quality")) / 3.0
            )
        )
    )
    result: dict[int, int] = {tid: 0 for tid in teacher_ids}
    for row in rows:
        avg_stars = row["avg_stars"]
        if avg_stars is None:
            continue
        result[row["rated_id"]] = max(0, min(100, round(float(avg_stars) / 5.0 * 100)))
    return result


def teacher_rating_percent(teacher_id: int) -> int:
    return teacher_rating_percents([teacher_id]).get(teacher_id, 0)
