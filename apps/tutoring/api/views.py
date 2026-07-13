from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.tutoring.teacher_services import (
    list_teachers_payload,
    record_teacher_heartbeat,
    resolve_user_type_slug,
)


def _require_auth(request) -> JsonResponse | None:
    if request.user.is_authenticated:
        return None
    return JsonResponse(
        {"success": False, "message": "يجب تسجيل الدخول."},
        status=401,
    )


@require_GET
def available_teachers(request):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err

    # Teachers only receive calls; they must not browse/call other teachers.
    if resolve_user_type_slug(request.user) == "teacher":
        return JsonResponse(
            {
                "success": False,
                "message": "المعلّم لا يمكنه عرض قائمة المعلمين أو بدء اتصال.",
            },
            status=403,
        )

    if not request.user.has_permission("mobile.teachers.list.view"):
        return JsonResponse(
            {"success": False, "message": "غير مصرح بعرض قائمة المعلمين."},
            status=403,
        )

    teachers = list_teachers_payload(approved_only=True, request=request)
    return JsonResponse({"success": True, "teachers": teachers})


@csrf_exempt
@require_POST
def teacher_heartbeat(request):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err

    if resolve_user_type_slug(request.user) != "teacher":
        return JsonResponse(
            {"success": False, "message": "هذا المسار للمعلّمين فقط."},
            status=403,
        )

    try:
        availability = record_teacher_heartbeat(request.user)
    except PermissionError:
        return JsonResponse(
            {"success": False, "message": "هذا المسار للمعلّمين فقط."},
            status=403,
        )

    last_seen = availability.last_seen or timezone.now()
    return JsonResponse(
        {
            "success": True,
            "last_seen": last_seen.isoformat(),
        }
    )
