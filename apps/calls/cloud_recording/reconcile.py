"""Reconcile stuck calls and cloud recordings without deleting data."""

from __future__ import annotations

import logging
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from apps.calls.cloud_recording.service import (
    stop_and_finalize_recording_for_call_id,
    try_finalize_recording_files,
)
from apps.calls.models import CallRecording, CallSession
from apps.tutoring.teacher_services import mark_teacher_online

logger = logging.getLogger(__name__)

STALE_ACTIVE_AFTER = timedelta(hours=2)
STALE_ENDING_AFTER = timedelta(minutes=2)
STALE_RECORDING_AFTER = timedelta(minutes=10)


def reconcile_stuck_calls(*, dry_run: bool = True, limit: int = 100) -> dict:
    """Finalize stuck ACTIVE/ENDING calls and preparing recordings."""
    now = timezone.now()
    summary = {
        "dry_run": dry_run,
        "active_finalized": [],
        "ending_finalized": [],
        "recordings_reconciled": [],
        "teachers_released": [],
        "errors": [],
    }

    stale_active = list(
        CallSession.objects.filter(status=CallSession.Status.ACTIVE)
        .filter(
            Q(started_at__lte=now - STALE_ACTIVE_AFTER)
            | Q(started_at__isnull=True, created_at__lte=now - STALE_ACTIVE_AFTER)
        )
        .order_by("id")[:limit]
    )
    for call in stale_active:
        summary["active_finalized"].append(call.id)
        if dry_run:
            continue
        try:
            _force_end_call(call, reason="stale_active_watchdog")
            stop_and_finalize_recording_for_call_id(call.id)
            if call.teacher_id:
                mark_teacher_online(call.teacher)
                summary["teachers_released"].append(call.teacher_id)
        except Exception as exc:
            summary["errors"].append({"call_id": call.id, "error": str(exc)[:200]})

    stale_ending = list(
        CallSession.objects.filter(status=CallSession.Status.ENDING)
        .filter(
            Q(end_requested_at__lte=now - STALE_ENDING_AFTER)
            | Q(end_requested_at__isnull=True, updated_at__lte=now - STALE_ENDING_AFTER)
        )
        .order_by("id")[:limit]
    )
    for call in stale_ending:
        summary["ending_finalized"].append(call.id)
        if dry_run:
            continue
        try:
            _force_end_call(call, reason="stale_ending_watchdog")
            stop_and_finalize_recording_for_call_id(call.id)
            if call.teacher_id:
                mark_teacher_online(call.teacher)
                summary["teachers_released"].append(call.teacher_id)
        except Exception as exc:
            summary["errors"].append({"call_id": call.id, "error": str(exc)[:200]})

    preparing = list(
        CallRecording.objects.filter(
            recording_status__in=sorted(CallRecording.PREPARING_STATUSES)
        )
        .select_related("call_session")
        .order_by("id")[:limit]
    )
    # Statuses that still need an Agora stop (not already past stop).
    needs_agora_stop = {
        CallRecording.RecordingStatus.STARTING,
        CallRecording.RecordingStatus.RECORDING,
        CallRecording.RecordingStatus.STOP_REQUESTED,
        CallRecording.RecordingStatus.STOPPING,
    }

    for rec in preparing:
        summary["recordings_reconciled"].append(
            {
                "recording_id": rec.id,
                "call_id": rec.call_session_id,
                "status": rec.recording_status,
            }
        )
        if dry_run:
            continue
        try:
            # Always try finalize/expire first (idempotent; no Agora stop).
            try_finalize_recording_files(rec, allow_expire=True)
            rec.refresh_from_db()
            if rec.is_terminal or not rec.call_session_id:
                continue
            # Re-stop only when stop was never completed; processing → finalize only.
            if rec.recording_status in needs_agora_stop:
                stop_and_finalize_recording_for_call_id(rec.call_session_id)
            elif rec.recording_status == CallRecording.RecordingStatus.PROCESSING:
                try_finalize_recording_files(rec, allow_expire=True)
        except Exception as exc:
            summary["errors"].append(
                {
                    "recording_id": rec.id,
                    "call_id": rec.call_session_id,
                    "error": str(exc)[:200],
                }
            )

    logger.info(
        "stuck_call_reconciled dry_run=%s active=%s ending=%s recordings=%s errors=%s",
        dry_run,
        len(summary["active_finalized"]),
        len(summary["ending_finalized"]),
        len(summary["recordings_reconciled"]),
        len(summary["errors"]),
    )
    return summary


def inspect_call_recording(call_id: int) -> dict:
    call = (
        CallSession.objects.select_related("student", "teacher", "recording")
        .filter(pk=call_id)
        .first()
    )
    if call is None:
        return {"ok": False, "error": "call_not_found", "call_id": call_id}

    rec = getattr(call, "recording", None)
    return {
        "ok": True,
        "call_id": call.id,
        "call_status": call.status,
        "blocks_new_calls": call.blocks_new_calls,
        "channel_present": bool((call.channel_name or "").strip()),
        "started_at": call.started_at.isoformat() if call.started_at else None,
        "ended_at": call.ended_at.isoformat() if call.ended_at else None,
        "end_requested_at": (
            call.end_requested_at.isoformat() if call.end_requested_at else None
        ),
        "end_reason": call.end_reason or "",
        "teacher_id": call.teacher_id,
        "recording": None
        if rec is None
        else {
            "recording_id": rec.id,
            "recording_status": rec.recording_status,
            "is_terminal": rec.is_terminal,
            "is_playable": rec.is_playable,
            "has_resource_id": bool((rec.agora_resource_id or "").strip()),
            "has_sid": bool((rec.agora_sid or "").strip()),
            "has_object_key": bool((rec.recording_object_key or "").strip()),
            "stop_requested_at": (
                rec.stop_requested_at.isoformat() if rec.stop_requested_at else None
            ),
            "stop_attempts": rec.stop_attempts,
            "query_attempts": rec.query_attempts,
            "last_query_at": (
                rec.last_query_at.isoformat() if rec.last_query_at else None
            ),
            "failure_code": rec.failure_code or "",
            "recording_error": (rec.recording_error or "")[:200],
            "processing_started_at": (
                rec.processing_started_at.isoformat()
                if rec.processing_started_at
                else None
            ),
            "finalized_at": (
                rec.finalized_at.isoformat() if rec.finalized_at else None
            ),
        },
    }


def reconcile_call_recording(call_id: int, *, apply: bool = False) -> dict:
    info = inspect_call_recording(call_id)
    if not info.get("ok"):
        return info
    result = {"ok": True, "dry_run": not apply, "before": info, "actions": []}
    if not apply:
        result["actions"].append("Would stop/finalize recording and release locks")
        return result

    call = CallSession.objects.get(pk=call_id)
    if call.blocks_new_calls:
        _force_end_call(call, reason="manual_reconcile")
        result["actions"].append("forced_call_ended")
        if call.teacher_id:
            mark_teacher_online(call.teacher)
            result["actions"].append("teacher_released")

    stop_result = stop_and_finalize_recording_for_call_id(call_id)
    result["actions"].append({"stop_finalize": stop_result})
    result["after"] = inspect_call_recording(call_id)
    return result


def _force_end_call(call: CallSession, *, reason: str) -> None:
    now = timezone.now()
    call.status = CallSession.Status.ENDED
    call.end_requested_at = call.end_requested_at or now
    call.ended_at = call.ended_at or now
    call.finalized_at = now
    call.end_reason = reason[:64]
    call.save(
        update_fields=[
            "status",
            "end_requested_at",
            "ended_at",
            "finalized_at",
            "end_reason",
            "updated_at",
        ]
    )
