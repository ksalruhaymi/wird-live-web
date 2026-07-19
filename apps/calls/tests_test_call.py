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
        self.assertEqual(call.service_type, CallSession.ServiceType.TEST_CALL)
        self.assertIsNone(call.teacher_id)
        self.assertEqual(call.student_id, self.student.id)
        self.assertEqual(call_data.get("service_type"), "test_call")
        self.assertIsNone(call_data.get("teacher_id"))

    def test_teacher_api_can_start_test_call(self):
        """Teachers must be allowed on POST calls/test-call/ (no role gate)."""
        teacher = User.objects.create_user(
            username="tc_teacher_caller",
            password="Pass1234!",
            user_type=USER_TYPE_TEACHER,
            email="tc_teacher_caller@example.com",
        )
        TeacherProfile.objects.create(
            user=teacher,
            display_name="معلم تجريبي",
            is_demo_teacher=False,
            is_approved=True,
            approval_status=TeacherProfile.ApprovalStatus.APPROVED,
            can_audio=True,
        )
        self.client.force_login(teacher)
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
        self.assertNotIn("غير متاح من حساب المعلّم", str(body))
        call_data = body["call"]
        self.assertTrue(call_data["is_test_call"])
        self.assertEqual(call_data.get("service_type"), "test_call")
        self.assertIsNone(call_data.get("teacher_id"))
        call = CallSession.objects.get(pk=call_data["id"])
        self.assertEqual(call.student_id, teacher.id)
        self.assertIsNone(call.teacher_id)
        self.assertEqual(call.service_type, CallSession.ServiceType.TEST_CALL)

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
                [self.student.id],
            )

        rec = CallRecording.objects.get(call_session=call)
        self.assertEqual(rec.recording_status, CallRecording.RecordingStatus.RECORDING)
        self.assertIsNone(rec.teacher_id)

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
                [self.student.id],
            )

        rec = CallRecording.objects.get(call_session=call)
        self.assertNotEqual(rec.recording_status, CallRecording.RecordingStatus.SKIPPED)
        self.assertIsNone(rec.teacher_id)

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
            teacher=None,
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
            teacher=None,
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


class TestCallLifetimeLimitTests(TestCase):
    """Lifetime max of 3 counted test calls (recording created) per user."""

    def setUp(self):
        self.student = User.objects.create_user(
            username="limit_student",
            password="Pass1234!",
            user_type=USER_TYPE_STUDENT,
            email="limit_student@example.com",
        )
        self.other = User.objects.create_user(
            username="limit_other",
            password="Pass1234!",
            user_type=USER_TYPE_STUDENT,
            email="limit_other@example.com",
        )
        self.teacher_user = User.objects.create_user(
            username="limit_teacher",
            password="Pass1234!",
            user_type=USER_TYPE_TEACHER,
            email="limit_teacher@example.com",
        )
        TeacherProfile.objects.create(
            user=self.teacher_user,
            display_name="معلم عادي",
            is_demo_teacher=False,
            is_approved=True,
            approval_status=TeacherProfile.ApprovalStatus.APPROVED,
            can_audio=True,
        )

    def _end_without_recording(self, call: CallSession) -> None:
        call.status = CallSession.Status.ENDED
        call.ended_at = timezone.now()
        call.save(update_fields=["status", "ended_at"])

    def _complete_counted_test_call(self, user) -> CallSession:
        """Simulate a real started test call that created a recording."""
        from apps.calls.services import counted_test_calls_for_user

        call = start_test_call_session(user)
        CallRecording.objects.create(
            call_session=call,
            student=user,
            teacher=None,
            session_type=call.session_type,
            recording_status=CallRecording.RecordingStatus.RECORDING,
            started_at=timezone.now(),
        )
        self._end_without_recording(call)
        self.assertGreaterEqual(counted_test_calls_for_user(user), 1)
        return call

    def test_user_can_complete_three_counted_test_calls(self):
        from apps.calls.services import counted_test_calls_for_user

        for _ in range(3):
            self._complete_counted_test_call(self.student)
        self.assertEqual(counted_test_calls_for_user(self.student), 3)

    def test_fourth_counted_test_call_is_rejected(self):
        from apps.calls.exceptions import CallValidationError
        from apps.calls.services import (
            TEST_CALL_LIFETIME_LIMIT_MESSAGE,
            start_test_call_session,
        )

        for _ in range(3):
            self._complete_counted_test_call(self.student)

        with self.assertRaises(CallValidationError) as ctx:
            start_test_call_session(self.student)
        self.assertEqual(ctx.exception.message, TEST_CALL_LIFETIME_LIMIT_MESSAGE)
        self.assertEqual(
            ctx.exception.message,
            "لقد استخدمت الحد الأقصى للاتصالات التجريبية.",
        )

    def test_failed_before_recording_does_not_count(self):
        from apps.calls.services import (
            counted_test_calls_for_user,
            start_test_call_session,
        )

        failed = start_test_call_session(self.student)
        self._end_without_recording(failed)
        self.assertEqual(counted_test_calls_for_user(self.student), 0)

        # Still allowed to start again (and complete with recording).
        self._complete_counted_test_call(self.student)
        self.assertEqual(counted_test_calls_for_user(self.student), 1)

        for _ in range(2):
            self._complete_counted_test_call(self.student)
        self.assertEqual(counted_test_calls_for_user(self.student), 3)

    def test_users_are_independent(self):
        from apps.calls.exceptions import CallValidationError
        from apps.calls.services import (
            counted_test_calls_for_user,
            start_test_call_session,
        )

        for _ in range(3):
            self._complete_counted_test_call(self.student)

        with self.assertRaises(CallValidationError):
            start_test_call_session(self.student)

        self.assertEqual(counted_test_calls_for_user(self.other), 0)
        first = start_test_call_session(self.other)
        self.assertTrue(first.is_test_call)
        self.assertEqual(first.student_id, self.other.id)

    def test_teacher_can_start_test_call(self):
        call = start_test_call_session(self.teacher_user)
        self.assertTrue(call.is_test_call)
        self.assertEqual(call.service_type, CallSession.ServiceType.TEST_CALL)
        self.assertEqual(call.student_id, self.teacher_user.id)
        self.assertIsNone(call.teacher_id)

    def test_recording_start_path_unchanged_for_test_call(self):
        """Existing gated recording start still runs after consent + media-ready."""
        call = start_test_call_session(self.student)
        with patch(
            "apps.calls.cloud_recording.service.start_cloud_recording_for_call"
        ) as mock_start:
            record_call_recording_consent(call, self.student, platform="android")
            mock_start.assert_not_called()
            mark_participant_media_ready(call, self.student, agora_uid=self.student.id)
            mock_start.assert_called_once()


class IndependentTestCallServiceTests(TestCase):
    """Standalone test-call service: no peer User/Teacher dependency."""

    def setUp(self):
        self.student = User.objects.create_user(
            username="ind_student",
            password="Pass1234!",
            user_type=USER_TYPE_STUDENT,
            email="ind_student@example.com",
        )
        self.teacher = User.objects.create_user(
            username="ind_teacher",
            password="Pass1234!",
            user_type=USER_TYPE_TEACHER,
            email="ind_teacher@example.com",
        )
        TeacherProfile.objects.create(
            user=self.teacher,
            display_name="معلم",
            is_demo_teacher=False,
            is_approved=True,
            approval_status=TeacherProfile.ApprovalStatus.APPROVED,
            can_audio=True,
            can_video=True,
        )

    def test_student_can_use_independent_test_call(self):
        call = start_test_call_session(self.student)
        self.assertTrue(call.is_test_call)
        self.assertEqual(call.service_type, "test_call")
        self.assertIsNone(call.teacher_id)
        self.assertEqual(call.student_id, self.student.id)
        self.assertEqual(call.status, CallSession.Status.ACTIVE)

    def test_teacher_can_use_independent_test_call(self):
        call = start_test_call_session(self.teacher)
        self.assertTrue(call.is_test_call)
        self.assertEqual(call.service_type, CallSession.ServiceType.TEST_CALL)
        self.assertIsNone(call.teacher_id)
        self.assertEqual(call.student_id, self.teacher.id)

    def test_service_is_not_a_user_or_teacher_peer(self):
        call = start_test_call_session(self.student)
        self.assertIsNone(call.teacher)
        self.assertFalse(
            TeacherProfile.objects.filter(user_id=call.teacher_id).exists()
        )
        self.assertTrue(call.is_independent_test_service)

    def test_request_call_to_demo_teacher_is_rejected(self):
        from apps.calls.exceptions import CallValidationError
        from apps.calls.services import request_call_session

        demo = User.objects.create_user(
            username="ind_demo",
            password="Pass1234!",
            user_type=USER_TYPE_TEACHER,
            email="ind.demo@wird.local",
        )
        TeacherProfile.objects.create(
            user=demo,
            is_demo_teacher=True,
            auto_accept_calls=True,
            is_approved=True,
            approval_status=TeacherProfile.ApprovalStatus.APPROVED,
            can_audio=True,
        )
        with self.assertRaises(CallValidationError) as ctx:
            request_call_session(
                self.student,
                session_type=CallSession.SessionType.AUDIO,
                teacher_id=demo.id,
            )
        self.assertIn("خدمة الاتصال التجريبي", ctx.exception.message)

    def test_normal_student_teacher_call_unaffected(self):
        from apps.calls.services import request_call_session

        with patch(
            "apps.calls.services.student_can_request_call",
            return_value=(True, ""),
        ), patch(
            "apps.calls.services.validate_teacher_for_call",
            return_value=None,
        ), patch(
            "apps.calls.services.provider_name_for_new_call",
            return_value=CallSession.Provider.AGORA,
        ), patch("apps.calls.services.assign_channel_name"), patch(
            "apps.calls.services.mark_teacher_busy"
        ):
            call = request_call_session(
                self.student,
                session_type=CallSession.SessionType.AUDIO,
                teacher_id=self.teacher.id,
            )
        self.assertFalse(call.is_test_call)
        self.assertEqual(call.service_type, CallSession.ServiceType.NONE)
        self.assertEqual(call.teacher_id, self.teacher.id)
        self.assertEqual(call.student_id, self.student.id)
        self.assertEqual(call.status, CallSession.Status.PENDING)

    def test_ensure_recording_row_allows_null_teacher(self):
        from apps.calls.cloud_recording.service import ensure_recording_row

        call = start_test_call_session(self.student)
        rec = ensure_recording_row(call)
        self.assertIsNone(rec.teacher_id)
        self.assertEqual(rec.student_id, self.student.id)


class TeacherTestCallMyRecordingsApiTests(TestCase):
    """Teacher test-call recordings must appear on recordings/my/."""

    def setUp(self):
        self.teacher = User.objects.create_user(
            username="rec_api_teacher",
            password="Pass1234!",
            user_type=USER_TYPE_TEACHER,
            email="rec_api_teacher@example.com",
        )
        TeacherProfile.objects.create(
            user=self.teacher,
            display_name="معلم API",
            is_demo_teacher=False,
            is_approved=True,
            approval_status=TeacherProfile.ApprovalStatus.APPROVED,
            can_audio=True,
        )
        self.student = User.objects.create_user(
            username="rec_api_student",
            password="Pass1234!",
            user_type=USER_TYPE_STUDENT,
            email="rec_api_student@example.com",
        )
        self.peer_teacher = User.objects.create_user(
            username="rec_api_peer",
            password="Pass1234!",
            user_type=USER_TYPE_TEACHER,
            email="rec_api_peer@example.com",
        )
        TeacherProfile.objects.create(
            user=self.peer_teacher,
            display_name="معلم عادي",
            is_demo_teacher=False,
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
        self.url = reverse("calls_api:recordings-my")

    def _create_teacher_test_recording(self, *, status, object_key=""):
        call = CallSession.objects.create(
            student=self.teacher,
            teacher=None,
            session_type=CallSession.SessionType.AUDIO,
            provider=CallSession.Provider.AGORA,
            status=CallSession.Status.ENDED,
            is_test_call=True,
            service_type=CallSession.ServiceType.TEST_CALL,
            channel_name="ch_teacher_test",
            started_at=timezone.now(),
            ended_at=timezone.now(),
        )
        return CallRecording.objects.create(
            call_session=call,
            student=self.teacher,
            teacher=None,
            session_type="audio",
            recording_status=status,
            recording_object_key=object_key,
            duration_seconds=45,
            started_at=call.started_at,
            ended_at=call.ended_at,
        )

    def _create_normal_recording(self):
        call = CallSession.objects.create(
            student=self.student,
            teacher=self.peer_teacher,
            session_type=CallSession.SessionType.AUDIO,
            provider=CallSession.Provider.AGORA,
            status=CallSession.Status.ENDED,
            is_test_call=False,
            channel_name="ch_normal",
            started_at=timezone.now(),
            ended_at=timezone.now(),
        )
        return CallRecording.objects.create(
            call_session=call,
            student=self.student,
            teacher=self.peer_teacher,
            session_type="audio",
            recording_status=CallRecording.RecordingStatus.COMPLETED,
            recording_object_key="recordings/normal/file.mp4",
            duration_seconds=120,
            started_at=call.started_at,
            ended_at=call.ended_at,
        )

    @patch("apps.calls.cloud_recording.try_finalize_recording_files")
    def test_teacher_test_recording_appears_in_my_recordings(self, _finalize):
        rec = self._create_teacher_test_recording(
            status=CallRecording.RecordingStatus.COMPLETED,
            object_key="recordings/test/teacher.mp4",
        )
        self.client.force_login(self.teacher)
        resp = self.client.get(self.url, **self.headers)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        ids = [r["id"] for r in body["recordings"]]
        self.assertIn(rec.id, ids)
        payload = next(r for r in body["recordings"] if r["id"] == rec.id)
        self.assertTrue(payload["is_test_call"])
        self.assertTrue(payload["is_playable"])
        self.assertEqual(payload["other_party_name"], "تسجيل الاتصال التجريبي")

    @patch("apps.calls.cloud_recording.try_finalize_recording_files")
    def test_teacher_null_payload_does_not_drop_preparing(self, _finalize):
        from apps.calls.post_call import recording_to_payload

        rec = self._create_teacher_test_recording(
            status=CallRecording.RecordingStatus.PROCESSING,
        )
        payload = recording_to_payload(rec, self.teacher)
        self.assertTrue(payload["is_test_call"])
        self.assertTrue(payload["is_preparing"])
        self.assertFalse(payload["is_playable"])
        self.assertEqual(payload["other_party_name"], "تسجيل الاتصال التجريبي")

        self.client.force_login(self.teacher)
        resp = self.client.get(self.url, **self.headers)
        self.assertEqual(resp.status_code, 200)
        ids = [r["id"] for r in resp.json()["recordings"]]
        self.assertIn(rec.id, ids)

    @patch("apps.calls.cloud_recording.try_finalize_recording_files")
    def test_completed_without_key_stays_preparing_then_playable(self, _finalize):
        from apps.calls.post_call import recording_to_payload

        rec = self._create_teacher_test_recording(
            status=CallRecording.RecordingStatus.COMPLETED,
            object_key="",
        )
        payload = recording_to_payload(rec, self.teacher)
        self.assertTrue(payload["is_preparing"])
        self.assertFalse(payload["is_playable"])

        rec.recording_object_key = "recordings/test/ready.mp4"
        rec.save(update_fields=["recording_object_key"])
        payload = recording_to_payload(rec, self.teacher)
        self.assertFalse(payload["is_preparing"])
        self.assertTrue(payload["is_playable"])

        self.client.force_login(self.teacher)
        resp = self.client.get(self.url, **self.headers)
        ids = [r["id"] for r in resp.json()["recordings"]]
        self.assertIn(rec.id, ids)
        row = next(r for r in resp.json()["recordings"] if r["id"] == rec.id)
        self.assertTrue(row["is_playable"])

    @patch("apps.calls.cloud_recording.try_finalize_recording_files")
    def test_normal_recordings_unaffected(self, _finalize):
        normal = self._create_normal_recording()
        self.client.force_login(self.peer_teacher)
        resp = self.client.get(self.url, **self.headers)
        self.assertEqual(resp.status_code, 200)
        ids = [r["id"] for r in resp.json()["recordings"]]
        self.assertIn(normal.id, ids)
        row = next(r for r in resp.json()["recordings"] if r["id"] == normal.id)
        self.assertFalse(row["is_test_call"])
        self.assertTrue(row["is_playable"])
        self.assertEqual(row["other_party_name"], "rec_api_student")

        self.client.force_login(self.student)
        resp = self.client.get(self.url, **self.headers)
        self.assertEqual(resp.status_code, 200)
        ids = [r["id"] for r in resp.json()["recordings"]]
        self.assertIn(normal.id, ids)
        row = next(r for r in resp.json()["recordings"] if r["id"] == normal.id)
        self.assertEqual(row["other_party_name"], "معلم عادي")
