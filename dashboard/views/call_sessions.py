from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render

from apps.calls.models import CallSession
from core.utils.pagination import build_pagination_query_string, paginate_with_smart_pages
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

    page_obj, page_numbers, per_page_param, total_calls = paginate_with_smart_pages(
        request=request,
        queryset=qs,
        default_per_page="5",
    )

    rows = [
        {"call": c, "duration": _duration_display(c)}
        for c in page_obj.object_list
    ]

    pagination_qs = build_pagination_query_string(
        q=q,
        type=type_filter,
        status=status_filter,
        per_page=per_page_param,
    )

    hidden_fields = []
    if q:
        hidden_fields.append({"name": "q", "value": q})
    if type_filter != "all":
        hidden_fields.append({"name": "type", "value": type_filter})
    if status_filter != "all":
        hidden_fields.append({"name": "status", "value": status_filter})
    return render(
        request,
        "dashboard/pages/calls/list.html",
        {
            "rows": rows,
            "page_obj": page_obj,
            "page_numbers": page_numbers,
            "per_page": per_page_param,
            "total_calls": total_calls,
            "q": q,
            "type_filter": type_filter,
            "status_filter": status_filter,
            "pagination_qs": pagination_qs,
            "pagination_hidden_fields": hidden_fields,
        },
    )
