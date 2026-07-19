"""Test-call (اتصال تجريبي) recording consent, media-ready, and duration tests."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.calls.cloud_recording.client import AgoraCloudRecordingError
from apps.calls.cloud_recording.reconcile import reconcile_stuck_calls
from apps.calls.models import (
    TEST_CALL_RECORDING_CONSENT_VERSION,
    CallRecording,
    CallRecordingConsent,
    CallSession,
    SessionEvaluation,
)
from apps.calls.recording_consent import (
    is_test_call_session,
    mark_participant_media_ready,
    maybe_start_recording_if_consents_ready,
    record_call_recording_consent,
    recording_consent_payload,
    recording_consents_satisfied,
)
from apps.calls.services import start_test_call_session
from apps.subscription.services import deduct_call_minutes_for_session
from apps.tutoring.models import TeacherProfile
from apps.tutoring.teacher_services import DEMO_CALL_MAX_SECONDS
from identity.accounts.user_types import USER_TYPE_STUDENT, USER_TYPE_TEACHER

User = get_user_model()


class TestCallFlowTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username="tc_student",
            password="Pass1234!",
            user_type=USER_TYPE_STUDENT,
            email="tc_student@example.com",
        )
        self.demo = User.objects.create_user(
            username="demo_teacher",
            password="Pass1234!",
            user_type=USER_TYPE_TEACHER,
            email="demo.teacher@wird.local",
        )
        TeacherProfile.objects.create(
            user=self.demo,
            display_name="اتصال تجريبي",
            is_demo_teacher=True,
            auto_accept_calls=True,
            is_approved=True,
            approval_status=TeacherProfile.ApprovalStatus.APPROVED,
            can_audio=True,
        )
        self.client = Client()
        self.headers = {
            "HTTP_X_APP_VERSION": "1.0.0",
            "HTTP_X_APP_BUILD": "1",
            "HTTP_X_APP_PLATFORM": "android",
        }

    def test_start_test_call_no_booking_or_balance(self):
        self.client.force_login(self.student)
        url = reverse("calls_api:test-call")
        with patch(
            "apps.calls.services.provider_name_for_new_call",
            return_value=CallSession.Provider.AGORA,
        ), patch("apps.calls.services.assign_channel_name"):
            resp = self.client.post(
                url, data="{}", content_type="application/json", **self.headers
            )
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertTrue(body["success"])
        call_data = body["call"]
        self.assertTrue(call_data["is_test_call"])
        self.assertEqual(call_data["max_duration_seconds"], 60)
        self.assertEqual(call_data.get("demo_max_seconds"), DEMO_CALL_MAX_SECONDS)
        call = CallSession.objects.get(pk=call_data["id"])
        self.assertTrue(call.is_test_call)
        self.assertEqual(call.teacher_id, self.demo.id)
        self.assertEqual(call.student_id, self.student.id)

    def test_consent_alone_does_not_start_test_call_recording(self):
        call = start_test_call_session(self.student)
        call.refresh_from_db()
        self.assertTrue(is_test_call_session(call))
        self.assertEqual(call.status, CallSession.Status.ACTIVE)

        with patch(
            "apps.calls.cloud_recording.service.start_cloud_recording_for_call"
        ) as mock_start:
            self.assertFalse(recording_consents_satisfied(call))
            mock_start.assert_not_called()

            record_call_recording_consent(call, self.student, platform="android")
            mock_start.assert_not_called()
            self.assertTrue(recording_consents_satisfied(call))
            self.assertFalse(maybe_start_recording_if_consents_ready(call))
            mock_start.assert_not_called()

        consent = CallRecordingConsent.objects.get(call_session=call, user=self.student)
        self.assertEqual(consent.consent_version, TEST_CALL_RECORDING_CONSENT_VERSION)
        self.assertEqual(
            CallRecordingConsent.objects.filter(call_session=call, user=self.demo).count(),
            0,
        )

    def test_media_ready_without_consent_rejected(self):
        from apps.calls.exceptions import CallValidationError

        call = start_test_call_session(self.student)
        with self.assertRaises(CallValidationError):
            mark_participant_media_ready(call, self.student, agora_uid=self.student.id)

    def test_media_ready_non_participant_rejected(self):
        from apps.calls.exceptions import CallValidationError

        other = User.objects.create_user(
            username="tc_other",
            password="Pass1234!",
            user_type=USER_TYPE_STUDENT,
        )
        call = start_test_call_session(self.student)
        record_call_recording_consent(call, self.student, platform="android")
        with self.assertRaises(CallValidationError):
            mark_participant_media_ready(call, other, agora_uid=other.id)

    def test_media_ready_starts_recording_once_idempotent(self):
        call = start_test_call_session(self.student)
        record_call_recording_consent(call, self.student, platform="android")

        with patch(
            "apps.calls.cloud_recording.service.start_cloud_recording_for_call"
        ) as mock_start:
            mark_participant_media_ready(call, self.student, agora_uid=self.student.id)
            mock_start.assert_called_once()

        call.refresh_from_db()
        self.assertIsNotNone(call.participant_media_ready_at)
        first_ready = call.participant_media_ready_at

        with patch(
            "apps.calls.cloud_recording.service.start_cloud_recording_for_call"
        ) as mock_start:
            # Idempotent media-ready timestamp; start_cloud still invoked but
            # real start is idempotent (tested below).
            mark_participant_media_ready(call, self.student, agora_uid=self.student.id)
            mock_start.assert_called_once()

        call.refresh_from_db()
        self.assertEqual(call.participant_media_ready_at, first_ready)

        with patch(
            "apps.calls.cloud_recording.service.uses_agora_rtc", return_value=True
        ), patch(
            "apps.calls.cloud_recording.service.cloud_recording_configured",
            return_value=True,
        ), patch(
            "apps.calls.cloud_recording.service.AgoraCloudRecordingClient"
        ) as client_cls:
            instance = client_cls.return_value
            instance.acquire.return_value = "r1"
            instance.start.return_value = "s1"
            from apps.calls.cloud_recording.service import start_cloud_recording_for_call

            start_cloud_recording_for_call(call)
            start_cloud_recording_for_call(call)
            self.assertEqual(instance.acquire.call_count, 1)
            self.assertEqual(instance.start.call_count, 1)
            self.assertEqual(
                instance.start.call_args.kwargs.get("subscribe_audio_uids"),
                [self.student.id, self.demo.id],
            )

        rec = CallRecording.objects.get(call_session=call)
        self.assertEqual(rec.recording_status, CallRecording.RecordingStatus.RECORDING)

    def test_media_ready_api_endpoint(self):
        call = start_test_call_session(self.student)
        record_call_recording_consent(call, self.student, platform="android")
        self.client.force_login(self.student)
        url = reverse("calls_api:media-ready", kwargs={"pk": call.id})
        with patch(
            "apps.calls.cloud_recording.service.start_cloud_recording_for_call"
        ) as mock_start:
            resp = self.client.post(
                url,
                data='{"agora_uid": %d}' % self.student.id,
                content_type="application/json",
                **self.headers,
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertTrue(body["call"]["participant_media_ready"])
        self.assertTrue(body.get("consent_ready"))
        mock_start.assert_called_once()
        call.refresh_from_db()
        self.assertIsNotNone(call.participant_media_ready_at)
        self.assertIn("expires_at", body["call"])
        self.assertIn("timer_started_at", body["call"])

    def test_demo_teacher_cannot_give_consent(self):
        from apps.calls.exceptions import CallValidationError

        call = start_test_call_session(self.student)
        with self.assertRaises(CallValidationError):
            record_call_recording_consent(call, self.demo, platform="android")

    def test_start_cloud_recording_does_not_skip_test_call(self):
        from apps.calls.cloud_recording.service import start_cloud_recording_for_call

        call = start_test_call_session(self.student)
        call.refresh_from_db()

        with patch(
            "apps.calls.cloud_recording.service.uses_agora_rtc", return_value=True
        ), patch(
            "apps.calls.cloud_recording.service.cloud_recording_configured",
            return_value=True,
        ), patch(
            "apps.calls.cloud_recording.service.AgoraCloudRecordingClient"
        ) as client_cls:
            instance = client_cls.return_value
            instance.acquire.return_value = "r1"
            instance.start.return_value = "s1"
            start_cloud_recording_for_call(call)
            client_cls.assert_called()
            self.assertEqual(
                instance.start.call_args.kwargs.get("subscribe_audio_uids"),
                [self.student.id, self.demo.id],
            )

        rec = CallRecording.objects.get(call_session=call)
        self.assertNotEqual(rec.recording_status, CallRecording.RecordingStatus.SKIPPED)

    def test_payload_allows_recording_for_test_call(self):
        call = start_test_call_session(self.student)
        payload = recording_consent_payload(call, self.student)
        self.assertTrue(payload["recording_allowed"])
        self.assertTrue(payload["recording_consent_required"])
        self.assertTrue(payload["is_test_call"])
        self.assertTrue(payload["test_call_caller_consent_only"])
        self.assertFalse(payload["participant_media_ready"])

    def test_concurrent_test_call_blocked(self):
        from apps.calls.exceptions import CallValidationError

        start_test_call_session(self.student)
        with self.assertRaises(CallValidationError):
            start_test_call_session(self.student)

    def test_auto_end_requires_media_ready_anchor(self):
        from apps.calls.services import maybe_auto_end_demo_call

        call = start_test_call_session(self.student)
        call.started_at = timezone.now() - timedelta(seconds=120)
        call.save(update_fields=["started_at"])
        # Without media-ready, do not auto-end on activation age.
        still = maybe_auto_end_demo_call(call, self.student)
        self.assertEqual(still.status, CallSession.Status.ACTIVE)

        call.participant_media_ready_at = timezone.now() - timedelta(seconds=61)
        call.save(update_fields=["participant_media_ready_at"])
        ended = maybe_auto_end_demo_call(call, self.student)
        self.assertEqual(ended.status, CallSession.Status.ENDED)

    def test_no_minute_deduction(self):
        call = start_test_call_session(self.student)
        call.status = CallSession.Status.ENDED
        call.started_at = timezone.now() - timedelta(seconds=40)
        call.ended_at = timezone.now()
        call.save(update_fields=["status", "started_at", "ended_at"])
        charged = deduct_call_minutes_for_session(call)
        self.assertEqual(charged, 0)
        call.refresh_from_db()
        self.assertEqual(float(call.minutes_charged or 0), 0)

    def test_no_evaluation_created(self):
        from apps.calls.post_call import ensure_post_call_artifacts

        call = start_test_call_session(self.student)
        call.status = CallSession.Status.ENDED
        call.ended_at = timezone.now()
        call.save(update_fields=["status", "ended_at"])
        ensure_post_call_artifacts(call)
        self.assertFalse(
            SessionEvaluation.objects.filter(call_session=call).exists()
        )

    def test_reconcile_ends_overdue_test_call(self):
        call = start_test_call_session(self.student)
        call.participant_media_ready_at = timezone.now() - timedelta(seconds=90)
        call.save(update_fields=["participant_media_ready_at"])
        with patch(
            "apps.calls.cloud_recording.reconcile.stop_and_finalize_recording_for_call_id"
        ):
            summary = reconcile_stuck_calls(dry_run=False)
        self.assertIn(call.id, summary["test_calls_finalized"])
        call.refresh_from_db()
        self.assertEqual(call.status, CallSession.Status.ENDED)

    def test_max_duration_constant_is_60(self):
        self.assertEqual(DEMO_CALL_MAX_SECONDS, 60)

    def test_worker_404_without_r2_sets_clear_failure(self):
        from apps.calls.cloud_recording.service import try_finalize_recording_files

        call = start_test_call_session(self.student)
        rec = CallRecording.objects.create(
            call_session=call,
            student=self.student,
            teacher=self.demo,
            session_type=call.session_type,
            recording_status=CallRecording.RecordingStatus.PROCESSING,
            agora_resource_id="rid",
            agora_sid="sid",
            recording_uid="900000007",
            processing_started_at=timezone.now(),
        )
        with patch(
            "apps.calls.recording_storage.find_playable_object_key_for_recording",
            return_value="",
        ), patch(
            "apps.calls.cloud_recording.service.AgoraCloudRecordingClient"
        ) as client_cls:
            instance = client_cls.return_value
            instance.query.side_effect = AgoraCloudRecordingError(
                "recording API returned status 404: failed to find worker",
                status_code=404,
                action="query",
                safe_body='{"reason":"failed to find worker"}',
            )
            ok = try_finalize_recording_files(rec, allow_expire=True)
        self.assertFalse(ok)
        rec.refresh_from_db()
        self.assertEqual(rec.recording_status, CallRecording.RecordingStatus.NO_MEDIA)
        self.assertEqual(rec.failure_code, "recorder_worker_exited_before_media")

    def test_r2_rematch_prevents_false_no_media(self):
        from apps.calls.cloud_recording.service import try_finalize_recording_files

        call = start_test_call_session(self.student)
        rec = CallRecording.objects.create(
            call_session=call,
            student=self.student,
            teacher=self.demo,
            session_type=call.session_type,
            recording_status=CallRecording.RecordingStatus.PROCESSING,
            agora_resource_id="rid",
            agora_sid="sid",
            recording_uid="900000007",
            processing_started_at=timezone.now(),
        )
        with patch(
            "apps.calls.recording_storage.find_playable_object_key_for_recording",
            return_value="recordings/ch/file.mp4",
        ), patch(
            "apps.calls.recording_storage.is_playable_object_key",
            return_value=True,
        ):
            ok = try_finalize_recording_files(rec, allow_expire=True)
        self.assertTrue(ok)
        rec.refresh_from_db()
        self.assertEqual(rec.recording_status, CallRecording.RecordingStatus.COMPLETED)
        self.assertEqual(rec.recording_object_key, "recordings/ch/file.mp4")

    def test_normal_call_still_needs_both_consents(self):
        teacher = User.objects.create_user(
            username="real_t", password="Pass1234!", user_type=USER_TYPE_TEACHER
        )
        TeacherProfile.objects.create(
            user=teacher,
            is_demo_teacher=False,
            is_approved=True,
            approval_status=TeacherProfile.ApprovalStatus.APPROVED,
        )
        call = CallSession.objects.create(
            student=self.student,
            teacher=teacher,
            session_type=CallSession.SessionType.AUDIO,
            provider=CallSession.Provider.AGORA,
            status=CallSession.Status.ACTIVE,
            started_at=timezone.now(),
            is_test_call=False,
            channel_name="ch_real",
        )
        with patch(
            "apps.calls.cloud_recording.service.start_cloud_recording_for_call"
        ) as mock_start:
            record_call_recording_consent(call, self.student, platform="android")
            mock_start.assert_not_called()
            record_call_recording_consent(call, teacher, platform="ios")
            mock_start.assert_not_called()
            mark_participant_media_ready(call, self.student, agora_uid=self.student.id)
            mock_start.assert_not_called()
            mark_participant_media_ready(call, teacher, agora_uid=teacher.id)
            mock_start.assert_called_once()
