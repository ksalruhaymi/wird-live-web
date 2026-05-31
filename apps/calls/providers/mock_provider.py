import secrets

from django.utils import timezone

from apps.calls.exceptions import CallProviderError
from apps.calls.models import CallSession


def _mock_token(call_id: int, user_id: int) -> str:
    suffix = secrets.token_hex(8)
    return f"mock_token_{call_id}_{user_id}_{suffix}"


def channel_name_for(call_id: int, student_id: int, teacher_id: int | None = None) -> str:
    if teacher_id:
        return f"call_{call_id}_s{student_id}_t{teacher_id}"
    return f"call_{call_id}_user_{student_id}"


class MockCallProvider:
    provider = CallSession.Provider.MOCK

    def create_session(
        self,
        user,
        *,
        session_type: str,
        teacher=None,
    ) -> CallSession:
        if session_type not in CallSession.SessionType.values:
            raise CallProviderError("نوع الاتصال غير صالح.")

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
        token = _mock_token(call.id, user.id)
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
