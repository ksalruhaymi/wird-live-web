from django.http import JsonResponse

from apps.mobile.app_config_services import build_mobile_access_denial, evaluate_mobile_api_access
from apps.mobile.models import MobileAppConfig

API_V1_PREFIX = "/api/v1/"
APP_CONFIG_PATH = "/api/v1/mobile/app-config/"
APP_VERSION_CHECK_PATH = "/api/v1/mobile/app-version/check/"
# Server-to-server callbacks (not mobile clients).
EXEMPT_API_PATHS = frozenset(
    {
        APP_CONFIG_PATH,
        APP_VERSION_CHECK_PATH,
        "/api/v1/agora/recording-webhook/",
    }
)


class MobileAppVersionMiddleware:
    """Enforce remote mobile app version policy on JSON API v1 routes."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._should_enforce(request):
            denial = self._evaluate_request(request)
            if denial is not None:
                return JsonResponse(
                    denial["payload"],
                    status=denial["status_code"],
                )
        return self.get_response(request)

    @staticmethod
    def _should_enforce(request) -> bool:
        path = request.path
        if not path.startswith(API_V1_PREFIX):
            return False
        if path in EXEMPT_API_PATHS:
            return False
        return True

    @staticmethod
    def _evaluate_request(request) -> dict | None:
        config = MobileAppConfig.get_settings()

        version = (request.META.get("HTTP_X_APP_VERSION") or "").strip()
        build_raw = (request.META.get("HTTP_X_APP_BUILD") or "").strip()
        platform = (request.META.get("HTTP_X_APP_PLATFORM") or "").strip().lower()

        if not version or not build_raw or platform not in {"android", "ios"}:
            return build_mobile_access_denial(
                status_code=426,
                code="app_version_required",
                config=config,
            )

        try:
            app_build = int(build_raw)
        except ValueError:
            return build_mobile_access_denial(
                status_code=426,
                code="app_version_required",
                config=config,
            )

        return evaluate_mobile_api_access(
            app_version=version,
            app_build=app_build,
            config=config,
        )
