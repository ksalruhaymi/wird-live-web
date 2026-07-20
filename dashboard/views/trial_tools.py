"""Dashboard views for superuser-only trial cleanup tools."""

from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.calls.trial_cleanup import purge_all_call_data
from identity.accounts.trial_cleanup import (
    non_protected_users_queryset,
    purge_non_protected_users,
)
from identity.rbac.decorators import superuser_required

logger = logging.getLogger(__name__)

CONFIRM_PURGE_CALLS = "DELETE ALL CALLS"
CONFIRM_PURGE_USERS = "DELETE ALL USERS"


@login_required
@superuser_required
@require_http_methods(["GET", "POST"])
def purge_all_calls(request):
    if request.method == "GET":
        from apps.calls.models import (
            CallPeerRating,
            CallPeerRatingAnswer,
            CallRecording,
            CallRecordingConsent,
            CallSession,
            SessionEvaluation,
        )

        return render(
            request,
            "dashboard/pages/trial/confirm_purge_calls.html",
            {
                "confirm_phrase": CONFIRM_PURGE_CALLS,
                "counts": {
                    "call_sessions": CallSession.objects.count(),
                    "call_recordings": CallRecording.objects.count(),
                    "peer_ratings": CallPeerRating.objects.count(),
                    "peer_rating_answers": CallPeerRatingAnswer.objects.count(),
                    "recording_consents": CallRecordingConsent.objects.count(),
                    "session_evaluations": SessionEvaluation.objects.count(),
                },
            },
        )

    typed = (request.POST.get("confirmation") or "").strip()
    if typed != CONFIRM_PURGE_CALLS:
        messages.error(
            request,
            f"نص التأكيد غير صحيح. اكتب بالضبط: {CONFIRM_PURGE_CALLS}",
        )
        return redirect("dashboard:purge_all_calls")

    try:
        result = purge_all_call_data(actor=request.user)
    except Exception:
        logger.exception(
            "trial_purge_all_calls_failed actor=%s",
            request.user.username,
        )
        messages.error(request, "تعذر حذف المكالمات. راجع سجلات النظام.")
        return redirect("dashboard:purge_all_calls")

    deleted = result["deleted"]
    messages.success(
        request,
        (
            "تم حذف بيانات المكالمات: "
            f"جلسات={deleted['call_sessions']}، "
            f"تسجيلات={deleted['call_recordings']}، "
            f"تقييمات={deleted['peer_ratings']}، "
            f"إجابات={deleted['peer_rating_answers']}، "
            f"موافقات={deleted['recording_consents']}، "
            f"تقييمات جلسات={deleted['session_evaluations']}، "
            f"R2 محذوف={result['r2_deleted']} (فشل={result['r2_failed']})."
        ),
    )
    return redirect(f"{reverse('dashboard:call_session_list')}?tab=log")


@login_required
@superuser_required
@require_http_methods(["GET", "POST"])
def purge_non_protected_users_view(request):
    if request.method == "GET":
        victims = non_protected_users_queryset(actor=request.user)
        return render(
            request,
            "dashboard/pages/trial/confirm_purge_users.html",
            {
                "confirm_phrase": CONFIRM_PURGE_USERS,
                "victim_count": victims.count(),
                "victim_sample": list(
                    victims.values_list("id", "username")[:30]
                ),
            },
        )

    typed = (request.POST.get("confirmation") or "").strip()
    if typed != CONFIRM_PURGE_USERS:
        messages.error(
            request,
            f"نص التأكيد غير صحيح. اكتب بالضبط: {CONFIRM_PURGE_USERS}",
        )
        return redirect("dashboard:purge_non_protected_users")

    try:
        result = purge_non_protected_users(actor=request.user)
    except Exception:
        logger.exception(
            "trial_purge_users_failed actor=%s",
            request.user.username,
        )
        messages.error(request, "تعذر حذف المستخدمين. راجع سجلات النظام.")
        return redirect("dashboard:purge_non_protected_users")

    messages.success(
        request,
        (
            "تم حذف المستخدمين غير المحميين: "
            f"مستخدمون={result['deleted_users_count']}، "
            f"تسجيلات={result['recordings_removed']}، "
            f"R2 محذوف={result['r2_deleted']} (فشل={result['r2_failed']})، "
            f"المتبقي={result['preserved_count']}."
        ),
    )
    return redirect(f"{reverse('dashboard:dashboard_users_list')}?tab=teachers")
