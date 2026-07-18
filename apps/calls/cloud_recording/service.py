"""Orchestrates Agora Cloud Recording for call sessions."""

from __future__ import annotations

import logging
import time
from datetime import timedelta
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

# Keep HTTP end-call fast: heavy work runs async.
MAX_INLINE_QUERY_ATTEMPTS = 2
MAX_INLINE_QUERY_DELAY_SECONDS = 1.0
MAX_BACKGROUND_QUERY_ATTEMPTS = 4
MAX_BACKGROUND_QUERY_DELAY_SECONDS = 2.0
PROCESSING_TIMEOUT = timedelta(minutes=10)
STOPPING_TIMEOUT = timedelta(minutes=5)
STARTING_TIMEOUT = timedelta(minutes=3)
MAX_STOP_ATTEMPTS = 3


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
    from apps.calls.recording_consent import is_demo_protected_call

    call = CallSession.objects.select_related("student", "teacher").get(pk=call.pk)
    if is_demo_protected_call(call):
        logger.info(
            "Skipping cloud recording for demo-protected call_id=%s",
            call.id,
        )
        rec = ensure_recording_row(call)
        if rec.recording_status in {
            CallRecording.RecordingStatus.IDLE,
            CallRecording.RecordingStatus.STARTING,
        }:
            rec.recording_status = CallRecording.RecordingStatus.SKIPPED
            rec.recording_error = "Recording is not allowed for demo calls."
            rec.finalized_at = timezone.now()
            rec.save(
                update_fields=[
                    "recording_status",
                    "recording_error",
                    "finalized_at",
                ]
            )
        return

    if not uses_agora_rtc(call):
        return
    if not cloud_recording_configured():
        rec = ensure_recording_row(call)
        if rec.recording_status == CallRecording.RecordingStatus.IDLE:
            rec.recording_status = CallRecording.RecordingStatus.SKIPPED
            rec.recording_error = "Cloud recording is not configured."
            rec.finalized_at = timezone.now()
            rec.save(
                update_fields=[
                    "recording_status",
                    "recording_error",
                    "finalized_at",
                ]
            )
        return

    rec = ensure_recording_row(call)
    if rec.recording_status in {
        CallRecording.RecordingStatus.RECORDING,
        CallRecording.RecordingStatus.STOP_REQUESTED,
        CallRecording.RecordingStatus.STOPPING,
        CallRecording.RecordingStatus.PROCESSING,
        CallRecording.RecordingStatus.COMPLETED,
    }:
        return

    channel = (call.channel_name or "").strip()
    if not channel:
        logger.warning("Cloud recording skipped for call %s: missing channel", call.id)
        return

    recording_uid = recording_uid_for_call(call)
    rec.recording_status = CallRecording.RecordingStatus.STARTING
    rec.recording_uid = recording_uid
    rec.started_at = call.started_at or timezone.now()
    rec.save(update_fields=["recording_status", "recording_uid", "started_at"])

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
        _mark_recording_terminal(
            rec,
            CallRecording.RecordingStatus.FAILED,
            failure_code=_failure_code_from_exc(exc),
            message=str(exc)[:500],
        )
        logger.warning(
            "recording_stop_failed action=start call_id=%s code=%s status=%s",
            call.id,
            _failure_code_from_exc(exc),
            exc.status_code,
        )
        return

    rec.agora_resource_id = resource_id
    rec.agora_sid = sid
    rec.provider_recording_id = sid
    rec.recording_status = CallRecording.RecordingStatus.RECORDING
    rec.recording_error = ""
    rec.failure_code = ""
    rec.save(
        update_fields=[
            "agora_resource_id",
            "agora_sid",
            "provider_recording_id",
            "recording_status",
            "recording_error",
            "failure_code",
        ]
    )
    logger.info("recording_start_success call_id=%s", call.id)


def request_stop_cloud_recording(call: CallSession) -> CallRecording:
    """Mark recording stop requested (fast, DB-only). Idempotent."""
    rec = ensure_recording_row(call)
    if rec.is_terminal:
        return rec
    if rec.recording_status in {
        CallRecording.RecordingStatus.STOP_REQUESTED,
        CallRecording.RecordingStatus.STOPPING,
        CallRecording.RecordingStatus.PROCESSING,
    }:
        return rec

    now = timezone.now()
    if rec.recording_status in {
        CallRecording.RecordingStatus.IDLE,
        CallRecording.RecordingStatus.SKIPPED,
    }:
        _mark_recording_terminal(
            rec,
            CallRecording.RecordingStatus.SKIPPED,
            failure_code="not_started",
            message="No active cloud recording to stop.",
        )
        return rec

    rec.recording_status = CallRecording.RecordingStatus.STOP_REQUESTED
    rec.stop_requested_at = now
    rec.recording_error = ""
    rec.save(
        update_fields=["recording_status", "stop_requested_at", "recording_error"]
    )
    return rec


def stop_cloud_recording_for_call(
    call: CallSession,
    *,
    wait_for_files: bool = False,
) -> None:
    """Stop Agora Cloud Recording.

    By default does a single stop call and leaves PROCESSING if files are not
    ready yet (for async finalization). Set wait_for_files=True only from
    background workers with limited retries.
    """
    if not uses_agora_rtc(call):
        return

    try:
        rec = call.recording
    except CallRecording.DoesNotExist:
        rec = ensure_recording_row(call)

    if rec.is_terminal and rec.is_playable:
        return
    if rec.is_terminal:
        return

    # Already past Agora stop — only query/storage finalize (no re-stop).
    if rec.recording_status == CallRecording.RecordingStatus.PROCESSING:
        try_finalize_recording_files(rec, allow_expire=True)
        return

    if rec.recording_status not in {
        CallRecording.RecordingStatus.RECORDING,
        CallRecording.RecordingStatus.STARTING,
        CallRecording.RecordingStatus.STOP_REQUESTED,
        CallRecording.RecordingStatus.STOPPING,
    }:
        _sync_recording_times_from_call(rec, call)
        return

    resource_id = (rec.agora_resource_id or "").strip()
    sid = (rec.agora_sid or "").strip()
    channel = (call.channel_name or "").strip()
    recording_uid = (rec.recording_uid or recording_uid_for_call(call)).strip()

    if not resource_id or not sid or not channel:
        _mark_recording_terminal(
            rec,
            CallRecording.RecordingStatus.FAILED,
            failure_code="missing_session_ids",
            message="Missing Agora recording session identifiers.",
        )
        _sync_recording_times_from_call(rec, call)
        return

    if rec.stop_attempts >= MAX_STOP_ATTEMPTS and rec.recording_status in {
        CallRecording.RecordingStatus.STOP_REQUESTED,
        CallRecording.RecordingStatus.STOPPING,
    }:
        # Exhausted stop attempts — reconcile via query/storage only.
        _enter_processing(rec, call, message="Stop attempts exhausted; reconciling.")
        if wait_for_files:
            try_finalize_recording_files(rec, allow_expire=True)
        return

    now = timezone.now()
    rec.recording_status = CallRecording.RecordingStatus.STOPPING
    rec.stop_attempts = (rec.stop_attempts or 0) + 1
    if not rec.stop_requested_at:
        rec.stop_requested_at = now
    rec.save(
        update_fields=["recording_status", "stop_attempts", "stop_requested_at"]
    )

    client = AgoraCloudRecordingClient()
    stop_payload: dict = {}
    try:
        stop_payload = client.stop(
            resource_id=resource_id,
            sid=sid,
            channel_name=channel,
            recording_uid=recording_uid,
        )
        logger.info(
            "recording_stop_success call_id=%s attempt=%s",
            call.id,
            rec.stop_attempts,
        )
    except AgoraCloudRecordingError as exc:
        code = _failure_code_from_exc(exc)
        if _is_already_stopped_or_expired(exc):
            logger.warning(
                "recording_stop_reconcile call_id=%s code=%s status=%s",
                call.id,
                code,
                exc.status_code,
            )
            _enter_processing(
                rec,
                call,
                message=f"Stop returned {code}; reconciling files.",
            )
            if wait_for_files:
                try_finalize_recording_files(rec, allow_expire=True)
            return

        if rec.stop_attempts < MAX_STOP_ATTEMPTS and _is_transient(exc):
            rec.recording_status = CallRecording.RecordingStatus.STOP_REQUESTED
            rec.failure_code = code
            rec.recording_error = str(exc)[:500]
            rec.next_retry_at = timezone.now() + timedelta(seconds=15 * rec.stop_attempts)
            rec.save(
                update_fields=[
                    "recording_status",
                    "failure_code",
                    "recording_error",
                    "next_retry_at",
                ]
            )
            raise

        terminal = (
            CallRecording.RecordingStatus.EXPIRED
            if code in {"resource_expired", "not_found"}
            else CallRecording.RecordingStatus.FAILED
        )
        _mark_recording_terminal(
            rec,
            terminal,
            failure_code=code,
            message=str(exc)[:500],
        )
        logger.warning(
            "recording_stop_failed call_id=%s code=%s status=%s",
            call.id,
            code,
            exc.status_code,
        )
        _sync_recording_times_from_call(rec, call)
        return

    rec.stopped_at = timezone.now()
    file_list = _extract_file_list(stop_payload)
    if not file_list and wait_for_files:
        file_list = _query_file_list_with_retry(
            client,
            resource_id,
            sid,
            rec=rec,
            attempts=MAX_BACKGROUND_QUERY_ATTEMPTS,
            delay_seconds=MAX_BACKGROUND_QUERY_DELAY_SECONDS,
        )
    elif not file_list:
        # One quick query only — do not block HTTP callers.
        file_list = _query_file_list_with_retry(
            client,
            resource_id,
            sid,
            rec=rec,
            attempts=MAX_INLINE_QUERY_ATTEMPTS,
            delay_seconds=MAX_INLINE_QUERY_DELAY_SECONDS,
        )

    object_key = _pick_object_key(file_list)
    rec.ended_at = call.ended_at or timezone.now()
    rec.duration_seconds = _duration_seconds(call, rec)
    if object_key:
        _mark_recording_ready(rec, object_key)
        logger.info("recording_ready call_id=%s", call.id)
    else:
        _enter_processing(
            rec,
            call,
            message="Recording stopped; waiting for playable file.",
        )
        logger.info("recording_processing call_id=%s", call.id)


def stop_and_finalize_recording_for_call_id(call_id: int) -> dict:
    call = CallSession.objects.select_related("recording").get(pk=call_id)
    stop_cloud_recording_for_call(call, wait_for_files=True)
    call.refresh_from_db()
    try:
        rec = call.recording
    except CallRecording.DoesNotExist:
        return {"ok": True, "call_id": call_id, "recording_status": "missing"}
    rec.refresh_from_db()
    # Rematch even when terminal-but-not-playable (e.g. completed with m3u8).
    if (not rec.is_terminal) or (not rec.is_playable):
        try_finalize_recording_files(rec, allow_expire=True)
        rec.refresh_from_db()
    return {
        "ok": True,
        "call_id": call_id,
        "recording_status": rec.recording_status,
        "is_playable": rec.is_playable,
    }


def mark_recording_failed_for_call_id(
    call_id: int,
    *,
    failure_code: str,
    message: str,
) -> None:
    try:
        rec = CallRecording.objects.get(call_session_id=call_id)
    except CallRecording.DoesNotExist:
        return
    if rec.is_terminal:
        return
    _mark_recording_terminal(
        rec,
        CallRecording.RecordingStatus.FAILED,
        failure_code=failure_code,
        message=message[:500],
    )


def try_finalize_recording_files(
    rec: CallRecording,
    *,
    allow_expire: bool = True,
) -> bool:
    """Best-effort: re-query Agora / rematch R2 for a playable object key.

    Returns True when a playable object key was persisted.
    """
    from apps.calls.recording_storage import (
        find_playable_object_key_for_recording,
        is_playable_object_key,
    )

    existing_key = (rec.recording_object_key or "").strip()
    if existing_key and is_playable_object_key(existing_key):
        if rec.recording_status != CallRecording.RecordingStatus.COMPLETED:
            _mark_recording_ready(rec, existing_key)
        return True

    # Non-playable key (e.g. m3u8) or missing: try rematch from R2 siblings first.
    rematched = find_playable_object_key_for_recording(rec)
    if rematched and is_playable_object_key(rematched):
        _mark_recording_ready(rec, rematched)
        logger.info(
            "recording_ready call_id=%s via=r2_rematch key_ext=%s",
            rec.call_session_id,
            rematched.rsplit(".", 1)[-1],
        )
        return True

    if rec.is_terminal and existing_key and not is_playable_object_key(existing_key):
        # Completed-with-playlist: keep row, but not playable until rematch succeeds.
        return False

    if rec.is_terminal:
        return False

    # Expire stuck preparing states so clients never spin forever.
    if allow_expire and _should_expire_preparing(rec):
        _mark_recording_terminal(
            rec,
            CallRecording.RecordingStatus.EXPIRED
            if rec.recording_status
            in {
                CallRecording.RecordingStatus.PROCESSING,
                CallRecording.RecordingStatus.STOPPING,
                CallRecording.RecordingStatus.STOP_REQUESTED,
            }
            else CallRecording.RecordingStatus.FAILED,
            failure_code="processing_timeout",
            message="Recording preparation timed out.",
        )
        logger.warning(
            "recording_processing_timeout call_id=%s status=%s",
            rec.call_session_id,
            rec.recording_status,
        )
        return False

    resource_id = (rec.agora_resource_id or "").strip()
    sid = (rec.agora_sid or "").strip()
    if not resource_id or not sid:
        return False

    client = AgoraCloudRecordingClient()
    try:
        file_list = _query_file_list_with_retry(
            client,
            resource_id,
            sid,
            rec=rec,
            attempts=2,
            delay_seconds=1.0,
        )
    except AgoraCloudRecordingError as exc:
        code = _failure_code_from_exc(exc)
        if allow_expire and code in {"resource_expired", "not_found"}:
            _mark_recording_terminal(
                rec,
                CallRecording.RecordingStatus.NO_MEDIA
                if code == "not_found"
                else CallRecording.RecordingStatus.EXPIRED,
                failure_code=code,
                message=str(exc)[:500],
            )
            logger.warning(
                "recording_expired call_id=%s code=%s",
                rec.call_session_id,
                code,
            )
        return False

    object_key = _pick_object_key(file_list)
    if not object_key:
        return False

    _mark_recording_ready(rec, object_key)
    logger.info("recording_ready call_id=%s via=finalize", rec.call_session_id)
    return True


def _should_expire_preparing(rec: CallRecording) -> bool:
    now = timezone.now()
    if rec.recording_status == CallRecording.RecordingStatus.PROCESSING:
        started = rec.processing_started_at or rec.stop_requested_at or rec.stopped_at
        return bool(started and now - started >= PROCESSING_TIMEOUT)
    if rec.recording_status in {
        CallRecording.RecordingStatus.STOPPING,
        CallRecording.RecordingStatus.STOP_REQUESTED,
    }:
        anchor = rec.stop_requested_at or rec.stopped_at
        return bool(anchor and now - anchor >= STOPPING_TIMEOUT)
    if rec.recording_status == CallRecording.RecordingStatus.STARTING:
        started = rec.started_at
        return bool(started and now - started >= STARTING_TIMEOUT)
    if rec.recording_status == CallRecording.RecordingStatus.RECORDING:
        # Recording while call already ended for a long time.
        call = getattr(rec, "call_session", None)
        if call and call.ended_at and now - call.ended_at >= STOPPING_TIMEOUT:
            return True
    return False


def _enter_processing(rec: CallRecording, call: CallSession, *, message: str) -> None:
    now = timezone.now()
    rec.recording_status = CallRecording.RecordingStatus.PROCESSING
    rec.processing_started_at = rec.processing_started_at or now
    rec.stopped_at = rec.stopped_at or now
    rec.ended_at = call.ended_at or now
    rec.duration_seconds = _duration_seconds(call, rec)
    rec.recording_error = message[:500]
    rec.save(
        update_fields=[
            "recording_status",
            "processing_started_at",
            "stopped_at",
            "ended_at",
            "duration_seconds",
            "recording_error",
        ]
    )


def _mark_recording_ready(rec: CallRecording, object_key: str) -> None:
    from apps.calls.recording_storage import is_playable_object_key

    key = (object_key or "").strip().lstrip("/")
    if not key or not is_playable_object_key(key):
        logger.warning(
            "recording_ready_rejected call_id=%s reason=non_playable_key",
            getattr(rec, "call_session_id", None),
        )
        return

    now = timezone.now()
    rec.recording_object_key = key
    rec.recording_url = _legacy_public_url(key)
    rec.recording_status = CallRecording.RecordingStatus.COMPLETED
    rec.recording_error = ""
    rec.failure_code = ""
    rec.ready_at = now
    rec.finalized_at = now
    rec.save(
        update_fields=[
            "recording_object_key",
            "recording_url",
            "recording_status",
            "recording_error",
            "failure_code",
            "ready_at",
            "finalized_at",
        ]
    )


def _mark_recording_terminal(
    rec: CallRecording,
    status: str,
    *,
    failure_code: str = "",
    message: str = "",
) -> None:
    now = timezone.now()
    rec.recording_status = status
    rec.failure_code = (failure_code or "")[:64]
    rec.recording_error = (message or "")[:500]
    rec.finalized_at = now
    if status in {
        CallRecording.RecordingStatus.FAILED,
        CallRecording.RecordingStatus.EXPIRED,
        CallRecording.RecordingStatus.NO_MEDIA,
    }:
        rec.failed_at = now
    rec.save(
        update_fields=[
            "recording_status",
            "failure_code",
            "recording_error",
            "finalized_at",
            "failed_at",
        ]
    )


def _failure_code_from_exc(exc: AgoraCloudRecordingError) -> str:
    body = (exc.safe_body or str(exc) or "").lower()
    if "resourceid exceeded time limit" in body or "resource expired" in body:
        return "resource_expired"
    if exc.status_code == 404:
        return "not_found"
    if exc.status_code and 500 <= exc.status_code < 600:
        return "agora_5xx"
    if exc.status_code and 400 <= exc.status_code < 500:
        return "agora_4xx"
    return exc.action or "agora_error"


def _is_already_stopped_or_expired(exc: AgoraCloudRecordingError) -> bool:
    code = _failure_code_from_exc(exc)
    if code in {"resource_expired", "not_found"}:
        return True
    body = (exc.safe_body or str(exc) or "").lower()
    return any(
        token in body
        for token in (
            "already stopped",
            "failed to find worker",
            "recording is exiting",
            "is not recording",
        )
    )


def _is_transient(exc: AgoraCloudRecordingError) -> bool:
    if exc.status_code and 500 <= exc.status_code < 600:
        return True
    if exc.status_code is None:
        return True
    return False


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
    rec: CallRecording | None = None,
    attempts: int = 6,
    delay_seconds: float = 2.5,
) -> list[dict]:
    last_exc: AgoraCloudRecordingError | None = None
    for attempt in range(attempts):
        if attempt:
            time.sleep(delay_seconds)
        try:
            payload = client.query(resource_id=resource_id, sid=sid)
            if rec is not None:
                rec.query_attempts = (rec.query_attempts or 0) + 1
                rec.last_query_at = timezone.now()
                rec.save(update_fields=["query_attempts", "last_query_at"])
        except AgoraCloudRecordingError as exc:
            last_exc = exc
            if _failure_code_from_exc(exc) in {"resource_expired", "not_found"}:
                raise
            continue
        files = _extract_file_list(payload)
        if files:
            return files
    if last_exc is not None and attempts <= 2:
        # Preserve signal for callers that want to expire.
        raise last_exc
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


def _pick_best_file_name(file_list: list[dict]) -> str:
    """Prefer final media (mp4 > m4a > aac > mp3). Never pick m3u8/ts/m2t."""
    from apps.calls.recording_storage import pick_best_playable_object_key

    if not file_list:
        return ""
    names: list[str] = []
    for item in file_list:
        name = (item.get("fileName") or item.get("filename") or "").strip()
        if name:
            names.append(name)
    return pick_best_playable_object_key(names)


def _pick_object_key(file_list: list[dict]) -> str:
    file_name = _pick_best_file_name(file_list)
    if not file_name:
        return ""
    return file_name.lstrip("/")


def _legacy_public_url(object_key: str) -> str:
    """Build a legacy public URL for DB backward compatibility only."""
    base = (getattr(settings, "AGORA_RECORDING_PUBLIC_BASE_URL", "") or "").strip()
    if not base or not object_key:
        return ""
    if not base.endswith("/"):
        base = f"{base}/"
    return urljoin(base, object_key.lstrip("/"))
