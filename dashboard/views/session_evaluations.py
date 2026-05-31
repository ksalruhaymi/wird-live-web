from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render

from apps.calls.models import SessionEvaluation
from identity.rbac.decorators import permissions_required


@login_required
@permissions_required("dashboard.access", "evaluations.view")
def session_evaluation_list(request):
    q = (request.GET.get("q") or "").strip()
    status_filter = (request.GET.get("status") or "all").strip()

    qs = SessionEvaluation.objects.select_related(
        "call_session", "student", "teacher"
    ).order_by("-created_at", "-id")

    if q:
        qs = qs.filter(
            Q(student__username__icontains=q)
            | Q(student__email__icontains=q)
            | Q(teacher__username__icontains=q)
            | Q(teacher__email__icontains=q)
        )

    if status_filter in {s[0] for s in SessionEvaluation.Status.choices}:
        qs = qs.filter(status=status_filter)

    return render(
        request,
        "dashboard/pages/evaluations/list.html",
        {
            "rows": qs[:500],
            "q": q,
            "status_filter": status_filter,
            "status_choices": SessionEvaluation.Status.choices,
        },
    )
