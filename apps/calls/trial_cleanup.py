"""Superuser trial tools: purge all call data safely."""

from __future__ import annotations

import logging

from django.db import transaction
from django.utils import timezone

from apps.calls.models import (
    CallPeerRating,
    CallPeerRatingAnswer,
    CallRecording,
    CallRecordingConsent,
    CallSession,
    RatingCategoryConfig,
    RatingQuestion,
    SessionEvaluation,
)
from apps.calls.recording_storage import (
    delete_recording_object,
    delete_recording_prefix,
    object_key_for_recording,
    prefix_for_recording_objects,
)
from core.utils.postgres_sequences import reset_sequence

logger = logging.getLogger(__name__)

CALL_TABLES_FOR_SEQUENCE_RESET = (
    "calls_callsession",
    "calls_callrecording",
    "calls_callpeerrating",
    "calls_callpeerratinganswer",
    "calls_callrecordingconsent",
    "calls_sessionevaluation",
)


def _delete_recording_r2(rec: CallRecording) -> tuple[int, int]:
    """Return (deleted_count, failed_count)."""
    prefix = prefix_for_recording_objects(rec)
    key = object_key_for_recording(rec)
    try:
        if prefix:
            deleted, failed = delete_recording_prefix(prefix)
            return deleted, len(failed)
        if key:
            delete_recording_object(key)
            return 1, 0
    except Exception:
        logger.exception(
            "trial_purge_calls_r2_failed recording_id=%s",
            getattr(rec, "pk", None),
        )
        return 0, 1
    return 0, 0


def purge_all_call_data(*, actor) -> dict:
    """
    Delete all CallSession rows and cascaded call data.

    Does NOT delete RatingQuestion / RatingCategoryConfig.
    Appointment.call_session is SET_NULL by FK.
    """
    actor_username = getattr(actor, "username", "") or ""
    started_at = timezone.now()

    counts_before = {
        "call_sessions": CallSession.objects.count(),
        "call_recordings": CallRecording.objects.count(),
        "peer_ratings": CallPeerRating.objects.count(),
        "peer_rating_answers": CallPeerRatingAnswer.objects.count(),
        "recording_consents": CallRecordingConsent.objects.count(),
        "session_evaluations": SessionEvaluation.objects.count(),
        "rating_questions": RatingQuestion.objects.count(),
        "rating_category_configs": RatingCategoryConfig.objects.count(),
    }

    r2_deleted = 0
    r2_failed = 0
    for rec in CallRecording.objects.all().iterator():
        deleted, failed = _delete_recording_r2(rec)
        r2_deleted += deleted
        r2_failed += failed

    with transaction.atomic():
        deleted_sessions, _ = CallSession.objects.all().delete()
        # Cascade removes children; recount for report clarity.
        remaining = {
            "call_sessions": CallSession.objects.count(),
            "call_recordings": CallRecording.objects.count(),
            "peer_ratings": CallPeerRating.objects.count(),
            "peer_rating_answers": CallPeerRatingAnswer.objects.count(),
            "recording_consents": CallRecordingConsent.objects.count(),
            "session_evaluations": SessionEvaluation.objects.count(),
        }
        if any(remaining.values()):
            # Belt-and-suspenders for orphans without CallSession FK cascade.
            CallPeerRatingAnswer.objects.all().delete()
            CallPeerRating.objects.all().delete()
            CallRecordingConsent.objects.all().delete()
            SessionEvaluation.objects.all().delete()
            CallRecording.objects.all().delete()

        sequences = {}
        for table in CALL_TABLES_FOR_SEQUENCE_RESET:
            sequences[table] = reset_sequence(table)

    rating_questions_after = RatingQuestion.objects.count()
    rating_configs_after = RatingCategoryConfig.objects.count()

    result = {
        "deleted": {
            "call_sessions": counts_before["call_sessions"],
            "call_recordings": counts_before["call_recordings"],
            "peer_ratings": counts_before["peer_ratings"],
            "peer_rating_answers": counts_before["peer_rating_answers"],
            "recording_consents": counts_before["recording_consents"],
            "session_evaluations": counts_before["session_evaluations"],
            "django_delete_total": deleted_sessions,
        },
        "preserved": {
            "rating_questions": rating_questions_after,
            "rating_category_configs": rating_configs_after,
        },
        "r2_deleted": r2_deleted,
        "r2_failed": r2_failed,
        "sequences": sequences,
        "actor": actor_username,
        "started_at": started_at.isoformat(),
        "finished_at": timezone.now().isoformat(),
    }

    logger.info(
        "trial_purge_all_calls actor=%s deleted_sessions=%s recordings=%s "
        "ratings=%s answers=%s consents=%s evaluations=%s "
        "r2_deleted=%s r2_failed=%s rating_questions_preserved=%s",
        actor_username,
        result["deleted"]["call_sessions"],
        result["deleted"]["call_recordings"],
        result["deleted"]["peer_ratings"],
        result["deleted"]["peer_rating_answers"],
        result["deleted"]["recording_consents"],
        result["deleted"]["session_evaluations"],
        r2_deleted,
        r2_failed,
        rating_questions_after,
    )
    return result
