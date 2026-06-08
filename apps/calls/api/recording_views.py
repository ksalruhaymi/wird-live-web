from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from apps.calls.models import CallRecording
from apps.calls.post_call import recording_to_payload
from apps.calls.recording_storage import (
    RecordingStorageError,
    generate_recording_signed_url,
    object_key_for_recording,
    user_can_access_recording,
)


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
    from apps.tutoring.teacher_services import resolve_user_type_slug

    if resolve_user_type_slug(user) == "teacher":
        qs = CallRecording.objects.filter(teacher=user).exclude(
            call_session__is_interview_call=True
        )
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


@csrf_exempt
@require_GET
def recording_signed_url(request, pk: int):
    """Return a short-lived presigned URL for an authorized recording."""
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err

    recording = get_object_or_404(CallRecording, pk=pk)

    if not user_can_access_recording(request.user, recording):
        return JsonResponse(
            {"success": False, "message": "غير مصرح لك بالوصول إلى هذا التسجيل."},
            status=403,
        )

    object_key = object_key_for_recording(recording)
    if not object_key:
        return JsonResponse(
            {"success": False, "message": "لا يوجد ملف تسجيل متاح."},
            status=404,
        )

    try:
        url, expires_in = generate_recording_signed_url(object_key)
    except RecordingStorageError:
        return JsonResponse(
            {"success": False, "message": "تعذر تجهيز رابط التشغيل."},
            status=500,
        )

    return JsonResponse(
        {
            "success": True,
            "url": url,
            "expires_in": expires_in,
        }
    )
