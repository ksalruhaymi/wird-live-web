from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from apps.mobile.app_config_services import app_config_to_payload
from apps.mobile.models import MobileAppConfig


@csrf_exempt
@require_GET
def app_config(request):
    config = MobileAppConfig.get_settings()
    return JsonResponse(app_config_to_payload(config))
