from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import render

from apps.calls.models import CallPeerRating, RatingCategoryConfig, RatingQuestion
from apps.calls.rating_service import CATEGORY_LABELS_AR
from core.utils.pagination import build_pagination_query_string, paginate_with_smart_pages
from identity.rbac.decorators import permissions_required


@login_required
@permissions_required("dashboard.access", "evaluations.view")
def session_evaluation_list(request):
    q = (request.GET.get("q") or "").strip()
    status_filter = (request.GET.get("status") or "all").strip()

    qs = CallPeerRating.objects.select_related(
        "call_session",
        "call_session__recording",
        "rater",
        "rated",
        "call_session__student",
        "call_session__teacher",
    ).order_by("-created_at", "-id")

    if q:
        qs = qs.filter(
            Q(call_session__student__username__icontains=q)
            | Q(call_session__student__email__icontains=q)
            | Q(call_session__teacher__username__icontains=q)
            | Q(call_session__teacher__email__icontains=q)
        )

    if status_filter in {s[0] for s in CallPeerRating.Status.choices}:
        qs = qs.filter(status=status_filter)

    page_obj, page_numbers, per_page_param, total_rows = paginate_with_smart_pages(
        request=request,
        queryset=qs,
        default_per_page="5",
    )

    pagination_qs = build_pagination_query_string(
        q=q,
        status=status_filter,
        per_page=per_page_param,
    )

    hidden_fields = []
    if q:
        hidden_fields.append({"name": "q", "value": q})
    if status_filter != "all":
        hidden_fields.append({"name": "status", "value": status_filter})
    category_configs = {
        row.category: row
        for row in RatingCategoryConfig.objects.all()
    }
    question_groups = []
    for category, _label in RatingQuestion.Category.choices:
        config = category_configs.get(category)
        question_groups.append(
            {
                "category": category,
                "label": CATEGORY_LABELS_AR.get(category, category),
                "is_active": config.is_active if config else True,
                "questions": list(
                    RatingQuestion.objects.filter(category=category).order_by(
                        "order", "id"
                    )
                ),
            }
        )

    return render(
        request,
        "dashboard/pages/evaluations/list.html",
        {
            "rows": page_obj.object_list,
            "page_obj": page_obj,
            "page_numbers": page_numbers,
            "per_page": per_page_param,
            "total_rows": total_rows,
            "q": q,
            "status_filter": status_filter,
            "status_choices": CallPeerRating.Status.choices,
            "role_choices": CallPeerRating.RaterRole.choices,
            "question_groups": question_groups,
            "category_labels": CATEGORY_LABELS_AR,
            "pagination_qs": pagination_qs,
            "pagination_hidden_fields": hidden_fields,
        },
    )
