from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.urls import reverse

from core.utils.pagination import build_pagination_query_string
from identity.rbac.decorators import permissions_required


def _evaluations_hub_url(tab: str, **params) -> str:
    qs = build_pagination_query_string(tab=tab, **params)
    base = reverse("dashboard:call_session_list")
    return f"{base}?{qs.rstrip('&')}" if qs else f"{base}?tab={tab}"


@login_required
@permissions_required("dashboard.access", "evaluations.view")
def session_evaluation_list(request):
    """Legacy URL — redirects to المكالمات → تقييمات / إعدادات."""
    raw_tab = (request.GET.get("tab") or "").strip()
    if raw_tab == "settings":
        tab = "rating-settings"
    elif raw_tab in {"", "users"}:
        tab = "ratings"
    else:
        tab = raw_tab

    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "all").strip()
    per_page = (request.GET.get("per_page") or "").strip()

    kwargs = {}
    if q:
        kwargs["q"] = q
    if status != "all":
        kwargs["status"] = status
    if per_page:
        kwargs["per_page"] = per_page
    return redirect(_evaluations_hub_url(tab, **kwargs))
