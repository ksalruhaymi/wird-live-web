"""Tests for incoming-call push payload + notify hooks."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.push.call_payload import (
    build_incoming_call_data,
    call_kit_uuid,
    parse_incoming_call_data,
)
from apps.push.models import UserDevice

User = get_user_model()


class CallPayloadTests(TestCase):
    def test_build_ring_payload_has_no_agora_secrets(self):
        data = build_incoming_call_data(
            call_id=42,
            caller_name="أحمد",
            caller_id=7,
            session_type="video",
            action="ring",
        )
        self.assertEqual(data["type"], "incoming_call")
        self.assertEqual(data["action"], "ring")
        self.assertEqual(data["call_id"], "42")
        self.assertEqual(data["caller_name"], "أحمد")
        self.assertEqual(data["session_type"], "video")
        self.assertEqual(data["call_uuid"], call_kit_uuid(42))
        joined = " ".join(data.values()).lower()
        self.assertNotIn("token", joined)
        self.assertNotIn("agora", joined)
        self.assertNotIn("app_id", joined)

    def test_parse_rejects_incomplete(self):
        self.assertIsNone(parse_incoming_call_data(None))
        self.assertIsNone(parse_incoming_call_data({}))
        self.assertIsNone(parse_incoming_call_data({"type": "incoming_call"}))
        self.assertIsNone(
            parse_incoming_call_data({"type": "incoming_call", "call_id": "x"})
        )

    def test_parse_accepts_valid(self):
        raw = build_incoming_call_data(
            call_id=9,
            caller_name="سارة",
            caller_id=3,
            session_type="audio",
        )
        parsed = parse_incoming_call_data(raw)
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["call_id"], 9)
        self.assertEqual(parsed["action"], "ring")

    def test_uuid_stable_for_same_call(self):
        self.assertEqual(call_kit_uuid(1), call_kit_uuid(1))
        self.assertNotEqual(call_kit_uuid(1), call_kit_uuid(2))


@override_settings(FIREBASE_CREDENTIALS_PATH="")
class IncomingCallNotifyTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username="student_push",
            email="student_push@example.com",
            password="pass12345",
        )
        self.teacher = User.objects.create_user(
            username="teacher_push",
            email="teacher_push@example.com",
            password="pass12345",
        )
        UserDevice.objects.create(
            user=self.teacher,
            fcm_token="fcm-teacher-1",
            platform=UserDevice.Platform.ANDROID,
            device_id="dev-a",
            is_active=True,
        )
        UserDevice.objects.create(
            user=self.teacher,
            fcm_token="fcm-teacher-ios",
            voip_token="voip-hex-token",
            platform=UserDevice.Platform.IOS,
            device_id="dev-i",
            is_active=True,
        )

    @patch("apps.push.call_notify._send_fcm_call")
    @patch("apps.push.apns_voip.send_voip_push", return_value=True)
    def test_notify_incoming_sends_fcm_and_voip(self, voip_mock, fcm_mock):
        fcm_mock.return_value = {
            "sent": 2,
            "failed": 0,
            "deactivated": 0,
            "total": 2,
        }
        from apps.calls.models import CallSession
        from apps.push.call_notify import notify_incoming_call

        call = CallSession.objects.create(
            student=self.student,
            teacher=self.teacher,
            session_type=CallSession.SessionType.AUDIO,
            status=CallSession.Status.PENDING,
            channel_name="ch-1",
        )
        result = notify_incoming_call(call)
        self.assertEqual(result["sent"], 2)
        self.assertEqual(result["voip"], 1)
        fcm_mock.assert_called_once()
        voip_mock.assert_called()
        data = fcm_mock.call_args.kwargs["data"]
        self.assertEqual(data["type"], "incoming_call")
        self.assertEqual(data["action"], "ring")
        self.assertEqual(data["call_id"], str(call.id))

    @patch("apps.push.call_notify._send_fcm_call")
    @patch("apps.push.apns_voip.send_voip_push", return_value=True)
    def test_notify_cancel_action(self, voip_mock, fcm_mock):
        fcm_mock.return_value = {
            "sent": 1,
            "failed": 0,
            "deactivated": 0,
            "total": 1,
        }
        from apps.calls.models import CallSession
        from apps.push.call_notify import notify_call_cancelled

        call = CallSession.objects.create(
            student=self.student,
            teacher=self.teacher,
            session_type=CallSession.SessionType.AUDIO,
            status=CallSession.Status.REJECTED,
            channel_name="ch-2",
        )
        notify_call_cancelled(call, reason="rejected")
        data = fcm_mock.call_args.kwargs["data"]
        self.assertEqual(data["action"], "cancel")
