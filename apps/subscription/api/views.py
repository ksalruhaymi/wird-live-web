import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from apps.subscription.models import StudentSubscription, SubscriptionPlan
from apps.subscription.services import (
    call_eligibility_payload,
    create_student_subscription,
    current_subscription_payload,
    is_student_user,
    subscription_to_payload,
    STUDENT_ONLY_SUBSCRIPTION_MESSAGE,
)


def _plan_payload(plan: SubscriptionPlan) -> dict:
    return {
        "id": plan.id,
        "title": plan.title,
        "duration_months": plan.duration_months,
        "price": str(plan.price),
        "minutes": plan.minutes,
        "description": plan.description,
        "sort_order": plan.sort_order,
    }


def _require_auth_json(request) -> JsonResponse | None:
    if request.user.is_authenticated:
        return None
    return JsonResponse(
        {"success": False, "message": "يجب تسجيل الدخول."},
        status=401,
    )


def _parse_json_body(request) -> tuple[dict | None, JsonResponse | None]:
    try:
        raw = request.body.decode("utf-8") if request.body else "{}"
        data = json.loads(raw or "{}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, JsonResponse({"success": False, "message": "JSON غير صالح."}, status=400)
    if not isinstance(data, dict):
        return None, JsonResponse(
            {"success": False, "message": "تنسيق البيانات غير صحيح."},
            status=400,
        )
    return data, None


@csrf_exempt
@require_GET
def list_plans(request):
    plans = SubscriptionPlan.objects.filter(is_active=True).order_by("sort_order", "id")
    return JsonResponse(
        {
            "success": True,
            "plans": [_plan_payload(p) for p in plans],
        }
    )


@csrf_exempt
@require_GET
def current_subscription(request):
    auth_err = _require_auth_json(request)
    if auth_err:
        return auth_err
    return JsonResponse(current_subscription_payload(request.user))


@csrf_exempt
@require_GET
def call_eligibility(request):
    auth_err = _require_auth_json(request)
    if auth_err:
        return auth_err
    return JsonResponse(call_eligibility_payload(request.user))


@csrf_exempt
@require_POST
def subscribe(request):
    auth_err = _require_auth_json(request)
    if auth_err:
        return auth_err

    if not is_student_user(request.user):
        return JsonResponse(
            {"success": False, "message": STUDENT_ONLY_SUBSCRIPTION_MESSAGE},
            status=403,
        )

    data, err = _parse_json_body(request)
    if err:
        return err

    plan_id_raw = data.get("plan_id")
    try:
        plan_id = int(plan_id_raw)
    except (TypeError, ValueError):
        return JsonResponse(
            {"success": False, "message": "معرّف الباقة غير صالح."},
            status=400,
        )

    payment_method = (data.get("payment_method") or "manual").strip() or "manual"

    sub, error = create_student_subscription(
        request.user,
        plan_id=plan_id,
        payment_method=payment_method,
    )
    if error:
        return JsonResponse({"success": False, "message": error}, status=400)

    return JsonResponse(
        {
            "success": True,
            "subscription": subscription_to_payload(sub),
        },
        status=201,
    )


@csrf_exempt
@require_GET
def my_subscriptions(request):
    auth_err = _require_auth_json(request)
    if auth_err:
        return auth_err

    if not is_student_user(request.user):
        return JsonResponse(
            {
                "success": True,
                "applicable": False,
                "subscriptions": [],
                "message": STUDENT_ONLY_SUBSCRIPTION_MESSAGE,
            }
        )

    subs = (
        StudentSubscription.objects.filter(user=request.user)
        .select_related("plan")
        .order_by("-created_at", "-id")
    )
    return JsonResponse(
        {
            "success": True,
            "subscriptions": [subscription_to_payload(s, include_display=True) for s in subs],
        }
    )
