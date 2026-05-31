from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render

from apps.calls.models import CallRecording
from identity.rbac.decorators import permissions_required


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
        )

    return render(
        request,
        "dashboard/pages/recordings/list.html",
        {"rows": qs[:500], "q": q},
    )
