from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from apps.calls.models import RatingQuestion
from apps.calls.rating_service import CATEGORY_LABELS_AR
from identity.rbac.decorators import permissions_required


def _parse_question_form(post):
    errors = []
    category = (post.get("category") or "").strip()
    question_text = (post.get("question_text") or "").strip()
    order_raw = (post.get("order") or "").strip()
    is_active = post.get("is_active") == "on"

    valid_categories = {c[0] for c in RatingQuestion.Category.choices}
    if category not in valid_categories:
        errors.append("نوع التقييم مطلوب.")

    if not question_text:
        errors.append("نص السؤال مطلوب.")

    try:
        order = int(order_raw)
        if order < 1:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("الترتيب يجب أن يكون رقماً موجباً.")
        order = 1

    return {
        "category": category,
        "question_text": question_text,
        "order": order,
        "is_active": is_active,
    }, errors


def _apply_question(instance: RatingQuestion, data: dict) -> RatingQuestion:
    instance.category = data["category"]
    instance.question_text = data["question_text"]
    instance.order = data["order"]
    instance.is_active = data["is_active"]
    instance.max_stars = 5
    instance.save()
    return instance


@login_required
@permissions_required("dashboard.access", "evaluations.create")
def rating_question_create(request):
    initial = {
        "category": RatingQuestion.Category.TEACHER,
        "order": 1,
        "is_active": True,
    }

    if request.method == "POST":
        data, errors = _parse_question_form(request.POST)
        initial = data
        if errors:
            for msg in errors:
                messages.error(request, msg)
        else:
            _apply_question(RatingQuestion(), data)
            messages.success(request, "تم إضافة سؤال التقييم بنجاح.")
            return redirect("dashboard:session_evaluation_list")

    return render(
        request,
        "dashboard/pages/evaluations/question_form.html",
        {
            "title": "إضافة تقييم",
            "mode": "create",
            "initial": initial,
            "category_choices": RatingQuestion.Category.choices,
            "category_labels": CATEGORY_LABELS_AR,
        },
    )


@login_required
@permissions_required("dashboard.access", "evaluations.update")
def rating_question_update(request, pk):
    question = get_object_or_404(RatingQuestion, pk=pk)
    initial = {
        "category": question.category,
        "question_text": question.question_text,
        "order": question.order,
        "is_active": question.is_active,
    }

    if request.method == "POST":
        data, errors = _parse_question_form(request.POST)
        initial = data
        if errors:
            for msg in errors:
                messages.error(request, msg)
        else:
            _apply_question(question, data)
            messages.success(request, "تم تحديث سؤال التقييم بنجاح.")
            return redirect("dashboard:session_evaluation_list")

    return render(
        request,
        "dashboard/pages/evaluations/question_form.html",
        {
            "title": "تعديل تقييم",
            "mode": "edit",
            "question": question,
            "initial": initial,
            "category_choices": RatingQuestion.Category.choices,
            "category_labels": CATEGORY_LABELS_AR,
        },
    )


@login_required
@permissions_required("dashboard.access", "evaluations.delete")
def rating_question_delete(request, pk):
    question = get_object_or_404(RatingQuestion, pk=pk)

    if request.method == "POST":
        question.delete()
        messages.success(request, "تم حذف سؤال التقييم.")
        return redirect("dashboard:session_evaluation_list")

    return render(
        request,
        "dashboard/pages/evaluations/question_confirm_delete.html",
        {"question": question, "category_labels": CATEGORY_LABELS_AR},
    )
