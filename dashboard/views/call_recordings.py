import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.calls.models import CallRecording
from apps.calls.recording_storage import (
    RecordingStorageError,
    delete_recording_object,
    generate_recording_signed_url,
    object_key_for_recording,
    playback_content_type_for_key,
)
from core.utils.pagination import build_pagination_query_string, paginate_with_smart_pages
from identity.rbac.decorators import permissions_required

logger = logging.getLogger(__name__)


def _attach_playback_urls(rows) -> None:
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

    page_obj, page_numbers, per_page_param, total_recordings = paginate_with_smart_pages(
        request=request,
        queryset=qs,
        default_per_page="5",
    )

    rows = list(page_obj.object_list)
    _attach_playback_urls(rows)

    pagination_qs = build_pagination_query_string(q=q, per_page=per_page_param)

    hidden_fields = []
    if q:
        hidden_fields.append({"name": "q", "value": q})
    return render(
        request,
        "dashboard/pages/recordings/list.html",
        {
            "rows": rows,
            "page_obj": page_obj,
            "page_numbers": page_numbers,
            "per_page": per_page_param,
            "total_recordings": total_recordings,
            "q": q,
            "pagination_qs": pagination_qs,
            "pagination_hidden_fields": hidden_fields,
        },
    )


@login_required
@permissions_required("dashboard.access", "recordings.delete")
def call_recording_delete(request, pk):
    recording = get_object_or_404(
        CallRecording.objects.select_related("student", "teacher"),
        pk=pk,
    )

    if request.method == "POST":
        object_key = object_key_for_recording(recording)
        if object_key:
            try:
                delete_recording_object(object_key)
            except RecordingStorageError:
                messages.error(
                    request,
                    "تعذر حذف ملف التسجيل من التخزين السحابي. "
                    "لم يتم حذف السجل من قاعدة البيانات.",
                )
                return redirect("dashboard:call_recording_list")

        recording.delete()
        messages.success(request, "تم حذف التسجيل وملفه من التخزين بنجاح.")
        return redirect("dashboard:call_recording_list")

    return render(
        request,
        "dashboard/pages/recordings/confirm_delete.html",
        {"recording": recording, "object_key": object_key_for_recording(recording)},
    )
