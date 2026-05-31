from django.conf import settings

from .agora_provider import AgoraCallProvider
from .mock_provider import MockCallProvider


def get_call_provider():
    name = (getattr(settings, "CALL_PROVIDER", "mock") or "mock").strip().lower()
    if name == "agora":
        return AgoraCallProvider()
    return MockCallProvider()
