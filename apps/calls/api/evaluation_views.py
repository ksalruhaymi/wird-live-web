import json

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.calls.models import CallPeerRating
from apps.calls.rating_service import _validate_score, rating_to_payload


def _require_auth(request):
    if request.user.is_authenticated:
        return None
    return JsonResponse(
        {"success": False, "message": "يجب تسجيل الدخول."},
        status=401,
    )


def _parse_json(request) -> dict:
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _ratings_queryset(user):
    return CallPeerRating.objects.filter(rater=user).select_related(
        "call_session",
        "call_session__student",
        "call_session__teacher",
        "rater",
        "rated",
    )


@csrf_exempt
@require_GET
def pending_evaluations(request):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err

    qs = (
        _ratings_queryset(request.user)
        .filter(status=CallPeerRating.Status.PENDING)
        .order_by("-created_at", "-id")
    )
    return JsonResponse(
        {
            "success": True,
            "evaluations": [rating_to_payload(r) for r in qs],
        }
    )


@csrf_exempt
@require_GET
def my_evaluations(request):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err

    qs = _ratings_queryset(request.user).order_by("-created_at", "-id")
    return JsonResponse(
        {
            "success": True,
            "evaluations": [rating_to_payload(r) for r in qs],
        }
    )


@csrf_exempt
@require_POST
def submit_evaluation(request):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err

    data = _parse_json(request)
    call_id = data.get("call_id")
    try:
        call_id = int(call_id)
    except (TypeError, ValueError):
        call_id = None

    if not call_id:
        return JsonResponse(
            {"success": False, "message": "معرّف الجلسة مطلوب."},
            status=400,
        )

    rating = get_object_or_404(
        _ratings_queryset(request.user),
        call_session_id=call_id,
        status=CallPeerRating.Status.PENDING,
    )

    competence = _validate_score(data.get("competence"))
    clarity = _validate_score(data.get("clarity"))
    audio_quality = _validate_score(data.get("audio_quality"))

    if competence is None or clarity is None or audio_quality is None:
        return JsonResponse(
            {"success": False, "message": "يرجى اختيار تقييم من 1 إلى 5 لكل معيار."},
            status=400,
        )

    rating.competence = competence
    rating.clarity = clarity
    rating.audio_quality = audio_quality
    rating.status = CallPeerRating.Status.COMPLETED
    rating.save()

    return JsonResponse(
        {"success": True, "evaluation": rating_to_payload(rating)}
    )
