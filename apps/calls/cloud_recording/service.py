"""Orchestrates Agora Cloud Recording for call sessions."""

from __future__ import annotations

import logging
import time
from urllib.parse import urljoin

from django.conf import settings
from django.utils import timezone

from apps.calls.cloud_recording.client import (
    AgoraCloudRecordingClient,
    AgoraCloudRecordingError,
)
from apps.calls.models import CallRecording, CallSession
from apps.calls.token_builder import (
    agora_credentials_configured,
    build_agora_rtc_token,
    uses_agora_rtc,
)

logger = logging.getLogger(__name__)


def cloud_recording_configured() -> bool:
    if not agora_credentials_configured():
        return False
    required = (
        "AGORA_CUSTOMER_ID",
        "AGORA_CUSTOMER_SECRET",
        "AGORA_RECORDING_STORAGE_BUCKET",
        "AGORA_RECORDING_STORAGE_ACCESS_KEY",
        "AGORA_RECORDING_STORAGE_SECRET_KEY",
    )
    for name in required:
        if not (getattr(settings, name, "") or "").strip():
            return False

    vendor = int(getattr(settings, "AGORA_RECORDING_STORAGE_VENDOR", 0) or 0)
    if vendor == 11 and not (
        getattr(settings, "AGORA_RECORDING_STORAGE_ENDPOINT", "") or ""
    ).strip():
        return False
    return True


def recording_uid_for_call(call: CallSession) -> str:
    base = int(getattr(settings, "AGORA_RECORDING_UID", 900000001) or 900000001)
    # Spread UIDs per call while staying in a dedicated high range.
    uid = base + (call.id % 100_000)
    return str(uid)


def ensure_recording_row(call: CallSession) -> CallRecording:
    rec, _ = CallRecording.objects.get_or_create(
        call_session=call,
        defaults={
            "student_id": call.student_id,
            "teacher_id": call.teacher_id,
            "session_type": call.session_type,
            "started_at": call.started_at,
        },
    )
    return rec


def start_cloud_recording_for_call(call: CallSession) -> None:
    """Start Agora Cloud Recording when a call becomes active (best-effort)."""
    if not uses_agora_rtc(call):
        return
    if not cloud_recording_configured():
        rec = ensure_recording_row(call)
        if rec.recording_status == CallRecording.RecordingStatus.IDLE:
            rec.recording_status = CallRecording.RecordingStatus.SKIPPED
            rec.recording_error = "Cloud recording is not configured."
            rec.save(update_fields=["recording_status", "recording_error"])
        return

    rec = ensure_recording_row(call)
    if rec.recording_status == CallRecording.RecordingStatus.RECORDING:
        return

    channel = (call.channel_name or "").strip()
    if not channel:
        logger.warning("Cloud recording skipped for call %s: missing channel", call.id)
        return

    recording_uid = recording_uid_for_call(call)
    rec.recording_status = CallRecording.RecordingStatus.STARTING
    rec.recording_uid = recording_uid
    rec.started_at = call.started_at or timezone.now()
    rec.save(
        update_fields=["recording_status", "recording_uid", "started_at"]
    )

    client = AgoraCloudRecordingClient()
    try:
        resource_id = client.acquire(
            channel_name=channel, recording_uid=recording_uid
        )
        rtc_token = build_agora_rtc_token(
            channel_name=channel, uid=int(recording_uid)
        )
        sid = client.start(
            resource_id=resource_id,
            channel_name=channel,
            recording_uid=recording_uid,
            rtc_token=rtc_token,
            session_type=call.session_type,
        )
    except AgoraCloudRecordingError as exc:
        rec.recording_status = CallRecording.RecordingStatus.FAILED
        rec.recording_error = str(exc)[:500]
        rec.save(update_fields=["recording_status", "recording_error"])
        logger.warning(
            "Cloud recording start failed for call %s: %s", call.id, exc
        )
        return

    rec.agora_resource_id = resource_id
    rec.agora_sid = sid
    rec.provider_recording_id = sid
    rec.recording_status = CallRecording.RecordingStatus.RECORDING
    rec.recording_error = ""
    rec.save(
        update_fields=[
            "agora_resource_id",
            "agora_sid",
            "provider_recording_id",
            "recording_status",
            "recording_error",
        ]
    )
    logger.info("Cloud recording started for call %s", call.id)


def stop_cloud_recording_for_call(call: CallSession) -> None:
    """Stop Agora Cloud Recording and persist file metadata (best-effort)."""
    if not uses_agora_rtc(call):
        return

    try:
        rec = call.recording
    except CallRecording.DoesNotExist:
        rec = ensure_recording_row(call)

    if rec.recording_status not in {
        CallRecording.RecordingStatus.RECORDING,
        CallRecording.RecordingStatus.STARTING,
    }:
        _sync_recording_times_from_call(rec, call)
        return

    resource_id = (rec.agora_resource_id or "").strip()
    sid = (rec.agora_sid or "").strip()
    channel = (call.channel_name or "").strip()
    recording_uid = (rec.recording_uid or recording_uid_for_call(call)).strip()

    if not resource_id or not sid or not channel:
        rec.recording_status = CallRecording.RecordingStatus.FAILED
        rec.recording_error = "Missing Agora recording session identifiers."
        rec.save(update_fields=["recording_status", "recording_error"])
        _sync_recording_times_from_call(rec, call)
        return

    rec.recording_status = CallRecording.RecordingStatus.STOPPING
    rec.save(update_fields=["recording_status"])

    client = AgoraCloudRecordingClient()
    stop_payload: dict = {}
    try:
        stop_payload = client.stop(
            resource_id=resource_id,
            sid=sid,
            channel_name=channel,
            recording_uid=recording_uid,
        )
    except AgoraCloudRecordingError as exc:
        rec.recording_status = CallRecording.RecordingStatus.FAILED
        rec.recording_error = str(exc)[:500]
        rec.save(update_fields=["recording_status", "recording_error"])
        logger.warning("Cloud recording stop failed for call %s: %s", call.id, exc)
        _sync_recording_times_from_call(rec, call)
        return

    file_list = _extract_file_list(stop_payload)
    if not file_list:
        file_list = _query_file_list_with_retry(client, resource_id, sid)

    file_url = _pick_playback_url(file_list)
    rec.ended_at = call.ended_at or timezone.now()
    rec.duration_seconds = _duration_seconds(call, rec)
    if file_url:
        rec.recording_url = file_url
        rec.recording_status = CallRecording.RecordingStatus.COMPLETED
        rec.recording_error = ""
    else:
        rec.recording_status = CallRecording.RecordingStatus.COMPLETED
        rec.recording_error = "Recording stopped but no playable file was returned."
    rec.save(
        update_fields=[
            "recording_url",
            "ended_at",
            "duration_seconds",
            "recording_status",
            "recording_error",
        ]
    )
    logger.info("Cloud recording stopped for call %s", call.id)


def _sync_recording_times_from_call(rec: CallRecording, call: CallSession) -> None:
    updates: list[str] = []
    if call.ended_at and rec.ended_at != call.ended_at:
        rec.ended_at = call.ended_at
        updates.append("ended_at")
    duration = _duration_seconds(call, rec)
    if duration and rec.duration_seconds != duration:
        rec.duration_seconds = duration
        updates.append("duration_seconds")
    if updates:
        rec.save(update_fields=updates)


def _duration_seconds(call: CallSession, rec: CallRecording) -> int:
    if call.started_at and call.ended_at:
        return max(0, int((call.ended_at - call.started_at).total_seconds()))
    if rec.started_at and rec.ended_at:
        return max(0, int((rec.ended_at - rec.started_at).total_seconds()))
    return 0


def _query_file_list_with_retry(
    client: AgoraCloudRecordingClient,
    resource_id: str,
    sid: str,
    *,
    attempts: int = 3,
    delay_seconds: float = 2.0,
) -> list[dict]:
    for attempt in range(attempts):
        if attempt:
            time.sleep(delay_seconds)
        try:
            payload = client.query(resource_id=resource_id, sid=sid)
        except AgoraCloudRecordingError:
            continue
        files = _extract_file_list(payload)
        if files:
            return files
    return []


def _extract_file_list(payload: dict) -> list[dict]:
    server = payload.get("serverResponse") or {}
    raw = server.get("fileList")
    if isinstance(raw, list):
        return [f for f in raw if isinstance(f, dict)]
    if isinstance(raw, str) and raw.strip():
        return [{"fileName": raw.strip()}]

    for entry in server.get("extensionServiceState") or []:
        if not isinstance(entry, dict):
            continue
        inner = entry.get("payload") or entry.get("playload") or {}
        if not isinstance(inner, dict):
            continue
        nested = inner.get("fileList")
        if isinstance(nested, list):
            return [f for f in nested if isinstance(f, dict)]
    return []


def _pick_playback_url(file_list: list[dict]) -> str:
    if not file_list:
        return ""

    def score(item: dict) -> tuple[int, int]:
        name = (item.get("fileName") or item.get("filename") or "").lower()
        track = (item.get("trackType") or "").lower()
        playable = 1 if item.get("isPlayable") else 0
        is_mp4 = 1 if name.endswith(".mp4") else 0
        is_audio = 1 if track == "audio" or name.endswith(".mp4") else 0
        is_video = 1 if track in {"video", "audio_and_video"} else 0
        return (playable, is_mp4 + is_audio + is_video)

    best = sorted(file_list, key=score, reverse=True)[0]
    file_name = (best.get("fileName") or best.get("filename") or "").strip()
    if not file_name:
        return ""

    base = (getattr(settings, "AGORA_RECORDING_PUBLIC_BASE_URL", "") or "").strip()
    if not base:
        return ""
    if not base.endswith("/"):
        base = f"{base}/"
    return urljoin(base, file_name.lstrip("/"))
