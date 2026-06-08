import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.calls.models import CallRecording
from apps.calls.recording_storage import (
    RecordingStorageError,
    delete_recording_object,
    object_key_for_recording,
)
from core.utils.pagination import build_pagination_query_string
from identity.rbac.decorators import permissions_required

logger = logging.getLogger(__name__)


def _recordings_hub_url(**params) -> str:
    qs = build_pagination_query_string(tab="recordings", **params)
    base = reverse("dashboard:call_session_list")
    if qs:
        return f"{base}?{qs.rstrip('&')}"
    return f"{base}?tab=recordings"


@login_required
@permissions_required("dashboard.access", "recordings.view")
def call_recording_list(request):
    """Legacy URL — redirects to المكالمات → التسجيلات."""
    q = (request.GET.get("q") or "").strip()
    per_page = (request.GET.get("per_page") or "").strip()
    kwargs = {}
    if q:
        kwargs["q"] = q
    if per_page:
        kwargs["per_page"] = per_page
    return redirect(_recordings_hub_url(**kwargs))


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
                return redirect(_recordings_hub_url())

        recording.delete()
        messages.success(request, "تم حذف التسجيل وملفه من التخزين بنجاح.")
        return redirect(_recordings_hub_url())

    return render(
        request,
        "dashboard/pages/recordings/confirm_delete.html",
        {"recording": recording, "object_key": object_key_for_recording(recording)},
    )
