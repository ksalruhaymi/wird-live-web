from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from apps.maqraa.teacher_services import (
    compute_teacher_status,
    computed_status_label,
    is_demo_teacher,
    search_teacher_rows,
    teacher_display_name,
    _active_teacher_ids,
)
from identity.rbac.decorators import permissions_required


@login_required
@permissions_required("dashboard.access", "teachers.availability.view")
def teacher_availability_list(request):
    q = (request.GET.get("q") or "").strip()
    teachers = search_teacher_rows(q)
    active_ids = _active_teacher_ids()
    rows = []
    for user in teachers[:500]:
        profile = user.teacher_profile
        availability = getattr(user, "teacher_availability", None)
        status = compute_teacher_status(user, active_teacher_ids=active_ids)
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
                "is_demo_teacher": is_demo_teacher(user),
                "last_seen": availability.last_seen if availability else None,
            }
        )

    return render(
        request,
        "dashboard/pages/teachers/availability_list.html",
        {
            "rows": rows,
            "q": q,
        },
    )
