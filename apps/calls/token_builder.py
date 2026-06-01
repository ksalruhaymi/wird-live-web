import os
import secrets
import time
from datetime import timedelta

from agora_token_builder.RtcTokenBuilder import Role_Publisher, RtcTokenBuilder
from django.conf import settings

from apps.calls.exceptions import CallProviderError
from apps.calls.models import CallSession
from apps.calls.providers.mock_provider import channel_name_for


def agora_credentials_configured() -> bool:
    app_id = (getattr(settings, "AGORA_APP_ID", "") or "").strip()
    certificate = (getattr(settings, "AGORA_APP_CERTIFICATE", "") or "").strip()
    return bool(app_id and certificate)


def is_production_environment() -> bool:
    env = getattr(settings, "APP_ENV", None) or os.getenv("APP_ENV", "dev") or "dev"
    return str(env).strip().lower() == "prod"


def _explicit_call_provider() -> str:
    return (getattr(settings, "CALL_PROVIDER", "") or "").strip().lower()


def _mock_token(call_id: int, user_id: int) -> str:
    suffix = secrets.token_hex(8)
    return f"mock_token_{call_id}_{user_id}_{suffix}"


def _agora_token(*, channel_name: str, uid: int) -> str:
    app_id = (getattr(settings, "AGORA_APP_ID", "") or "").strip()
    certificate = (getattr(settings, "AGORA_APP_CERTIFICATE", "") or "").strip()
    if not app_id or not certificate:
        raise CallProviderError("إعدادات Agora غير مكتملة.")
    if uid <= 0:
        raise CallProviderError("معرّف المستخدم غير صالح لـ Agora.")

    ttl = int(getattr(settings, "CALL_TOKEN_TTL_SECONDS", 3600) or 3600)
    privilege_expired_ts = int(time.time()) + max(ttl, 60)
    token = RtcTokenBuilder.buildTokenWithUid(
        app_id,
        certificate,
        channel_name,
        uid,
        Role_Publisher,
        privilege_expired_ts,
    )
    if not token:
        raise CallProviderError("تعذّر توليد رمز Agora.")
    return token


def token_expiry_iso() -> str:
    from django.utils import timezone

    ttl = int(getattr(settings, "CALL_TOKEN_TTL_SECONDS", 3600) or 3600)
    return (timezone.now() + timedelta(seconds=max(ttl, 60))).isoformat()


def assign_channel_name(call: CallSession) -> str:
    teacher_id = call.teacher_id
    channel = channel_name_for(call.id, call.student_id, teacher_id)
    call.channel_name = channel
    call.room_name = channel
    call.save(update_fields=["channel_name", "room_name", "updated_at"])
    return channel


def uses_agora_rtc(call: CallSession) -> bool:
    if call.provider == CallSession.Provider.AGORA:
        return True
    if not agora_credentials_configured():
        return False
    if is_production_environment():
        return True
    return _explicit_call_provider() != "mock"


def ensure_agora_provider(call: CallSession) -> None:
    """Upgrade legacy mock rows when Agora is configured (e.g. after deploy)."""
    if not uses_agora_rtc(call):
        return
    if call.provider == CallSession.Provider.AGORA:
        return
    call.provider = CallSession.Provider.AGORA
    call.save(update_fields=["provider", "updated_at"])


def build_agora_rtc_token(*, channel_name: str, uid: int) -> str:
    """RTC token for a UID joining a channel (e.g. cloud recording bot)."""
    return _agora_token(channel_name=channel_name, uid=uid)


def build_token_for_uid(call: CallSession, uid: int) -> str:
    if not call.channel_name:
        assign_channel_name(call)

    ensure_agora_provider(call)

    if uses_agora_rtc(call):
        return _agora_token(channel_name=call.channel_name, uid=uid)

    if is_production_environment():
        raise CallProviderError("إعدادات Agora غير مكتملة.")

    return _mock_token(call.id, uid)


def provider_name_for_new_call() -> str:
    explicit = _explicit_call_provider()

    if explicit == "mock":
        if is_production_environment():
            raise CallProviderError("Mock call provider is disabled in production.")
        return CallSession.Provider.MOCK

    if explicit == "agora":
        if not agora_credentials_configured():
            raise CallProviderError("إعدادات Agora غير مكتملة.")
        return CallSession.Provider.AGORA

    if agora_credentials_configured():
        return CallSession.Provider.AGORA

    if is_production_environment():
        raise CallProviderError("إعدادات Agora غير مكتملة.")

    return CallSession.Provider.MOCK
