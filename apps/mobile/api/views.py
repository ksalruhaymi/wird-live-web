from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from apps.mobile.app_config_services import app_config_to_payload
from apps.mobile.models import MobileAppConfig, MobilePlatform
from apps.mobile.version_services import (
    evaluate_app_version_check,
    is_valid_version_name,
)


@csrf_exempt
@require_GET
def app_config(request):
    """Legacy public config endpoint — kept for older published app builds."""
    config = MobileAppConfig.get_settings()
    return JsonResponse(app_config_to_payload(config))


@csrf_exempt
@require_GET
def app_version_check(request):
    """
    Public version-check endpoint for optional / required / blocked updates.
    Does not require authentication.
    """
    platform = (request.GET.get("platform") or "").strip().lower()
    version_name = (request.GET.get("version_name") or "").strip()
    build_raw = (request.GET.get("build_number") or "").strip()
    locale = (request.GET.get("locale") or "ar").strip()

    if platform not in {MobilePlatform.ANDROID, MobilePlatform.IOS}:
        return JsonResponse(
            {"success": False, "message": "platform غير صالح."},
            status=400,
        )

    if not is_valid_version_name(version_name):
        return JsonResponse(
            {"success": False, "message": "version_name غير صالح."},
            status=400,
        )

    try:
        build_number = int(build_raw)
    except (TypeError, ValueError):
        return JsonResponse(
            {"success": False, "message": "build_number غير صالح."},
            status=400,
        )

    if build_number < 1:
        return JsonResponse(
            {"success": False, "message": "build_number غير صالح."},
            status=400,
        )

    payload = evaluate_app_version_check(
        platform=platform,
        version_name=version_name,
        build_number=build_number,
        locale=locale,
    )
    return JsonResponse(payload)
