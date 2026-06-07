import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.tutoring.models import TeacherFavorite
from apps.tutoring.teacher_services import resolve_user_type_slug


def _require_auth(request):
    if request.user.is_authenticated:
        return None
    return JsonResponse(
        {"success": False, "message": "يجب تسجيل الدخول."},
        status=401,
    )


@csrf_exempt
@require_GET
def favorite_teacher_ids(request):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err
    if resolve_user_type_slug(request.user) != "student":
        return JsonResponse({"success": True, "teacher_ids": []})

    ids = list(
        TeacherFavorite.objects.filter(student=request.user).values_list(
            "teacher_id", flat=True
        )
    )
    return JsonResponse({"success": True, "teacher_ids": ids})


@csrf_exempt
@require_POST
def toggle_favorite(request, teacher_id):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err
    if resolve_user_type_slug(request.user) != "student":
        return JsonResponse(
            {"success": False, "message": "للطلاب فقط."},
            status=403,
        )

    from django.contrib.auth import get_user_model

    User = get_user_model()
    teacher = User.objects.filter(
        pk=teacher_id, teacher_profile__isnull=False
    ).first()
    if teacher is None:
        return JsonResponse(
            {"success": False, "message": "المعلّم غير موجود."},
            status=404,
        )

    fav = TeacherFavorite.objects.filter(
        student=request.user, teacher=teacher
    ).first()
    if fav:
        fav.delete()
        is_favorite = False
    else:
        TeacherFavorite.objects.create(student=request.user, teacher=teacher)
        is_favorite = True

    return JsonResponse(
        {"success": True, "teacher_id": teacher_id, "is_favorite": is_favorite}
    )
