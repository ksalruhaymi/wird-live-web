from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from apps.communication.announcement_services import (
    announcement_to_legacy_payload,
    announcement_to_payload,
    get_active_announcements,
    get_current_announcement,
)


@csrf_exempt
@require_GET
def current_announcement(request):
    announcement = get_current_announcement()
    if not announcement:
        return JsonResponse({"announcement": None})
    return JsonResponse(
        announcement_to_legacy_payload(announcement),
    )


@csrf_exempt
@require_GET
def active_announcements(request):
    items = get_active_announcements(limit=3)
    return JsonResponse(
        {
            "success": True,
            "announcements": [
                announcement_to_payload(item, request=request) for item in items
            ],
        }
    )
