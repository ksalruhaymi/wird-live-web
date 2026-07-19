"""Teacher accept atomicity, dual media-ready, and recordings list filters."""

from __future__ import annotations

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.calls.models import CallRecording, CallSession
from apps.calls.recording_consent import (
    mark_participant_media_ready,
    maybe_start_recording_if_consents_ready,
    record_call_recording_consent,
    recording_start_prerequisites_met,
)
from apps.calls.services import accept_call_session
from identity.accounts.user_types import USER_TYPE_STUDENT, USER_TYPE_TEACHER
from apps.tutoring.models import TeacherProfile

User = get_user_model()


class TeacherAcceptCallTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username="acc_student",
            password="Pass1234!",
            user_type=USER_TYPE_STUDENT,
        )
        self.teacher = User.objects.create_user(
            username="acc_teacher",
            password="Pass1234!",
            user_type=USER_TYPE_TEACHER,
        )
        TeacherProfile.objects.create(user=self.teacher)
        self.other = User.objects.create_user(
            username="acc_other",
            password="Pass1234!",
            user_type=USER_TYPE_TEACHER,
        )
        TeacherProfile.objects.create(user=self.other)
        self.call = CallSession.objects.create(
            student=self.student,
            teacher=self.teacher,
            session_type=CallSession.SessionType.AUDIO,
            provider=CallSession.Provider.AGORA,
            status=CallSession.Status.PENDING,
            channel_name="ch_accept_1",
        )
        self.client = Client()

    def test_accept_pending_call_atomic(self):
        updated, error = accept_call_session(self.call, self.teacher)
        self.assertIsNone(error)
        self.assertEqual(updated.status, CallSession.Status.ACTIVE)
        self.assertIsNotNone(updated.started_at)

    def test_accept_idempotent_when_already_active(self):
        first, err1 = accept_call_session(self.call, self.teacher)
        self.assertIsNone(err1)
        second, err2 = accept_call_session(first, self.teacher)
        self.assertIsNone(err2)
        self.assertEqual(second.status, CallSession.Status.ACTIVE)
        self.assertEqual(second.id, first.id)

    def test_non_assigned_teacher_cannot_accept(self):
        updated, error = accept_call_session(self.call, self.other)
        self.assertIsNone(updated)
        self.assertIn("غير مصرح", error or "")

    def test_accept_api_returns_teacher_agora_uid(self):
        self.client.force_login(self.teacher)
        url = reverse("calls_api:accept", kwargs={"pk": self.call.pk})
        with patch(
            "apps.calls.services.build_token_for_uid",
            return_value="teacher_token_abc",
        ):
            resp = self.client.post(
                url,
                data=json.dumps({}),
                content_type="application/json",
                HTTP_X_APP_VERSION="1.0.0",
                HTTP_X_APP_BUILD="1",
                HTTP_X_APP_PLATFORM="android",
            )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["call"]["uid"], self.teacher.id)
        self.assertEqual(body["call"]["token"], "teacher_token_abc")
        self.assertEqual(body["call"]["channel_name"], "ch_accept_1")
        self.assertEqual(body["call"]["status"], CallSession.Status.ACTIVE)


class RealCallMediaReadyRecordingTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username="mr_student",
            password="Pass1234!",
            user_type=USER_TYPE_STUDENT,
        )
        self.teacher = User.objects.create_user(
            username="mr_teacher",
            password="Pass1234!",
            user_type=USER_TYPE_TEACHER,
        )
        TeacherProfile.objects.create(user=self.teacher)
        self.call = CallSession.objects.create(
            student=self.student,
            teacher=self.teacher,
            session_type=CallSession.SessionType.AUDIO,
            provider=CallSession.Provider.AGORA,
            status=CallSession.Status.ACTIVE,
            started_at=timezone.now(),
            channel_name="ch_media_1",
        )

    def test_consent_alone_does_not_start_real_call_recording(self):
        with patch(
            "apps.calls.cloud_recording.service.start_cloud_recording_for_call"
        ) as mock_start:
            record_call_recording_consent(self.call, self.student, platform="android")
            record_call_recording_consent(self.call, self.teacher, platform="ios")
            self.assertFalse(recording_start_prerequisites_met(self.call))
            self.assertFalse(maybe_start_recording_if_consents_ready(self.call))
            mock_start.assert_not_called()

    def test_both_media_ready_starts_recording_once(self):
        record_call_recording_consent(self.call, self.student, platform="android")
        record_call_recording_consent(self.call, self.teacher, platform="ios")

        def _fake_start(call):
            CallRecording.objects.get_or_create(
                call_session=call,
                defaults={
                    "student_id": call.student_id,
                    "teacher_id": call.teacher_id,
                    "session_type": call.session_type,
                    "recording_status": CallRecording.RecordingStatus.RECORDING,
                },
            )
            rec = call.recording
            if rec.recording_status != CallRecording.RecordingStatus.RECORDING:
                rec.recording_status = CallRecording.RecordingStatus.RECORDING
                rec.save(update_fields=["recording_status"])

        with patch(
            "apps.calls.cloud_recording.service.start_cloud_recording_for_call",
            side_effect=_fake_start,
        ) as mock_start:
            mark_participant_media_ready(
                self.call, self.student, agora_uid=self.student.id
            )
            mock_start.assert_not_called()

            mark_participant_media_ready(
                self.call, self.teacher, agora_uid=self.teacher.id
            )
            mock_start.assert_called_once()

            mark_participant_media_ready(
                self.call, self.teacher, agora_uid=self.teacher.id
            )
            mock_start.assert_called_once()

        call = CallSession.objects.get(pk=self.call.pk)
        self.assertIsNotNone(call.student_media_ready_at)
        self.assertIsNotNone(call.teacher_media_ready_at)

    def test_media_ready_allowed_with_own_consent_only(self):
        """Student can mark media-ready before teacher consents (no deadlock)."""
        record_call_recording_consent(self.call, self.student, platform="android")
        with patch(
            "apps.calls.cloud_recording.service.start_cloud_recording_for_call"
        ) as mock_start:
            mark_participant_media_ready(
                self.call, self.student, agora_uid=self.student.id
            )
            mock_start.assert_not_called()
        call = CallSession.objects.get(pk=self.call.pk)
        self.assertIsNotNone(call.student_media_ready_at)
        self.assertIsNone(call.teacher_media_ready_at)

    def test_one_party_media_ready_does_not_start_recording(self):
        record_call_recording_consent(self.call, self.student, platform="android")
        record_call_recording_consent(self.call, self.teacher, platform="ios")
        with patch(
            "apps.calls.cloud_recording.service.start_cloud_recording_for_call"
        ) as mock_start:
            mark_participant_media_ready(
                self.call, self.student, agora_uid=self.student.id
            )
            mock_start.assert_not_called()
            self.assertFalse(recording_start_prerequisites_met(self.call))

    def test_media_ready_idempotent_for_student(self):
        record_call_recording_consent(self.call, self.student, platform="android")
        first = mark_participant_media_ready(
            self.call, self.student, agora_uid=self.student.id
        )
        second = mark_participant_media_ready(
            self.call, self.student, agora_uid=self.student.id
        )
        self.assertEqual(first.student_media_ready_at, second.student_media_ready_at)

    def test_non_participant_cannot_media_ready(self):
        from apps.calls.exceptions import CallValidationError

        other = User.objects.create_user(
            username="mr_other",
            password="Pass1234!",
            user_type=USER_TYPE_STUDENT,
        )
        record_call_recording_consent(self.call, self.student, platform="android")
        with self.assertRaises(CallValidationError):
            mark_participant_media_ready(self.call, other, agora_uid=other.id)

    def test_accepted_active_is_not_completed(self):
        self.assertEqual(self.call.status, CallSession.Status.ACTIVE)
        self.assertNotIn(self.call.status, CallSession.TERMINAL_STATUSES)


class StaleActiveCallReconcileTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username="stale_student",
            password="Pass1234!",
            user_type=USER_TYPE_STUDENT,
        )
        self.teacher = User.objects.create_user(
            username="stale_teacher",
            password="Pass1234!",
            user_type=USER_TYPE_TEACHER,
        )
        TeacherProfile.objects.create(user=self.teacher)

    def test_stale_active_without_media_ends_as_failed(self):
        from datetime import timedelta

        from apps.calls.cloud_recording.reconcile import _force_end_call

        call = CallSession.objects.create(
            student=self.student,
            teacher=self.teacher,
            session_type=CallSession.SessionType.AUDIO,
            provider=CallSession.Provider.AGORA,
            status=CallSession.Status.ACTIVE,
            started_at=timezone.now() - timedelta(hours=2),
            channel_name="ch_stale_1",
        )
        _force_end_call(call, reason="stale_active_watchdog")
        call.refresh_from_db()
        self.assertEqual(call.status, CallSession.Status.FAILED)
        self.assertEqual(call.end_reason, "stale_active_watchdog")


class MyRecordingsListFilterTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username="rec_student",
            password="Pass1234!",
            user_type=USER_TYPE_STUDENT,
        )
        self.teacher = User.objects.create_user(
            username="rec_teacher",
            password="Pass1234!",
            user_type=USER_TYPE_TEACHER,
        )
        TeacherProfile.objects.create(user=self.teacher)
        self.call = CallSession.objects.create(
            student=self.student,
            teacher=self.teacher,
            session_type=CallSession.SessionType.AUDIO,
            provider=CallSession.Provider.AGORA,
            status=CallSession.Status.ENDED,
            started_at=timezone.now(),
            ended_at=timezone.now(),
            channel_name="ch_rec_1",
        )
        self.client = Client()

    def test_no_media_not_listed_as_playable_recording(self):
        CallRecording.objects.create(
            call_session=self.call,
            student=self.student,
            teacher=self.teacher,
            session_type=CallSession.SessionType.AUDIO,
            recording_status=CallRecording.RecordingStatus.NO_MEDIA,
        )
        self.client.force_login(self.student)
        url = reverse("calls_api:recordings-my")
        resp = self.client.get(
            url,
            HTTP_X_APP_VERSION="1.0.0",
            HTTP_X_APP_BUILD="1",
            HTTP_X_APP_PLATFORM="android",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["recordings"], [])
