import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.analytics.api_auth import allow_public_analytics_ingest

from ..ingest import MAX_BODY_BYTES, ingest_mobile_payload


def _allow_public_analytics_ingest(request):
    return allow_public_analytics_ingest(request)


@csrf_exempt
@require_POST
def ingest_mobile_events(request):
    if not _allow_public_analytics_ingest(request):
        return JsonResponse({"detail": "Invalid or missing API key."}, status=401)

    if len(request.body) > MAX_BODY_BYTES:
        return JsonResponse({"detail": "Request body too large."}, status=413)

    try:
        data = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"detail": "Invalid JSON."}, status=400)

    if not isinstance(data, dict):
        return JsonResponse({"detail": "Invalid payload."}, status=400)

    return ingest_mobile_payload(request, data)
