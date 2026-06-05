import logging

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render

from apps.calls.models import CallRecording
from apps.calls.recording_storage import (
    RecordingStorageError,
    generate_recording_signed_url,
    object_key_for_recording,
    playback_content_type_for_key,
)
from identity.rbac.decorators import permissions_required

logger = logging.getLogger(__name__)


@login_required
@permissions_required("dashboard.access", "recordings.view")
def call_recording_list(request):
    q = (request.GET.get("q") or "").strip()

    qs = CallRecording.objects.select_related(
        "call_session", "student", "teacher"
    ).order_by("-created_at", "-id")

    if q:
        qs = qs.filter(
            Q(student__username__icontains=q)
            | Q(teacher__username__icontains=q)
            | Q(recording_url__icontains=q)
            | Q(recording_object_key__icontains=q)
        )

    rows = list(qs[:500])
    for row in rows:
        row.signed_playback_url = None
        row.signed_playback_type = "audio/mp4"
        row.playback_unavailable = False

        object_key = object_key_for_recording(row)
        if not object_key:
            continue

        row.signed_playback_type = playback_content_type_for_key(object_key)
        try:
            row.signed_playback_url, _ = generate_recording_signed_url(object_key)
        except RecordingStorageError as exc:
            row.playback_unavailable = True
            logger.warning(
                "Dashboard signed URL failed for recording %s (key=%s): %s",
                row.id,
                object_key,
                exc,
            )

    return render(
        request,
        "dashboard/pages/recordings/list.html",
        {"rows": rows, "q": q},
    )
