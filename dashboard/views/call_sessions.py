from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render

from apps.calls.models import CallSession
from identity.rbac.decorators import permissions_required


def _duration_display(call: CallSession) -> str:
    if call.started_at and call.ended_at:
        delta = call.ended_at - call.started_at
        total = int(delta.total_seconds())
        minutes, seconds = divmod(total, 60)
        if minutes:
            return f"{minutes} د {seconds} ث"
        return f"{seconds} ث"
    if call.status == CallSession.Status.ACTIVE and call.started_at:
        return "جارية"
    return "—"


@login_required
@permissions_required("dashboard.access", "calls.view")
def call_session_list(request):
    q = (request.GET.get("q") or "").strip()
    type_filter = (request.GET.get("type") or "all").strip()
    status_filter = (request.GET.get("status") or "all").strip()

    qs = CallSession.objects.select_related("student", "teacher").order_by(
        "-created_at", "-id"
    )

    if q:
        qs = qs.filter(
            Q(student__username__icontains=q)
            | Q(student__email__icontains=q)
            | Q(student__full_name__icontains=q)
            | Q(teacher__username__icontains=q)
            | Q(teacher__email__icontains=q)
            | Q(channel_name__icontains=q)
        )

    if type_filter in {CallSession.SessionType.AUDIO, CallSession.SessionType.VIDEO}:
        qs = qs.filter(session_type=type_filter)

    if status_filter in {s[0] for s in CallSession.Status.choices}:
        qs = qs.filter(status=status_filter)

    rows = [{"call": c, "duration": _duration_display(c)} for c in qs[:500]]

    return render(
        request,
        "dashboard/pages/calls/list.html",
        {
            "rows": rows,
            "q": q,
            "type_filter": type_filter,
            "status_filter": status_filter,
        },
    )
