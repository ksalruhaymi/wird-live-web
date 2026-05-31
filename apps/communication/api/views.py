from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from apps.communication.announcement_services import (
    announcement_to_payload,
    get_current_announcement,
)


@csrf_exempt
@require_GET
def current_announcement(request):
    announcement = get_current_announcement()
    if not announcement:
        return JsonResponse({"announcement": None})
    return JsonResponse(announcement_to_payload(announcement))
