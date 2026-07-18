"""Background stop/finalize for Agora cloud recording.

Celery is the only async execution path. If enqueue fails, the recording
stays in stop_requested / preparing for the periodic reconcile job —
never rely on an in-process thread as a production guarantee.
"""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


def enqueue_stop_and_finalize_recording(call_id: int) -> str:
    """Schedule Celery stop+finalize.

    Returns:
        ``"celery"`` when the task was enqueued, or ``"deferred"`` when the
        broker/app rejected the enqueue (caller must leave DB state for
        reconcile).
    """
    try:
        stop_and_finalize_recording_task.delay(call_id)
        return "celery"
    except Exception:
        logger.warning(
            "Celery enqueue failed for call_id=%s; leaving stop_requested "
            "for reconcile (no thread fallback)",
            call_id,
            exc_info=True,
        )
        return "deferred"


@shared_task(
    bind=True,
    name="apps.calls.tasks.stop_and_finalize_recording",
    max_retries=3,
    default_retry_delay=20,
    soft_time_limit=90,
    time_limit=120,
)
def stop_and_finalize_recording_task(self, call_id: int) -> dict:
    from apps.calls.cloud_recording.service import (
        stop_and_finalize_recording_for_call_id,
    )

    try:
        return stop_and_finalize_recording_for_call_id(call_id)
    except Exception as exc:
        # Retry only transient failures; always attempt to leave a terminal state
        # on the last retry via the service itself.
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.exception(
                "recording_stop_failed call_id=%s retries_exhausted", call_id
            )
            from apps.calls.cloud_recording.service import (
                mark_recording_failed_for_call_id,
            )

            mark_recording_failed_for_call_id(
                call_id,
                failure_code="stop_retries_exhausted",
                message="Recording stop retries exhausted.",
            )
            return {"ok": False, "call_id": call_id, "error": "retries_exhausted"}


@shared_task(name="apps.calls.tasks.reconcile_stuck_calls")
def reconcile_stuck_calls_task(*, dry_run: bool = False) -> dict:
    from apps.calls.cloud_recording.reconcile import reconcile_stuck_calls

    return reconcile_stuck_calls(dry_run=dry_run)
