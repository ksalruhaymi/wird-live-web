"""Tests for Agora webhook HMAC signature verification and replay guards."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.calls.api.agora_webhook import verify_agora_request_signature
from apps.calls.models import CallRecording, CallSession

User = get_user_model()

SECRET = "test-agora-notification-secret"


def _sign(body: bytes, *, secret: str = SECRET) -> tuple[str, str]:
    v1 = hmac.new(secret.encode(), body, hashlib.sha1).hexdigest()
    v2 = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return v1, v2


@override_settings(
    AGORA_WEBHOOK_SECRET=SECRET,
    AGORA_WEBHOOK_MAX_SKEW_SECONDS=600,
)
class AgoraWebhookAuthTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.url = reverse("calls_api:agora-recording-webhook")
        self.student = User.objects.create_user(username="wh_student", password="x")
        self.teacher = User.objects.create_user(username="wh_teacher", password="x")
        self.call = CallSession.objects.create(
            student=self.student,
            teacher=self.teacher,
            session_type=CallSession.SessionType.AUDIO,
            provider=CallSession.Provider.AGORA,
            status=CallSession.Status.ENDED,
            channel_name="ch_wh_1",
            started_at=timezone.now(),
            ended_at=timezone.now(),
        )
        self.rec = CallRecording.objects.create(
            call_session=self.call,
            student=self.student,
            teacher=self.teacher,
            session_type="audio",
            recording_status=CallRecording.RecordingStatus.PROCESSING,
            agora_resource_id="res_wh_1",
            agora_sid="sid_wh_1",
            recording_uid="900000099",
        )

    def _payload(self, **overrides) -> dict:
        data = {
            "noticeId": "notice-abc-001",
            "productId": 3,
            "eventType": 31,
            "notifyMs": int(time.time() * 1000),
            "payload": {
                "sid": "sid_wh_1",
                "resourceId": "res_wh_1",
                "sendts": int(time.time() * 1000),
            },
        }
        data.update(overrides)
        return data

    def _post(self, payload: dict, *, headers: dict | None = None, qs: str = ""):
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        v1, v2 = _sign(body)
        hdrs = {
            "HTTP_AGORA_SIGNATURE": v1,
            "HTTP_AGORA_SIGNATURE_V2": v2,
            "CONTENT_TYPE": "application/json",
        }
        if headers is not None:
            hdrs = {"CONTENT_TYPE": "application/json", **headers}
        url = self.url + qs
        return self.client.generic("POST", url, data=body, **hdrs), body

    def test_hmac_helper_accepts_sha1_and_sha256(self):
        body = b'{"noticeId":"n1"}'
        v1, v2 = _sign(body)
        self.assertTrue(
            verify_agora_request_signature(
                secret=SECRET, body=body, signature_sha1=v1, signature_sha256=""
            )
        )
        self.assertTrue(
            verify_agora_request_signature(
                secret=SECRET, body=body, signature_sha1="", signature_sha256=v2
            )
        )
        self.assertFalse(
            verify_agora_request_signature(
                secret=SECRET, body=body, signature_sha1="deadbeef", signature_sha256=""
            )
        )

    def test_rejects_missing_secret_config(self):
        with override_settings(AGORA_WEBHOOK_SECRET=""):
            resp, _ = self._post(self._payload())
        self.assertEqual(resp.status_code, 503)

    def test_rejects_missing_signature(self):
        body = json.dumps(self._payload()).encode()
        resp = self.client.generic(
            "POST",
            self.url,
            data=body,
            CONTENT_TYPE="application/json",
        )
        self.assertEqual(resp.status_code, 401)

    def test_rejects_query_token_even_with_valid_signature(self):
        payload = self._payload()
        body = json.dumps(payload, separators=(",", ":")).encode()
        v1, v2 = _sign(body)
        resp = self.client.generic(
            "POST",
            self.url + f"?token={SECRET}",
            data=body,
            CONTENT_TYPE="application/json",
            HTTP_AGORA_SIGNATURE=v1,
            HTTP_AGORA_SIGNATURE_V2=v2,
        )
        self.assertEqual(resp.status_code, 401)

    def test_rejects_bad_signature(self):
        payload = self._payload()
        body = json.dumps(payload, separators=(",", ":")).encode()
        resp = self.client.generic(
            "POST",
            self.url,
            data=body,
            CONTENT_TYPE="application/json",
            HTTP_AGORA_SIGNATURE="0" * 40,
        )
        self.assertEqual(resp.status_code, 401)

    def test_rejects_stale_notify_ms(self):
        payload = self._payload(notifyMs=int(time.time() * 1000) - 20 * 60 * 1000)
        resp, _ = self._post(payload)
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json().get("message"), "stale_event")

    def test_accepts_valid_signature_and_matches_recording(self):
        with patch(
            "apps.calls.api.agora_webhook.try_finalize_recording_files"
        ) as mock_finalize:
            mock_finalize.return_value = None
            resp, _ = self._post(self._payload())
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertTrue(data["matched"])
        self.assertEqual(data["recording_id"], self.rec.id)
        mock_finalize.assert_called_once()

    def test_duplicate_notice_id_is_idempotent(self):
        with patch(
            "apps.calls.api.agora_webhook.try_finalize_recording_files"
        ) as mock_finalize:
            mock_finalize.return_value = None
            first, _ = self._post(self._payload())
            second, _ = self._post(self._payload())
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(second.json().get("duplicate"))
        self.assertEqual(mock_finalize.call_count, 1)

    def test_does_not_log_full_secret_or_signature_on_failure(self):
        payload = self._payload()
        body = json.dumps(payload, separators=(",", ":")).encode()
        with self.assertLogs("apps.calls.api.agora_webhook", level="WARNING") as cm:
            self.client.generic(
                "POST",
                self.url,
                data=body,
                CONTENT_TYPE="application/json",
                HTTP_AGORA_SIGNATURE="abcdef0123456789abcdef0123456789abcdef01",
            )
        joined = "\n".join(cm.output)
        self.assertNotIn(SECRET, joined)
        self.assertNotIn("abcdef0123456789abcdef0123456789abcdef01", joined)
