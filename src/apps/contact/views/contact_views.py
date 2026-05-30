import re

from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from ..services import handle_contact


CONTACT_RATE_LIMIT_SECONDS = 60
MAX_FULL_NAME_LENGTH = 150
MAX_EMAIL_LENGTH = 254
MAX_PHONE_LENGTH = 20
MAX_MESSAGE_LENGTH = 5000


def _clean_contact_input(request):
    full_name = (request.POST.get("full_name") or "").strip()
    email = (request.POST.get("email") or "").strip().lower()
    phone = re.sub(r"\D", "", (request.POST.get("phone") or "").strip())
    message = (request.POST.get("message") or "").strip()

    return {
        "full_name": full_name,
        "email": email,
        "phone": phone,
        "message": message,
    }


def _validate_contact_input(data):
    errors = {}

    if len(data["full_name"]) > MAX_FULL_NAME_LENGTH:
        errors["full_name"] = "الاسم طويل جدًا"

    if len(data["email"]) > MAX_EMAIL_LENGTH:
        errors["email"] = "البريد طويل جدًا"

    if len(data["phone"]) > MAX_PHONE_LENGTH:
        errors["phone"] = "رقم الجوال غير صحيح"

    if len(data["message"]) > MAX_MESSAGE_LENGTH:
        errors["message"] = "نص الرسالة طويل جدًا"

    return errors


def _is_rate_limited(request):
    last_submit_ts = request.session.get("contact_last_submit_ts")
    if not last_submit_ts:
        return False

    try:
        import time
        return (time.time() - float(last_submit_ts)) < CONTACT_RATE_LIMIT_SECONDS
    except (TypeError, ValueError):
        return False


def _mark_contact_submitted(request):
    import time
    request.session["contact_last_submit_ts"] = time.time()
    request.session["contact_success_allowed"] = True


@never_cache
@sensitive_post_parameters("email", "phone", "message")
@require_http_methods(["GET", "POST"])
def contact_view(request):
    data = {
        "full_name": "",
        "email": "",
        "phone": "",
        "message": "",
    }
    errors = {}

    if request.method == "POST":
        # Honeypot field for simple bot detection
        if (request.POST.get("website") or "").strip():
            _mark_contact_submitted(request)
            return redirect("contact:success")

        data = _clean_contact_input(request)

        input_errors = _validate_contact_input(data)
        if input_errors:
            errors.update(input_errors)
        elif _is_rate_limited(request):
            errors["__all__"] = "تم الإرسال مؤخرًا، حاول مرة أخرى بعد قليل"
        else:
            _, service_errors = handle_contact(data)
            if service_errors:
                errors.update(service_errors)
            else:
                _mark_contact_submitted(request)
                return redirect("contact:success")

    return render(
        request,
        "contact/contact.html",
        {
            "data": data,
            "errors": errors,
        },
    )


@never_cache
@require_http_methods(["GET"])
def contact_success(request):
    if not request.session.pop("contact_success_allowed", False):
        return redirect("contact:contact")

    return render(request, "contact/success.html")