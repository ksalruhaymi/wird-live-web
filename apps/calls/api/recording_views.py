from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from apps.calls.models import CallRecording
from apps.calls.post_call import recording_to_payload


def _require_auth(request):
    if request.user.is_authenticated:
        return None
    return JsonResponse(
        {"success": False, "message": "يجب تسجيل الدخول."},
        status=401,
    )


@csrf_exempt
@require_GET
def my_recordings(request):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err

    user = request.user
    from apps.maqraa.teacher_services import resolve_user_type_slug

    if resolve_user_type_slug(user) == "teacher":
        qs = CallRecording.objects.filter(teacher=user)
    else:
        qs = CallRecording.objects.filter(student=user)

    qs = qs.select_related(
        "call_session", "student", "teacher"
    ).order_by("-created_at", "-id")

    return JsonResponse(
        {
            "success": True,
            "recordings": [recording_to_payload(r, user) for r in qs],
        }
    )
