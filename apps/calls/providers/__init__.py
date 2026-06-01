from django.conf import settings

from apps.calls.exceptions import CallProviderError

from .agora_provider import AgoraCallProvider
from .mock_provider import MockCallProvider


def get_call_provider():
    explicit = (getattr(settings, "CALL_PROVIDER", "") or "").strip().lower()
    env = getattr(settings, "APP_ENV", None) or "dev"
    is_prod = str(env).strip().lower() == "prod"
    app_id = (getattr(settings, "AGORA_APP_ID", "") or "").strip()
    certificate = (getattr(settings, "AGORA_APP_CERTIFICATE", "") or "").strip()
    agora_ready = bool(app_id and certificate)

    if explicit == "mock":
        if is_prod:
            raise CallProviderError("Mock call provider is disabled in production.")
        return MockCallProvider()
    if explicit == "agora" or agora_ready:
        return AgoraCallProvider()
    if is_prod:
        raise CallProviderError("إعدادات Agora غير مكتملة.")
    return MockCallProvider()
