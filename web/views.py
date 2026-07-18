import re
import time

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from core.models import SiteStat

ACCOUNT_DELETION_RATE_LIMIT_SECONDS = 120
MAX_USERNAME_LENGTH = 150
MAX_EMAIL_LENGTH = 254
SUPPORT_EMAIL = "support@wird.me"


def home(request):
    visitors = SiteStat.objects.filter(key="visitors").first()
    return render(
        request,
        "web/pages/home.html",
        {
            "visitors_count": visitors.value if visitors else 0,
        },
    )


def about(request):
    return render(request, "web/pages/about.html")


def privacy_policy(request):
    return render(request, "web/pages/privacy_policy.html")


def _clean_account_deletion_request(request):
    return {
        "username": (request.POST.get("username") or "").strip()[:MAX_USERNAME_LENGTH],
        "email": (request.POST.get("email") or "").strip().lower()[:MAX_EMAIL_LENGTH],
        "notes": (request.POST.get("notes") or "").strip()[:1000],
    }


def _validate_account_deletion_request(data):
    errors = {}
    if not data["username"]:
        errors["username"] = "username_required"
    if not data["email"]:
        errors["email"] = "email_required"
    else:
        try:
            validate_email(data["email"])
        except ValidationError:
            errors["email"] = "email_invalid"
    return errors


def _is_account_deletion_rate_limited(request):
    last_ts = request.session.get("account_deletion_last_submit_ts")
    if not last_ts:
        return False
    try:
        return (time.time() - float(last_ts)) < ACCOUNT_DELETION_RATE_LIMIT_SECONDS
    except (TypeError, ValueError):
        return False


def _send_account_deletion_request_email(data, *, client_ip: str = ""):
    recipient = getattr(settings, "CONTACT_RECIPIENT_EMAIL", None) or SUPPORT_EMAIL
    body = (
        "Account deletion request (public web form — identity not verified).\n"
        "Do NOT delete automatically. Verify the requester before acting.\n\n"
        f"Username: {data['username']}\n"
        f"Email: {data['email']}\n"
        f"Notes: {data['notes'] or '-'}\n"
        f"Client IP: {client_ip or '-'}\n"
    )
    send_mail(
        subject=f"[Wird Live] Account deletion request: {data['username']}",
        message=body,
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None) or SUPPORT_EMAIL,
        recipient_list=[recipient, SUPPORT_EMAIL]
        if recipient != SUPPORT_EMAIL
        else [SUPPORT_EMAIL],
        fail_silently=False,
    )


@never_cache
@csrf_protect
@require_http_methods(["GET", "POST"])
def account_deletion(request):
    data = {"username": "", "email": "", "notes": ""}
    errors = {}
    success = False

    if request.method == "POST":
        # Honeypot — bots fill hidden fields; pretend success without emailing.
        if (request.POST.get("company") or "").strip():
            request.session["account_deletion_last_submit_ts"] = time.time()
            success = True
        else:
            data = _clean_account_deletion_request(request)
            errors = _validate_account_deletion_request(data)
            if not errors and _is_account_deletion_rate_limited(request):
                errors["form"] = "rate_limited"
            elif not errors:
                try:
                    client_ip = (
                        request.META.get("HTTP_X_FORWARDED_FOR", "")
                        .split(",")[0]
                        .strip()
                        or request.META.get("REMOTE_ADDR", "")
                    )
                    # Strip non-printable noise from IP for logs/email only.
                    client_ip = re.sub(r"[^\w\.:\-]", "", client_ip)[:64]
                    _send_account_deletion_request_email(data, client_ip=client_ip)
                    request.session["account_deletion_last_submit_ts"] = time.time()
                    success = True
                    data = {"username": "", "email": "", "notes": ""}
                except Exception:
                    errors["form"] = "send_failed"

    return render(
        request,
        "web/pages/account_deletion.html",
        {
            "data": data,
            "errors": errors,
            "success": success,
            "support_email": SUPPORT_EMAIL,
        },
    )
