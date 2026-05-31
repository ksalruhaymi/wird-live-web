import secrets
import time

from agora_token_builder.RtcTokenBuilder import Role_Publisher, RtcTokenBuilder
from django.conf import settings

from apps.calls.exceptions import CallProviderError
from apps.calls.models import CallSession
from apps.calls.providers.mock_provider import channel_name_for


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


def assign_channel_name(call: CallSession) -> str:
    teacher_id = call.teacher_id
    channel = channel_name_for(call.id, call.student_id, teacher_id)
    call.channel_name = channel
    call.room_name = channel
    call.save(update_fields=["channel_name", "room_name", "updated_at"])
    return channel


def build_token_for_uid(call: CallSession, uid: int) -> str:
    if not call.channel_name:
        assign_channel_name(call)

    if call.provider == CallSession.Provider.AGORA:
        return _agora_token(channel_name=call.channel_name, uid=uid)
    return _mock_token(call.id, uid)


def provider_name_for_new_call() -> str:
    name = (getattr(settings, "CALL_PROVIDER", "mock") or "mock").strip().lower()
    if name == "agora":
        return CallSession.Provider.AGORA
    return CallSession.Provider.MOCK
