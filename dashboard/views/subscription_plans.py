from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.subscription.models import SubscriptionPlan
from core.utils.pagination import build_pagination_query_string, paginate_with_smart_pages
from identity.rbac.decorators import permissions_required

VALIDITY_UNITS = {
    SubscriptionPlan.ValidityUnit.DAYS,
    SubscriptionPlan.ValidityUnit.MONTHS,
}


def _parse_plan_form(post):
    """Return (data dict, errors list) from POST."""
    errors = []
    title = (post.get("title") or "").strip()
    price_raw = (post.get("price") or "").strip()
    minutes_raw = (post.get("minutes") or "0").strip()
    description = (post.get("description") or "").strip()
    sort_raw = (post.get("sort_order") or "0").strip()
    is_active = post.get("is_active") == "on"
    is_open_ended = post.get("is_open_ended") == "on"
    validity_value_raw = (post.get("validity_value") or "").strip()
    validity_unit_raw = (post.get("validity_unit") or "").strip()

    if not title:
        errors.append("الرجاء إدخال اسم الباقة.")

    validity_value = None
    validity_unit = None
    duration_months = 0

    if is_open_ended:
        validity_value = None
        validity_unit = None
        duration_months = 0
    else:
        if not validity_value_raw and not validity_unit_raw:
            errors.append("الرجاء إدخال قيمة ووحدة الصلاحية، أو اختيار باقة مفتوحة.")
        elif not validity_value_raw:
            errors.append("لا يمكن تحديد وحدة الصلاحية دون قيمة.")
        elif not validity_unit_raw:
            errors.append("لا يمكن تحديد قيمة الصلاحية دون وحدة.")
        else:
            try:
                validity_value = int(validity_value_raw)
                if validity_value < 1:
                    errors.append("قيمة الصلاحية يجب أن تكون رقمًا موجبًا (1 فأكثر).")
                    validity_value = None
            except ValueError:
                errors.append("قيمة الصلاحية يجب أن تكون رقمًا صحيحًا.")
                validity_value = None

            if validity_unit_raw not in VALIDITY_UNITS:
                errors.append("وحدة الصلاحية غير صالحة.")
                validity_unit = None
            else:
                validity_unit = validity_unit_raw

            if validity_value is not None and validity_unit == SubscriptionPlan.ValidityUnit.MONTHS:
                duration_months = validity_value
            else:
                duration_months = 0

    price = None
    if not price_raw:
        errors.append("الرجاء إدخال المبلغ.")
    else:
        try:
            price = Decimal(price_raw)
            if price < 0:
                errors.append("المبلغ لا يمكن أن يكون سالبًا.")
        except InvalidOperation:
            errors.append("المبلغ غير صالح.")

    minutes = 0
    if not minutes_raw:
        errors.append("الرجاء إدخال دقائق الباقة.")
    else:
        try:
            minutes = int(minutes_raw)
            if minutes < 0:
                errors.append("دقائق الباقة لا يمكن أن تكون سالبة.")
        except ValueError:
            errors.append("دقائق الباقة يجب أن تكون رقمًا صحيحًا.")

    sort_order = 0
    try:
        sort_order = int(sort_raw) if sort_raw else 0
        if sort_order < 0:
            errors.append("ترتيب العرض لا يمكن أن يكون سالبًا.")
    except ValueError:
        errors.append("ترتيب العرض يجب أن يكون رقمًا صحيحًا.")

    data = {
        "title": title,
        "validity_value": validity_value,
        "validity_unit": validity_unit,
        "is_open_ended": is_open_ended,
        "duration_months": duration_months,
        "price": price,
        "minutes": minutes,
        "description": description,
        "sort_order": sort_order,
        "is_active": is_active,
    }
    return data, errors


def _plan_form_initial_from_post(post, data):
    return {
        "title": post.get("title", ""),
        "validity_value": post.get("validity_value", ""),
        "validity_unit": post.get("validity_unit", ""),
        "is_open_ended": post.get("is_open_ended") == "on",
        "price": post.get("price", ""),
        "minutes": post.get("minutes", "0"),
        "description": post.get("description", ""),
        "sort_order": post.get("sort_order", "0"),
        "is_active": data.get("is_active", post.get("is_active") == "on"),
    }


def _plan_list_hidden_fields(*, q: str, active_filter: str) -> list[dict]:
    fields = []
    if q:
        fields.append({"name": "q", "value": q})
    if active_filter and active_filter != "all":
        fields.append({"name": "active", "value": active_filter})
    return fields


@login_required
@permissions_required("dashboard.access", "subscriptions.view")
def subscription_plan_list(request):
    q = (request.GET.get("q") or "").strip()
    active_filter = (request.GET.get("active") or "all").strip()

    qs = SubscriptionPlan.objects.all().order_by("sort_order", "id")
    if q:
        q_filter = Q(title__icontains=q) | Q(description__icontains=q)
        try:
            q_filter |= Q(price=Decimal(q.replace(",", ".")))
        except (InvalidOperation, ValueError):
            pass
        try:
            q_filter |= Q(validity_value=int(q)) | Q(duration_months=int(q))
        except ValueError:
            pass
        qs = qs.filter(q_filter)

    if active_filter == "active":
        qs = qs.filter(is_active=True)
    elif active_filter == "inactive":
        qs = qs.filter(is_active=False)

    page_obj, page_numbers, per_page_param, total_plans = paginate_with_smart_pages(
        request=request,
        queryset=qs,
        default_per_page="5",
    )

    pagination_qs = build_pagination_query_string(
        q=q,
        active=active_filter,
        per_page=per_page_param,
    )

    return render(
        request,
        "dashboard/pages/subscription_plans/list.html",
        {
            "plans": page_obj.object_list,
            "page_obj": page_obj,
            "page_numbers": page_numbers,
            "per_page": per_page_param,
            "total_plans": total_plans,
            "q": q,
            "active_filter": active_filter,
            "pagination_qs": pagination_qs,
            "pagination_hidden_fields": _plan_list_hidden_fields(
                q=q,
                active_filter=active_filter,
            ),
        },
    )


@login_required
@permissions_required("dashboard.access", "subscriptions.create")
def subscription_plan_create(request):
    initial = {
        "title": "",
        "validity_value": "",
        "validity_unit": SubscriptionPlan.ValidityUnit.MONTHS,
        "is_open_ended": False,
        "price": "",
        "minutes": "0",
        "description": "",
        "sort_order": "0",
        "is_active": True,
    }

    if request.method == "POST":
        data, errors = _parse_plan_form(request.POST)
        initial = _plan_form_initial_from_post(request.POST, data)

        if errors:
            for msg in errors:
                messages.error(request, msg)
        else:
            plan = SubscriptionPlan(
                title=data["title"],
                validity_value=data["validity_value"],
                validity_unit=data["validity_unit"],
                duration_months=data["duration_months"],
                price=data["price"],
                minutes=data["minutes"],
                description=data["description"],
                sort_order=data["sort_order"],
                is_active=data["is_active"],
            )
            plan.sync_legacy_duration_months()
            plan.save()
            messages.success(request, "تم إنشاء الباقة بنجاح.")
            return redirect("dashboard:subscription_plan_list")

    return render(
        request,
        "dashboard/pages/subscription_plans/form.html",
        {
            "title": "إضافة باقة اشتراك",
            "mode": "create",
            "initial": initial,
            "plan": None,
            "validity_unit_choices": SubscriptionPlan.ValidityUnit.choices,
        },
    )


@login_required
@permissions_required("dashboard.access", "subscriptions.update")
def subscription_plan_update(request, pk):
    plan = get_object_or_404(SubscriptionPlan, pk=pk)
    initial = {
        "title": plan.title,
        "validity_value": "" if plan.validity_value is None else str(plan.validity_value),
        "validity_unit": plan.validity_unit or SubscriptionPlan.ValidityUnit.MONTHS,
        "is_open_ended": plan.is_open_ended,
        "price": str(plan.price),
        "minutes": str(plan.minutes),
        "description": plan.description,
        "sort_order": str(plan.sort_order),
        "is_active": plan.is_active,
    }

    if request.method == "POST":
        data, errors = _parse_plan_form(request.POST)
        initial = _plan_form_initial_from_post(request.POST, data)

        if errors:
            for msg in errors:
                messages.error(request, msg)
        else:
            plan.title = data["title"]
            plan.validity_value = data["validity_value"]
            plan.validity_unit = data["validity_unit"]
            plan.duration_months = data["duration_months"]
            plan.price = data["price"]
            plan.minutes = data["minutes"]
            plan.description = data["description"]
            plan.sort_order = data["sort_order"]
            plan.is_active = data["is_active"]
            plan.sync_legacy_duration_months()
            plan.save()
            messages.success(request, "تم تحديث الباقة بنجاح.")
            return redirect("dashboard:subscription_plan_list")

    return render(
        request,
        "dashboard/pages/subscription_plans/form.html",
        {
            "title": "تعديل باقة اشتراك",
            "mode": "edit",
            "initial": initial,
            "plan": plan,
            "validity_unit_choices": SubscriptionPlan.ValidityUnit.choices,
        },
    )


@login_required
@permissions_required("dashboard.access", "subscriptions.delete")
def subscription_plan_delete(request, pk):
    plan = get_object_or_404(SubscriptionPlan, pk=pk)

    if request.method == "POST":
        plan.delete()
        messages.success(request, "تم حذف الباقة بنجاح.")
        return redirect("dashboard:subscription_plan_list")

    return render(
        request,
        "dashboard/pages/subscription_plans/confirm_delete.html",
        {"plan": plan},
    )


@login_required
@permissions_required("dashboard.access", "subscriptions.update")
@require_POST
def subscription_plan_toggle_active(request, pk):
    plan = get_object_or_404(SubscriptionPlan, pk=pk)
    plan.is_active = not plan.is_active
    plan.save(update_fields=["is_active", "updated_at"])
    if plan.is_active:
        messages.success(request, f"تم تفعيل «{plan.title}».")
    else:
        messages.success(request, f"تم تعطيل «{plan.title}».")
    return redirect("dashboard:subscription_plan_list")
