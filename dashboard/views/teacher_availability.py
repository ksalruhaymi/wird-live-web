from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.tutoring.teacher_services import (
    COMPUTED_AVAILABLE,
    COMPUTED_BUSY,
    COMPUTED_OFFLINE,
    compute_teacher_status,
    computed_status_label,
    is_demo_teacher,
    search_teacher_rows,
    teacher_display_name,
    _active_teacher_ids,
)
from core.utils.pagination import build_pagination_query_string, paginate_with_smart_pages
from identity.rbac.decorators import permissions_required


@login_required
@permissions_required("dashboard.access", "teachers.availability.view")
def teacher_availability_list(request):
    q = (request.GET.get("q") or "").strip()
    status_filter = (request.GET.get("status") or "all").strip()
    demo_filter = (request.GET.get("demo") or "all").strip()

    teachers = search_teacher_rows(q)
    active_ids = _active_teacher_ids()
    rows = []
    for user in teachers:
        profile = user.teacher_profile
        availability = getattr(user, "teacher_availability", None)
        status = compute_teacher_status(user, active_teacher_ids=active_ids)
        is_demo = is_demo_teacher(user)
        rows.append(
            {
                "user": user,
                "display_name": teacher_display_name(user),
                "email": user.email,
                "availability": availability,
                "status": status,
                "status_label": computed_status_label(status),
                "can_audio": profile.can_audio,
                "can_video": profile.can_video,
                "is_demo_teacher": is_demo,
                "last_seen": availability.last_seen if availability else None,
            }
        )

    if status_filter in {COMPUTED_AVAILABLE, COMPUTED_BUSY, COMPUTED_OFFLINE}:
        rows = [r for r in rows if r["status"] == status_filter]

    if demo_filter == "yes":
        rows = [r for r in rows if r["is_demo_teacher"]]
    elif demo_filter == "no":
        rows = [r for r in rows if not r["is_demo_teacher"]]

    page_obj, page_numbers, per_page_param, total_rows = paginate_with_smart_pages(
        request=request,
        queryset=rows,
        default_per_page="5",
    )

    pagination_qs = build_pagination_query_string(
        q=q,
        status=status_filter,
        demo=demo_filter,
        per_page=per_page_param,
    )

    hidden_fields = []
    if q:
        hidden_fields.append({"name": "q", "value": q})
    if status_filter != "all":
        hidden_fields.append({"name": "status", "value": status_filter})
    if demo_filter != "all":
        hidden_fields.append({"name": "demo", "value": demo_filter})
    return render(
        request,
        "dashboard/pages/teachers/availability_list.html",
        {
            "rows": page_obj.object_list,
            "page_obj": page_obj,
            "page_numbers": page_numbers,
            "per_page": per_page_param,
            "total_rows": total_rows,
            "q": q,
            "status_filter": status_filter,
            "demo_filter": demo_filter,
            "pagination_qs": pagination_qs,
            "pagination_hidden_fields": hidden_fields,
        },
    )
