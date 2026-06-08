from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.urls import reverse

from core.utils.pagination import build_pagination_query_string
from identity.rbac.decorators import permissions_required


@login_required
@permissions_required("dashboard.access", "teachers.availability.view")
def teacher_availability_list(request):
    """Legacy URL — redirects to المستخدمين → المعلمون with the same filters."""
    q = (request.GET.get("q") or "").strip()
    status_filter = (request.GET.get("status") or "all").strip()
    demo_filter = (request.GET.get("demo") or "all").strip()
    per_page = (request.GET.get("per_page") or "").strip()

    kwargs = {"tab": "teachers"}
    if q:
        kwargs["q"] = q
    if status_filter != "all":
        kwargs["status"] = status_filter
    if demo_filter != "all":
        kwargs["demo"] = demo_filter
    if per_page:
        kwargs["per_page"] = per_page

    qs = build_pagination_query_string(**kwargs)
    base = reverse("dashboard:dashboard_users_list")
    if qs:
        return redirect(f"{base}?{qs.rstrip('&')}")
    return redirect(base)
