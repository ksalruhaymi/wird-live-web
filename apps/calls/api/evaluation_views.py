import json

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.calls.models import CallPeerRating, RatingQuestion
from apps.calls.rating_service import (
    list_questions_payload,
    rating_to_payload,
    submit_peer_rating,
)


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
def rating_questions(request):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err

    category = (request.GET.get("type") or "").strip()
    valid = {c[0] for c in RatingQuestion.Category.choices}
    if category not in valid:
        return JsonResponse(
            {
                "success": False,
                "message": "نوع التقييم غير صالح.",
            },
            status=400,
        )

    return JsonResponse(list_questions_payload(category))


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
    evaluations = [
        payload
        for r in qs
        if (payload := rating_to_payload(r)).get("rating_active")
    ]
    return JsonResponse(
        {
            "success": True,
            "evaluations": evaluations,
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

    updated, error = submit_peer_rating(rating, data)
    if error:
        return JsonResponse({"success": False, "message": error}, status=400)

    return JsonResponse(
        {"success": True, "evaluation": rating_to_payload(updated)}
    )
