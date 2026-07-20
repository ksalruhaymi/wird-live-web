import json
import mimetypes

from django.contrib.auth import get_user_model
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST

from apps.tutoring.management_services import (
    list_pending_teachers,
    management_dashboard_stats_payload,
    pending_teacher_card_payload,
    teacher_review_detail_payload,
)
from apps.tutoring.models import TeacherProfile
from apps.tutoring.teacher_approval_service import (
    approve_teacher_profile,
    reject_teacher_profile,
)
from identity.accounts.auth.profile_service import ijazah_file_kind
from identity.accounts.user_types import USER_TYPE_TEACHER

User = get_user_model()


def _api_error(message: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"success": False, "message": message}, status=status)


def _require_permission(request, code: str) -> JsonResponse | None:
    if not request.user.is_authenticated:
        return _api_error("يجب تسجيل الدخول.", 401)
    if not request.user.has_permission(code):
        return _api_error("ليس لديك صلاحية لهذا الإجراء.", 403)
    return None


def _parse_json_body(request) -> tuple[dict | None, JsonResponse | None]:
    try:
        raw = request.body.decode("utf-8") if request.body else "{}"
        data = json.loads(raw or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, _api_error("Invalid JSON.", 400)
    if not isinstance(data, dict):
        return None, _api_error("Invalid JSON.", 400)
    return data, None


def _get_pending_teacher(teacher_id: int):
    return get_object_or_404(
        User.objects.select_related("teacher_profile"),
        pk=teacher_id,
        user_type=USER_TYPE_TEACHER,
        teacher_profile__isnull=False,
        teacher_profile__approval_status=TeacherProfile.ApprovalStatus.PENDING,
    )


@require_GET
def management_dashboard_stats(request):
    err = _require_permission(request, "management.teachers.view")
    if err:
        return err

    return JsonResponse(
        {
            "success": True,
            "stats": management_dashboard_stats_payload(),
        }
    )


@require_GET
def pending_teachers_list(request):
    err = _require_permission(request, "management.teachers.view")
    if err:
        return err

    q = (request.GET.get("q") or "").strip()
    teachers = [
        pending_teacher_card_payload(user, request)
        for user in list_pending_teachers(q=q, viewer=request.user)
    ]
    return JsonResponse({"success": True, "teachers": teachers})


@require_GET
def pending_teacher_detail(request, teacher_id):
    err = _require_permission(request, "management.teachers.view")
    if err:
        return err

    user = get_object_or_404(
        User.objects.select_related("teacher_profile"),
        pk=teacher_id,
        user_type=USER_TYPE_TEACHER,
        teacher_profile__isnull=False,
    )
    return JsonResponse(
        {
            "success": True,
            "teacher": teacher_review_detail_payload(user, request),
        }
    )


@require_POST
def pending_teacher_approve(request, teacher_id):
    err = _require_permission(request, "management.teachers.approve")
    if err:
        return err

    user = _get_pending_teacher(teacher_id)
    approve_teacher_profile(user.teacher_profile, request.user)
    return JsonResponse({"success": True, "message": "تم قبول المعلّم بنجاح."})


@require_POST
def pending_teacher_reject(request, teacher_id):
    err = _require_permission(request, "management.teachers.reject")
    if err:
        return err

    data, parse_err = _parse_json_body(request)
    if parse_err:
        return parse_err

    reason = (data.get("rejection_reason") or "").strip()
    if not reason:
        return _api_error("سبب الرفض مطلوب.")

    user = _get_pending_teacher(teacher_id)
    reject_teacher_profile(user.teacher_profile, request.user, reason)
    return JsonResponse({"success": True, "message": "تم رفض طلب المعلّم."})


@require_GET
def management_teacher_profile_image(request, teacher_id):
    err = _require_permission(request, "management.teachers.view")
    if err:
        return err

    user_obj = get_object_or_404(User, pk=teacher_id, user_type=USER_TYPE_TEACHER)
    image = getattr(user_obj, "profile_image", None)
    if not image or not image.name:
        return _api_error("لا توجد صورة.", 404)

    content_type, _ = mimetypes.guess_type(image.name)
    try:
        return FileResponse(
            image.open("rb"),
            content_type=content_type or "image/jpeg",
        )
    except (ValueError, FileNotFoundError):
        return _api_error("تعذر فتح الملف.", 404)


@require_GET
def management_teacher_ijazah(request, teacher_id):
    err = _require_permission(request, "management.teachers.view")
    if err:
        return err

    user_obj = get_object_or_404(
        User.objects.select_related("teacher_profile"),
        pk=teacher_id,
        user_type=USER_TYPE_TEACHER,
    )
    profile = getattr(user_obj, "teacher_profile", None)
    ijazah = getattr(profile, "ijazah", None) if profile else None
    if not ijazah or not ijazah.name:
        return _api_error("لا يوجد ملف إجازة.", 404)

    content_type, _ = mimetypes.guess_type(ijazah.name)
    filename = ijazah.name.rsplit("/", 1)[-1]
    try:
        response = FileResponse(
            ijazah.open("rb"),
            content_type=content_type or "application/octet-stream",
        )
        disposition = (
            "inline"
            if ijazah_file_kind(filename) in {"image", "pdf"}
            else "attachment"
        )
        response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
        return response
    except (ValueError, FileNotFoundError):
        return _api_error("تعذر فتح الملف.", 404)
