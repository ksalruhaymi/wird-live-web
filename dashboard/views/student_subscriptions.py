from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render

from apps.subscription.models import StudentSubscription
from apps.subscription.services import display_status, display_status_label
from identity.rbac.decorators import permissions_required

User = get_user_model()

FILTER_ALL = "all"
FILTER_ACTIVE = "active"
FILTER_EXPIRED = "expired"
FILTER_CANCELLED = "cancelled"


def _annotate_rows(queryset):
    rows = []
    for sub in queryset.select_related("user", "plan"):
        computed = display_status(sub)
        rows.append(
            {
                "subscription": sub,
                "display_status": computed,
                "display_label": display_status_label(computed),
            }
        )
    return rows


def _filter_rows(rows, status_filter: str):
    if status_filter == FILTER_ALL:
        return rows
    return [r for r in rows if r["display_status"] == status_filter]


@login_required
@permissions_required("dashboard.access", "subscriptions.view")
def student_subscription_list(request):
    q = (request.GET.get("q") or "").strip()
    status_filter = (request.GET.get("status") or FILTER_ALL).strip()

    if status_filter not in {
        FILTER_ALL,
        FILTER_ACTIVE,
        FILTER_EXPIRED,
        FILTER_CANCELLED,
    }:
        status_filter = FILTER_ALL

    qs = StudentSubscription.objects.all().order_by("-created_at", "-id")

    if q:
        qs = qs.filter(
            Q(user__username__icontains=q)
            | Q(user__email__icontains=q)
            | Q(user__full_name__icontains=q)
            | Q(user__first_name__icontains=q)
            | Q(user__last_name__icontains=q)
            | Q(plan_title__icontains=q)
            | Q(transaction_reference__icontains=q)
            | Q(id__icontains=q)
        )

    rows = _filter_rows(_annotate_rows(qs[:500]), status_filter)

    return render(
        request,
        "dashboard/pages/student_subscriptions/list.html",
        {
            "rows": rows,
            "q": q,
            "status_filter": status_filter,
            "filter_all": FILTER_ALL,
            "filter_active": FILTER_ACTIVE,
            "filter_expired": FILTER_EXPIRED,
            "filter_cancelled": FILTER_CANCELLED,
        },
    )
