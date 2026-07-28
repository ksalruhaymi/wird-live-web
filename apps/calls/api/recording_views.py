from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from apps.calls.models import CallRecording
from apps.calls.post_call import recording_to_payload
from apps.calls.recording_storage import (
    RecordingStorageError,
    generate_recording_signed_url,
    is_playable_object_key,
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
    from django.db.models import Q

    from apps.calls.recording_soft_delete import recording_hidden_for_user
    from apps.tutoring.teacher_services import resolve_user_type_slug

    # Include rows where the viewer is student OR teacher.
    # Test-call recordings store the caller as student with teacher=null.
    qs = CallRecording.objects.filter(Q(student=user) | Q(teacher=user))
    if resolve_user_type_slug(user) == "teacher":
        qs = qs.exclude(call_session__is_interview_call=True)

    qs = qs.select_related(
        "call_session", "student", "teacher"
    ).order_by("-created_at", "-id")

    # Finalize a few recent recordings that are still waiting on Agora files.
    from apps.calls.cloud_recording import try_finalize_recording_files

    pending = [
        rec
        for rec in qs[:8]
        if (
            not is_playable_object_key(object_key_for_recording(rec))
            and (
                rec.recording_status in CallRecording.PREPARING_STATUSES
                or (
                    rec.recording_status == CallRecording.RecordingStatus.COMPLETED
                    and not rec.is_playable
                )
            )
        )
    ]
    for rec in pending[:3]:
        try:
            try_finalize_recording_files(rec, allow_expire=True)
        except Exception:
            continue

    visible = [r for r in qs if not recording_hidden_for_user(r, user)]
    return JsonResponse(
        {
            "success": True,
            "recordings": [
                p
                for r in visible
                if (p := recording_to_payload(r, user))
                and (p.get("is_playable") or p.get("is_preparing"))
            ],
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
    if not object_key or not is_playable_object_key(object_key):
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



@csrf_exempt
@require_http_methods(["DELETE", "POST"])
def delete_my_recording(request, pk: int):
    """Soft-remove a recording from the caller's list only.

    Does not delete the file from storage. Hard delete is retention-gated and
    separate from the user-facing remove action.
    """
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err

    recording = get_object_or_404(CallRecording, pk=pk)
    user = request.user
    if recording.student_id != user.id and recording.teacher_id != user.id:
        return JsonResponse(
            {"success": False, "message": "غير مصرح لك بحذف هذا التسجيل."},
            status=403,
        )

    from apps.calls.recording_soft_delete import (
        hide_recording_for_user,
        recording_parties_have_hidden,
    )

    hide_recording_for_user(recording, user)
    recording.refresh_from_db()
    both_hidden = recording_parties_have_hidden(recording)
    # Hard delete is retention-gated and runs via cleanup job — not here.
    return JsonResponse(
        {
            "success": True,
            "recording_id": pk,
            "soft_removed": True,
            "removed_for_both_parties": both_hidden,
            "hard_deleted": False,
            "storage_cleaned": False,
        }
    )
