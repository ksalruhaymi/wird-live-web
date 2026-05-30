# File: apps/contact/dashboard_views.py
# Description: Handles contact messages in dashboard (list, view, reply, mark as replied)

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from ..models import ContactMessage
from ..services import send_contact_reply


ALLOWED_TABS = {"list", "unread", "replied"}
MAX_SEARCH_LENGTH = 100
MAX_REPLY_SUBJECT_LENGTH = 200
MAX_REPLY_BODY_LENGTH = 5000
REPLY_RATE_LIMIT_SECONDS = 10


def _clean_tab(raw_tab):
    tab = (raw_tab or "list").strip().lower()
    return tab if tab in ALLOWED_TABS else "list"


def _clean_search_query(raw_q):
    q = (raw_q or "").strip()
    if len(q) > MAX_SEARCH_LENGTH:
        q = q[:MAX_SEARCH_LENGTH]
    return q


def _clean_reply_input(request):
    subject = (request.POST.get("subject") or "").strip()
    body = (request.POST.get("body") or "").strip()

    if len(subject) > MAX_REPLY_SUBJECT_LENGTH:
        subject = subject[:MAX_REPLY_SUBJECT_LENGTH]

    if len(body) > MAX_REPLY_BODY_LENGTH:
        body = body[:MAX_REPLY_BODY_LENGTH]

    return subject, body


def _validate_reply_input(subject, body):
    errors = {}

    if not subject:
        errors["subject"] = "عنوان الرد مطلوب"

    if not body:
        errors["body"] = "نص الرد مطلوب"

    return errors


def _is_reply_rate_limited(request, message_id):
    key = f"contact_reply_last_submit_{message_id}"
    last_submit_ts = request.session.get(key)
    if not last_submit_ts:
        return False

    try:
        import time
        return (time.time() - float(last_submit_ts)) < REPLY_RATE_LIMIT_SECONDS
    except (TypeError, ValueError):
        return False


def _mark_reply_submitted(request, message_id):
    import time
    key = f"contact_reply_last_submit_{message_id}"
    request.session[key] = time.time()


@never_cache
@require_GET
@login_required
# Purpose: List and filter contact messages with pagination
def list_messages(request):
    tab = _clean_tab(request.GET.get("tab"))
    q = _clean_search_query(request.GET.get("q"))
    per_page = (request.GET.get("per_page") or "5").strip()

    qs = ContactMessage.objects.all().order_by("-created_at")

    if tab == "unread":
        qs = qs.filter(status=ContactMessage.Status.NEW)
    elif tab == "replied":
        qs = qs.filter(status=ContactMessage.Status.REPLIED)

    if q:
        qs = qs.filter(
            Q(full_name__icontains=q)
            | Q(email__icontains=q)
            | Q(phone__icontains=q)
            | Q(message__icontains=q)
        )

    total_messages = qs.count()

    if per_page == "all":
        page_obj = qs
        page_numbers = []
    else:
        try:
            per_page_int = int(per_page)
        except ValueError:
            per_page_int = 5

        paginator = Paginator(qs, per_page_int)
        page_number = request.GET.get("page")
        page_obj = paginator.get_page(page_number)
        page_numbers = paginator.get_elided_page_range(
            number=page_obj.number,
            on_each_side=1,
            on_ends=1,
        )

    return render(
        request,
        "dashboard/contact/list.html",
        {
            "contact_messages": page_obj,
            "page_obj": page_obj,
            "page_numbers": page_numbers,
            "tab": tab,
            "q": q,
            "per_page": per_page,
            "total_messages": total_messages,
        },
    )
@never_cache
@sensitive_post_parameters("subject", "body")
@require_http_methods(["GET", "POST"])
@login_required
# Purpose: Display a single message, mark it as read, and handle reply submission
def detail_message(request, pk):
    message_obj = get_object_or_404(ContactMessage, pk=pk)
    tab = _clean_tab(request.GET.get("tab"))
    errors = {}

    reply_data = {
        "subject": message_obj.reply_subject or "رد على رسالتك في موقعنا",
        "body": message_obj.reply_body or "",
    }

    if request.method == "GET" and message_obj.status == ContactMessage.Status.NEW:
        message_obj.status = ContactMessage.Status.READ
        message_obj.is_read = True
        message_obj.save(update_fields=["status", "is_read"])

    if request.method == "POST":
        subject, body = _clean_reply_input(request)

        reply_data["subject"] = subject
        reply_data["body"] = body

        errors.update(_validate_reply_input(subject, body))

        if not errors and _is_reply_rate_limited(request, message_obj.pk):
            errors["general"] = "تم إرسال رد قبل لحظات، حاول مرة أخرى بعد قليل"

        if not errors:
            #send_contact_reply(message_obj, subject, body)

            message_obj.reply_subject = subject
            message_obj.reply_body = body
            message_obj.replied_by = request.user
            message_obj.replied_at = timezone.now()
            message_obj.status = ContactMessage.Status.REPLIED
            message_obj.is_read = True
            message_obj.save(
                update_fields=[
                    "reply_subject",
                    "reply_body",
                    "replied_by",
                    "replied_at",
                    "status",
                    "is_read",
                ]
            )

            _mark_reply_submitted(request, message_obj.pk)

            return redirect(
                f"{reverse('contact:dashboard_detail', args=[message_obj.pk])}?replied=1"
            )

    return render(
        request,
        "dashboard/contact/detail.html",
        {
            "message": message_obj,
            "tab": tab,
            "reply_data": reply_data,
            "errors": errors,
            "general_error": errors.get("general", ""),
        },
    )


@never_cache
@require_POST
@login_required
# Purpose: Mark message as replied without sending an email
def mark_replied(request, pk):
    message_obj = get_object_or_404(ContactMessage, pk=pk)

    if message_obj.status != ContactMessage.Status.REPLIED:
        message_obj.status = ContactMessage.Status.REPLIED
        message_obj.replied_at = timezone.now()
        message_obj.is_read = True
        message_obj.save(update_fields=["status", "replied_at", "is_read"])

    return redirect("contact:dashboard_detail", pk=message_obj.pk)