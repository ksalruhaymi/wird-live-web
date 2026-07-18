"""Celery registration and recording-stop task behaviour."""

from __future__ import annotations

from unittest.mock import patch

from celery import current_app
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.calls.models import CallRecording, CallSession
from apps.calls.services import end_call_session
from apps.calls.tasks import (
    enqueue_stop_and_finalize_recording,
    stop_and_finalize_recording_task,
)

User = get_user_model()

STOP_TASK_NAME = "apps.calls.tasks.stop_and_finalize_recording"


class CeleryRecordingTaskTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username="celery_student", password="x"
        )
        self.teacher = User.objects.create_user(
            username="celery_teacher", password="x"
        )
        self.call = CallSession.objects.create(
            student=self.student,
            teacher=self.teacher,
            session_type=CallSession.SessionType.AUDIO,
            provider=CallSession.Provider.AGORA,
            status=CallSession.Status.ACTIVE,
            channel_name="ch_celery_1",
            started_at=timezone.now(),
        )
        self.rec = CallRecording.objects.create(
            call_session=self.call,
            student=self.student,
            teacher=self.teacher,
            session_type="audio",
            recording_status=CallRecording.RecordingStatus.RECORDING,
            agora_resource_id="res_celery_1",
            agora_sid="sid_celery_1",
            recording_uid="900000101",
        )

    def test_stop_task_is_registered(self):
        import apps.calls.tasks  # noqa: F401
        from config.celery import app as celery_app

        celery_app.loader.import_default_modules()
        self.assertIn(STOP_TASK_NAME, current_app.tasks)
        self.assertIn(STOP_TASK_NAME, celery_app.tasks)
        self.assertIs(
            celery_app.tasks[STOP_TASK_NAME],
            current_app.tasks[STOP_TASK_NAME],
        )

    @patch("apps.calls.tasks.stop_and_finalize_recording_task.delay")
    @patch("apps.subscription.services.deduct_call_minutes_for_session")
    @patch("apps.calls.post_call.ensure_post_call_artifacts")
    @patch("apps.calls.services.mark_teacher_online")
    def test_enqueue_failure_leaves_stop_requested(
        self, _online, _artifacts, _deduct, mock_delay
    ):
        mock_delay.side_effect = RuntimeError("broker unavailable")
        updated, err = end_call_session(self.call, self.student)
        self.assertIsNone(err)
        self.assertEqual(updated.status, CallSession.Status.ENDED)
        self.rec.refresh_from_db()
        self.assertEqual(
            self.rec.recording_status,
            CallRecording.RecordingStatus.STOP_REQUESTED,
        )
        self.assertEqual(
            enqueue_stop_and_finalize_recording(self.call.id),
            "deferred",
        )

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("apps.calls.cloud_recording.service.AgoraCloudRecordingClient")
    def test_stop_task_is_idempotent(self, mock_client_cls):
        client = mock_client_cls.return_value
        client.stop.return_value = {"serverResponse": {}}
        client.query.return_value = {"serverResponse": {}}

        self.call.status = CallSession.Status.ENDED
        self.call.ended_at = timezone.now()
        self.call.save(update_fields=["status", "ended_at"])
        self.rec.recording_status = CallRecording.RecordingStatus.STOP_REQUESTED
        self.rec.stop_requested_at = timezone.now()
        self.rec.save(update_fields=["recording_status", "stop_requested_at"])

        first = stop_and_finalize_recording_task(self.call.id)
        self.rec.refresh_from_db()
        status_after_first = self.rec.recording_status
        attempts_after_first = self.rec.stop_attempts

        second = stop_and_finalize_recording_task(self.call.id)
        self.rec.refresh_from_db()

        self.assertTrue(first.get("ok"))
        self.assertTrue(second.get("ok"))
        # After first run we should be past Agora stop (processing/terminal).
        self.assertNotEqual(
            status_after_first,
            CallRecording.RecordingStatus.STOP_REQUESTED,
        )
        # Second run must not issue another Agora stop once in processing+.
        if status_after_first == CallRecording.RecordingStatus.PROCESSING:
            self.assertEqual(client.stop.call_count, 1)
            self.assertEqual(self.rec.stop_attempts, attempts_after_first)
        self.assertEqual(self.rec.recording_status, status_after_first)
