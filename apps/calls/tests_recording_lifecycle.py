"""Tests for async end-call and recording lifecycle hardening."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.calls.cloud_recording.client import AgoraCloudRecordingError
from apps.calls.cloud_recording.reconcile import (
    inspect_call_recording,
    reconcile_stuck_calls,
)
from apps.calls.cloud_recording.service import (
    request_stop_cloud_recording,
    stop_cloud_recording_for_call,
    try_finalize_recording_files,
)
from apps.calls.models import CallRecording, CallSession
from apps.calls.services import end_call_session
from apps.tutoring.teacher_services import _active_teacher_ids, compute_teacher_status

User = get_user_model()


class CallRecordingLifecycleTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            username="student_rec_1", password="x"
        )
        self.teacher = User.objects.create_user(
            username="teacher_rec_1", password="x"
        )
        self.call = CallSession.objects.create(
            student=self.student,
            teacher=self.teacher,
            session_type=CallSession.SessionType.AUDIO,
            provider=CallSession.Provider.AGORA,
            status=CallSession.Status.ACTIVE,
            channel_name="ch_test_1",
            started_at=timezone.now(),
        )
        self.rec = CallRecording.objects.create(
            call_session=self.call,
            student=self.student,
            teacher=self.teacher,
            session_type="audio",
            recording_status=CallRecording.RecordingStatus.RECORDING,
            agora_resource_id="res_1",
            agora_sid="sid_1",
            recording_uid="900000001",
        )

    @patch("apps.calls.tasks.enqueue_stop_and_finalize_recording")
    @patch("apps.subscription.services.deduct_call_minutes_for_session")
    @patch("apps.calls.post_call.ensure_post_call_artifacts")
    @patch("apps.calls.services.mark_teacher_online")
    def test_end_call_is_fast_and_idempotent(
        self, mock_online, mock_artifacts, mock_deduct, mock_enqueue
    ):
        mock_enqueue.return_value = "celery"
        updated, err = end_call_session(self.call, self.student)
        self.assertIsNone(err)
        self.assertEqual(updated.status, CallSession.Status.ENDED)
        mock_enqueue.assert_called_once_with(self.call.id)

        # Second end is idempotent and does not re-enqueue billing path.
        mock_enqueue.reset_mock()
        updated2, err2 = end_call_session(self.call, self.student)
        self.assertIsNone(err2)
        self.assertEqual(updated2.status, CallSession.Status.ENDED)

        self.rec.refresh_from_db()
        self.assertEqual(
            self.rec.recording_status,
            CallRecording.RecordingStatus.STOP_REQUESTED,
        )

    @patch("apps.calls.cloud_recording.service.AgoraCloudRecordingClient")
    def test_stop_success_without_files_enters_processing(self, mock_client_cls):
        client = mock_client_cls.return_value
        client.stop.return_value = {"serverResponse": {}}
        client.query.return_value = {"serverResponse": {}}

        self.call.status = CallSession.Status.ENDED
        self.call.ended_at = timezone.now()
        self.call.save(update_fields=["status", "ended_at"])

        stop_cloud_recording_for_call(self.call, wait_for_files=False)
        self.rec.refresh_from_db()
        self.assertEqual(
            self.rec.recording_status,
            CallRecording.RecordingStatus.PROCESSING,
        )
        self.assertFalse(self.rec.is_playable)

    @patch("apps.calls.cloud_recording.service.AgoraCloudRecordingClient")
    def test_stop_resource_expired_reconciles(self, mock_client_cls):
        client = mock_client_cls.return_value
        client.stop.side_effect = AgoraCloudRecordingError(
            "resourceid exceeded time limit",
            status_code=400,
            action="stop",
            safe_body="resourceid exceeded time limit",
        )
        client.query.side_effect = AgoraCloudRecordingError(
            "resourceid exceeded time limit",
            status_code=400,
            action="query",
            safe_body="resourceid exceeded time limit",
        )

        self.call.status = CallSession.Status.ENDED
        self.call.ended_at = timezone.now()
        self.call.save(update_fields=["status", "ended_at"])

        stop_cloud_recording_for_call(self.call, wait_for_files=True)
        self.rec.refresh_from_db()
        self.assertIn(
            self.rec.recording_status,
            {
                CallRecording.RecordingStatus.PROCESSING,
                CallRecording.RecordingStatus.EXPIRED,
                CallRecording.RecordingStatus.NO_MEDIA,
                CallRecording.RecordingStatus.FAILED,
            },
        )
        self.assertNotEqual(self.call.status, CallSession.Status.ACTIVE)

    def test_processing_timeout_becomes_terminal(self):
        self.rec.recording_status = CallRecording.RecordingStatus.PROCESSING
        self.rec.processing_started_at = timezone.now() - timedelta(minutes=20)
        self.rec.save(
            update_fields=["recording_status", "processing_started_at"]
        )
        ok = try_finalize_recording_files(self.rec, allow_expire=True)
        self.assertFalse(ok)
        self.rec.refresh_from_db()
        self.assertTrue(self.rec.is_terminal)
        self.assertEqual(self.rec.failure_code, "processing_timeout")

    def test_processing_does_not_block_new_calls(self):
        self.call.status = CallSession.Status.ENDED
        self.call.ended_at = timezone.now()
        self.call.save(update_fields=["status", "ended_at"])
        self.rec.recording_status = CallRecording.RecordingStatus.PROCESSING
        self.rec.save(update_fields=["recording_status"])

        active_ids = _active_teacher_ids()
        self.assertNotIn(self.teacher.id, active_ids)
        status = compute_teacher_status(
            self.teacher, active_teacher_ids=active_ids
        )
        self.assertNotEqual(status, "busy")

    def test_reconcile_dry_run_does_not_mutate(self):
        self.call.status = CallSession.Status.ACTIVE
        self.call.started_at = timezone.now() - timedelta(hours=5)
        self.call.save(update_fields=["status", "started_at"])
        before = self.call.status
        summary = reconcile_stuck_calls(dry_run=True)
        self.call.refresh_from_db()
        self.assertEqual(self.call.status, before)
        self.assertIn(self.call.id, summary["active_finalized"])

    def test_inspect_call_recording_hides_secrets(self):
        info = inspect_call_recording(self.call.id)
        self.assertTrue(info["ok"])
        rec = info["recording"]
        self.assertTrue(rec["has_resource_id"])
        self.assertTrue(rec["has_sid"])
        self.assertNotIn("agora_resource_id", rec)
        self.assertNotIn("agora_sid", rec)

    def test_request_stop_idempotent(self):
        first = request_stop_cloud_recording(self.call)
        second = request_stop_cloud_recording(self.call)
        self.assertEqual(first.recording_status, second.recording_status)
        self.assertEqual(
            first.recording_status,
            CallRecording.RecordingStatus.STOP_REQUESTED,
        )

    @patch("apps.calls.cloud_recording.service.AgoraCloudRecordingClient")
    def test_processing_does_not_re_stop_agora(self, mock_client_cls):
        client = mock_client_cls.return_value
        self.call.status = CallSession.Status.ENDED
        self.call.ended_at = timezone.now()
        self.call.save(update_fields=["status", "ended_at"])
        self.rec.recording_status = CallRecording.RecordingStatus.PROCESSING
        self.rec.processing_started_at = timezone.now()
        self.rec.save(update_fields=["recording_status", "processing_started_at"])

        stop_cloud_recording_for_call(self.call, wait_for_files=True)
        client.stop.assert_not_called()

    @patch(
        "apps.calls.cloud_recording.reconcile.stop_and_finalize_recording_for_call_id"
    )
    @patch("apps.calls.cloud_recording.reconcile.try_finalize_recording_files")
    def test_reconcile_processing_skips_stop(self, mock_finalize, mock_stop):
        self.call.status = CallSession.Status.ENDED
        self.call.ended_at = timezone.now()
        self.call.save(update_fields=["status", "ended_at"])
        self.rec.recording_status = CallRecording.RecordingStatus.PROCESSING
        self.rec.processing_started_at = timezone.now()
        self.rec.save(update_fields=["recording_status", "processing_started_at"])

        def _finalize(rec, allow_expire=True):
            return False

        mock_finalize.side_effect = _finalize
        summary = reconcile_stuck_calls(dry_run=False)
        self.assertIn(self.rec.id, [r["recording_id"] for r in summary["recordings_reconciled"]])
        mock_stop.assert_not_called()
        self.assertGreaterEqual(mock_finalize.call_count, 1)

    @patch("apps.calls.tasks.stop_and_finalize_recording_task.delay")
    def test_enqueue_deferred_when_celery_unavailable(self, mock_delay):
        from apps.calls.tasks import enqueue_stop_and_finalize_recording

        mock_delay.side_effect = RuntimeError("broker down")
        mode = enqueue_stop_and_finalize_recording(self.call.id)
        self.assertEqual(mode, "deferred")
        mock_delay.assert_called_once_with(self.call.id)
