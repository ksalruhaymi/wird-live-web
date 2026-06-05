from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.notification.app_notification_services import (
    list_app_notifications_for_user,
    mark_all_app_notifications_read,
    mark_app_notification_read,
    unread_app_notifications_count,
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
def app_notifications_list(request):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err
    notifications = list_app_notifications_for_user(request.user)
    return JsonResponse(
        {
            "success": True,
            "notifications": notifications,
            "unread_count": unread_app_notifications_count(request.user),
        }
    )


@csrf_exempt
@require_GET
def app_notifications_unread_count(request):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err
    return JsonResponse(
        {
            "success": True,
            "unread_count": unread_app_notifications_count(request.user),
        }
    )


@csrf_exempt
@require_POST
def app_notification_mark_read(request, notification_id: int):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err
    if not mark_app_notification_read(request.user, notification_id):
        return JsonResponse(
            {"success": False, "message": "التنبيه غير موجود أو غير نشط."},
            status=404,
        )
    return JsonResponse(
        {
            "success": True,
            "unread_count": unread_app_notifications_count(request.user),
        }
    )


@csrf_exempt
@require_POST
def app_notifications_mark_all_read(request):
    auth_err = _require_auth(request)
    if auth_err:
        return auth_err
    marked = mark_all_app_notifications_read(request.user)
    return JsonResponse(
        {
            "success": True,
            "marked_count": marked,
            "unread_count": unread_app_notifications_count(request.user),
        }
    )
