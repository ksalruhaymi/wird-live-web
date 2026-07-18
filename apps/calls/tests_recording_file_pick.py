"""Tests for playable recording object key selection."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.calls.cloud_recording.service import (
    _mark_recording_ready,
    _pick_object_key,
)
from apps.calls.models import CallRecording, CallSession
from apps.calls.post_call import recording_to_payload
from apps.calls.recording_storage import (
    is_playable_object_key,
    pick_best_playable_object_key,
)

User = get_user_model()


class RecordingFilePickTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(username="pick_s", password="x")
        self.teacher = User.objects.create_user(username="pick_t", password="x")
        self.call = CallSession.objects.create(
            student=self.student,
            teacher=self.teacher,
            session_type=CallSession.SessionType.AUDIO,
            provider=CallSession.Provider.AGORA,
            status=CallSession.Status.ENDED,
            channel_name="ch_pick_1",
            started_at=timezone.now(),
            ended_at=timezone.now(),
        )
        self.rec = CallRecording.objects.create(
            call_session=self.call,
            student=self.student,
            teacher=self.teacher,
            session_type="audio",
            recording_status=CallRecording.RecordingStatus.PROCESSING,
        )

    def test_mp4_preferred_over_m3u8(self):
        files = [
            {"fileName": "wird-live/call_call_80_s8_t2/playlist.m3u8", "isPlayable": True},
            {"fileName": "wird-live/call_call_80_s8_t2/final_0.mp4"},
            {"fileName": "wird-live/call_call_80_s8_t2/seg_001.ts"},
        ]
        key = _pick_object_key(files)
        self.assertTrue(key.endswith(".mp4"))
        self.assertTrue(is_playable_object_key(key))

    def test_m3u8_only_not_playable(self):
        key = _pick_object_key(
            [{"fileName": "wird-live/x/index.m3u8", "isPlayable": True}]
        )
        self.assertEqual(key, "")
        self.assertFalse(is_playable_object_key("wird-live/x/index.m3u8"))

    def test_ts_m2t_only_not_playable(self):
        key = pick_best_playable_object_key(
            [
                "wird-live/x/a.ts",
                "wird-live/x/b.m2t",
                "wird-live/x/c.m2ts",
            ]
        )
        self.assertEqual(key, "")
        self.assertFalse(is_playable_object_key("wird-live/x/a.ts"))
        self.assertFalse(is_playable_object_key("wird-live/x/b.m2t"))

    def test_valid_mp4_marks_completed_playable(self):
        mp4 = "wird-live/call_call_80_s8_t2/final_0.mp4"
        _mark_recording_ready(self.rec, mp4)
        self.rec.refresh_from_db()
        self.assertEqual(
            self.rec.recording_status, CallRecording.RecordingStatus.COMPLETED
        )
        self.assertEqual(self.rec.recording_object_key, mp4)
        self.assertTrue(self.rec.is_playable)
        payload = recording_to_payload(self.rec, self.student)
        self.assertTrue(payload["is_playable"])
        self.assertTrue(payload["has_recording"])
        self.assertEqual(payload["recording_status"], "completed")

    def test_m3u8_key_rejected_for_completed(self):
        _mark_recording_ready(self.rec, "wird-live/x/index.m3u8")
        self.rec.refresh_from_db()
        self.assertNotEqual(
            self.rec.recording_status, CallRecording.RecordingStatus.COMPLETED
        )
        self.assertFalse(self.rec.is_playable)

    def test_completed_with_m3u8_in_db_not_playable_in_api(self):
        self.rec.recording_status = CallRecording.RecordingStatus.COMPLETED
        self.rec.recording_object_key = "wird-live/x/index.m3u8"
        self.rec.save(
            update_fields=["recording_status", "recording_object_key"]
        )
        self.assertFalse(self.rec.is_playable)
        payload = recording_to_payload(self.rec, self.student)
        self.assertFalse(payload["is_playable"])
        self.assertFalse(payload["has_recording"])
