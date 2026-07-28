"""Soft-hide recordings per participant; hard delete is retention-gated."""

from __future__ import annotations

import logging
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.calls.models import CallRecording

logger = logging.getLogger(__name__)

# Hard delete of storage/DB only after both parties hide and this window elapses.
RECORDING_RETENTION_DAYS_AFTER_BOTH_HIDDEN = 30


def recording_hidden_for_user(recording: CallRecording, user) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if recording.student_id == user.id:
        return recording.hidden_by_student_at is not None
    if recording.teacher_id == user.id:
        return recording.hidden_by_teacher_at is not None
    return False


def recording_parties_have_hidden(recording: CallRecording) -> bool:
    """True when every existing participant has soft-hidden the recording."""
    if recording.hidden_by_student_at is None:
        return False
    if recording.teacher_id and recording.hidden_by_teacher_at is None:
        return False
    return True


def recording_still_needed_by_system(recording: CallRecording) -> bool:
    """Keep rows that are not yet terminal (admin/ops may still need them)."""
    return recording.recording_status not in CallRecording.TERMINAL_STATUSES


def recording_eligible_for_hard_delete(recording: CallRecording) -> bool:
    """Hard delete only after both hides + retention window + terminal status."""
    if recording_still_needed_by_system(recording):
        return False
    if not recording_parties_have_hidden(recording):
        return False
    stamps = [
        t
        for t in (recording.hidden_by_student_at, recording.hidden_by_teacher_at)
        if t is not None
    ]
    if not stamps:
        return False
    last_hidden = max(stamps)
    return timezone.now() >= last_hidden + timedelta(
        days=RECORDING_RETENTION_DAYS_AFTER_BOTH_HIDDEN
    )


def hide_recording_for_user(recording: CallRecording, user) -> CallRecording:
    """Soft-remove from the caller's list only. Does not delete storage."""
    now = timezone.now()
    updates: list[str] = []
    if recording.student_id == user.id and recording.hidden_by_student_at is None:
        recording.hidden_by_student_at = now
        updates.append("hidden_by_student_at")
    elif recording.teacher_id == user.id and recording.hidden_by_teacher_at is None:
        recording.hidden_by_teacher_at = now
        updates.append("hidden_by_teacher_at")
    if updates:
        recording.save(update_fields=updates)
    return recording


def maybe_hard_delete_recording(recording: CallRecording) -> bool:
    """
    Physically delete R2 + DB row only when eligible.

    Idempotent. On R2 failure, leaves the DB row for a later cleanup pass.
    Returns True when the recording was hard-deleted.
    """
    recording = CallRecording.objects.filter(pk=recording.pk).first()
    if recording is None:
        return False
    if not recording_eligible_for_hard_delete(recording):
        return False

    from apps.calls.recording_storage import (
        RecordingStorageError,
        delete_recording_object,
        delete_recording_prefix,
        object_key_for_recording,
        prefix_for_recording_objects,
    )

    prefix = prefix_for_recording_objects(recording)
    key = object_key_for_recording(recording)
    try:
        if prefix:
            delete_recording_prefix(prefix)
        elif key:
            delete_recording_object(key)
    except RecordingStorageError:
        logger.exception(
            "hard_delete_storage_failed recording_id=%s; leaving DB row",
            recording.id,
        )
        return False

    recording_id = recording.id
    with transaction.atomic():
        deleted, _ = CallRecording.objects.filter(pk=recording_id).delete()
    if not deleted:
        return False
    logger.info("hard_deleted_recording recording_id=%s", recording_id)
    return True


def soft_hidden_candidates_queryset():
    """Candidates both parties have soft-hidden (teacher may be null on test calls)."""
    return CallRecording.objects.filter(
        hidden_by_student_at__isnull=False,
        recording_status__in=CallRecording.TERMINAL_STATUSES,
    ).filter(Q(teacher_id__isnull=True) | Q(hidden_by_teacher_at__isnull=False))


def purge_expired_soft_hidden_recordings(
    *,
    limit: int = 100,
    dry_run: bool = False,
) -> dict:
    """Retention cleanup: hard-delete eligible soft-hidden recordings.

    Safe to run repeatedly. Does not delete rows still needed (non-terminal)
    or inside the retention window.
    """
    limit = max(1, min(int(limit or 100), 500))
    scanned = 0
    eligible = 0
    deleted = 0
    failed = 0
    skipped = 0

    # Prefetch a bounded window; eligibility uses last-hidden + 30d in Python.
    qs = soft_hidden_candidates_queryset().order_by("id")[: limit * 3]
    for recording in qs:
        scanned += 1
        if not recording_eligible_for_hard_delete(recording):
            skipped += 1
            continue
        eligible += 1
        if dry_run:
            continue
        if maybe_hard_delete_recording(recording):
            deleted += 1
        else:
            failed += 1
        if deleted + failed >= limit:
            break

    summary = {
        "scanned": scanned,
        "eligible": eligible,
        "deleted": deleted,
        "failed": failed,
        "skipped": skipped,
        "dry_run": dry_run,
        "limit": limit,
    }
    logger.info("purge_expired_soft_hidden_recordings %s", summary)
    return summary
