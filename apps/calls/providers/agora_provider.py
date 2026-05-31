import time

from agora_token_builder.RtcTokenBuilder import Role_Publisher, RtcTokenBuilder
from django.conf import settings
from django.utils import timezone

from apps.calls.exceptions import CallProviderError
from apps.calls.models import CallSession

from .mock_provider import channel_name_for


class AgoraCallProvider:
    provider = CallSession.Provider.AGORA

    def _require_config(self) -> tuple[str, str]:
        app_id = (getattr(settings, "AGORA_APP_ID", "") or "").strip()
        certificate = (getattr(settings, "AGORA_APP_CERTIFICATE", "") or "").strip()
        if not app_id or not certificate:
            raise CallProviderError("إعدادات Agora غير مكتملة.")
        return app_id, certificate

    def _build_rtc_token(
        self,
        *,
        app_id: str,
        certificate: str,
        channel_name: str,
        uid: int,
    ) -> str:
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

    def create_session(
        self,
        user,
        *,
        session_type: str,
        teacher=None,
    ) -> CallSession:
        if session_type not in CallSession.SessionType.values:
            raise CallProviderError("نوع الاتصال غير صالح.")

        app_id, certificate = self._require_config()
        uid = int(user.id)
        if uid <= 0:
            raise CallProviderError("معرّف المستخدم غير صالح لـ Agora.")

        now = timezone.now()
        call = CallSession.objects.create(
            student=user,
            teacher=teacher,
            session_type=session_type,
            provider=self.provider,
            status=CallSession.Status.ACTIVE,
            started_at=now,
        )
        channel = channel_name_for(call.id, user.id, getattr(teacher, "id", None))
        token = self._build_rtc_token(
            app_id=app_id,
            certificate=certificate,
            channel_name=channel,
            uid=uid,
        )
        call.channel_name = channel
        call.room_name = channel
        call.token = token
        call.save(
            update_fields=[
                "channel_name",
                "room_name",
                "token",
                "updated_at",
            ]
        )
        return call
