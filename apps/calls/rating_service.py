from django.db import transaction
from django.db.models import Avg, F

from .models import (
    CallPeerRating,
    CallPeerRatingAnswer,
    CallSession,
    RatingCategoryConfig,
    RatingQuestion,
)
from .services import student_display_name, teacher_display_name


CATEGORY_LABELS_AR = {
    RatingQuestion.Category.TEACHER: "تقييم المعلم",
    RatingQuestion.Category.STUDENT: "تقييم الطالب",
}


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


def questions_type_for_rating(rating: CallPeerRating) -> str:
    if rating.rater_role == CallPeerRating.RaterRole.TEACHER:
        return RatingQuestion.Category.STUDENT
    return RatingQuestion.Category.TEACHER


def _valid_categories() -> set[str]:
    return {c[0] for c in RatingQuestion.Category.choices}


def is_category_active(category: str) -> bool:
    if category not in _valid_categories():
        return False
    config = RatingCategoryConfig.objects.filter(category=category).first()
    if config is None:
        return True
    return config.is_active


def questions_for_type(category: str) -> list[RatingQuestion]:
    if category not in _valid_categories():
        return []
    return list(
        RatingQuestion.objects.filter(category=category).order_by("order", "id")
    )


def question_to_payload(question: RatingQuestion) -> dict:
    return {
        "id": question.id,
        "text": question.question_text,
        "order": question.order,
        "max_stars": question.max_stars,
    }


def list_questions_payload(category: str) -> dict:
    if not is_category_active(category):
        return {
            "success": True,
            "type": category,
            "rating_active": False,
            "questions": [],
        }
    questions = questions_for_type(category)
    return {
        "success": True,
        "type": category,
        "rating_active": True,
        "questions": [question_to_payload(q) for q in questions],
    }


def _mirror_legacy_fields(
    rating: CallPeerRating,
    answers: list[CallPeerRatingAnswer],
) -> None:
    ordered = sorted(answers, key=lambda a: (a.question.order, a.question_id))
    if len(ordered) >= 1:
        rating.competence = ordered[0].stars
    if len(ordered) >= 2:
        rating.clarity = ordered[1].stars
    if len(ordered) >= 3:
        rating.audio_quality = ordered[2].stars


def _parse_answers_payload(
    data: dict,
    *,
    questions: list[RatingQuestion],
) -> tuple[list[tuple[RatingQuestion, int]] | None, str | None]:
    raw_answers = data.get("answers")
    if not isinstance(raw_answers, list) or not raw_answers:
        return None, None

    question_map = {q.id: q for q in questions}
    if not question_map:
        return None, "لا توجد أسئلة تقييم لهذا النوع."

    parsed: list[tuple[RatingQuestion, int]] = []
    seen_ids: set[int] = set()

    for item in raw_answers:
        if not isinstance(item, dict):
            return None, "صيغة الإجابات غير صالحة."
        try:
            question_id = int(item.get("question_id"))
        except (TypeError, ValueError):
            return None, "معرّف السؤال غير صالح."
        stars = _validate_score(item.get("stars"))
        if stars is None:
            return None, "يرجى اختيار تقييم من 1 إلى 5 لكل سؤال."

        question = question_map.get(question_id)
        if question is None:
            return None, "سؤال التقييم غير صالح."
        if question_id in seen_ids:
            return None, "تكرار في أسئلة التقييم."
        seen_ids.add(question_id)
        parsed.append((question, stars))

    if len(parsed) != len(question_map):
        return None, "يرجى الإجابة على جميع أسئلة التقييم."

    return parsed, None


@transaction.atomic
def submit_peer_rating(rating: CallPeerRating, data: dict) -> tuple[CallPeerRating | None, str | None]:
    questions_type = questions_type_for_rating(rating)
    if not is_category_active(questions_type):
        return None, "التقييم غير مفعّل لهذا النوع."

    questions = questions_for_type(questions_type)

    parsed, error = _parse_answers_payload(data, questions=questions)
    if error:
        return None, error

    if parsed is not None:
        CallPeerRatingAnswer.objects.filter(rating=rating).delete()
        answer_rows = [
            CallPeerRatingAnswer(
                rating=rating,
                question=question,
                stars=stars,
            )
            for question, stars in parsed
        ]
        CallPeerRatingAnswer.objects.bulk_create(answer_rows)
        _mirror_legacy_fields(rating, answer_rows)
    else:
        competence = _validate_score(data.get("competence"))
        clarity = _validate_score(data.get("clarity"))
        audio_quality = _validate_score(data.get("audio_quality"))
        if competence is None or clarity is None or audio_quality is None:
            return None, "يرجى اختيار تقييم من 1 إلى 5 لكل معيار."
        rating.competence = competence
        rating.clarity = clarity
        rating.audio_quality = audio_quality

    rating.status = CallPeerRating.Status.COMPLETED
    rating.save()
    return rating, None


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

    questions_type = questions_type_for_rating(rating)
    return {
        "id": rating.id,
        "call_id": call.id,
        "status": rating.status,
        "rater_role": rating.rater_role,
        "peer_name": peer_name,
        "peer_role": peer_role,
        "questions_type": questions_type,
        "rating_active": is_category_active(questions_type),
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
