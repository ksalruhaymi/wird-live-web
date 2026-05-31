import json

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.calls.models import SessionEvaluation
from apps.calls.post_call import evaluation_to_payload
from apps.maqraa.teacher_services import resolve_user_type_slug


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


@csrf_exempt
@require_GET
def pending_evaluations(request):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err
    if resolve_user_type_slug(request.user) != "student":
        return JsonResponse(
            {"success": False, "message": "للطلاب فقط."},
            status=403,
        )

    qs = (
        SessionEvaluation.objects.filter(
            student=request.user,
            status=SessionEvaluation.Status.PENDING,
        )
        .select_related("call_session", "teacher", "student")
        .order_by("-created_at", "-id")
    )
    return JsonResponse(
        {
            "success": True,
            "evaluations": [evaluation_to_payload(e) for e in qs],
        }
    )


@csrf_exempt
@require_GET
def my_evaluations(request):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err

    user = request.user
    if resolve_user_type_slug(user) == "teacher":
        qs = SessionEvaluation.objects.filter(teacher=user)
    else:
        qs = SessionEvaluation.objects.filter(student=user)

    qs = qs.select_related("call_session", "teacher", "student").order_by(
        "-created_at", "-id"
    )
    return JsonResponse(
        {
            "success": True,
            "evaluations": [evaluation_to_payload(e) for e in qs],
        }
    )


@csrf_exempt
@require_POST
def submit_evaluation(request):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err
    if resolve_user_type_slug(request.user) != "student":
        return JsonResponse(
            {"success": False, "message": "للطلاب فقط."},
            status=403,
        )

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

    ev = get_object_or_404(
        SessionEvaluation.objects.select_related("call_session", "teacher", "student"),
        call_session_id=call_id,
        student=request.user,
    )

    focus = data.get("focus_level")
    try:
        focus_level = int(focus) if focus is not None else None
    except (TypeError, ValueError):
        focus_level = None

    ev.focus_level = focus_level
    ev.pages_count = (data.get("pages_count") or "").strip()
    ev.surah = (data.get("surah") or "").strip()
    ev.memorization = (data.get("memorization") or "").strip()
    ev.consolidation = (data.get("consolidation") or "").strip()
    ev.status = SessionEvaluation.Status.COMPLETED
    ev.save()

    return JsonResponse(
        {"success": True, "evaluation": evaluation_to_payload(ev)}
    )
