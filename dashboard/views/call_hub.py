import logging

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from apps.calls.models import (
    CallPeerRating,
    CallRecording,
    CallSession,
    RatingCategoryConfig,
    RatingQuestion,
)
from apps.calls.rating_service import CATEGORY_LABELS_AR
from apps.calls.recording_storage import (
    RecordingStorageError,
    generate_recording_signed_url,
    object_key_for_recording,
    playback_content_type_for_key,
)
from core.utils.pagination import build_pagination_query_string, paginate_with_smart_pages
from identity.rbac.decorators import permissions_required
from identity.rbac.resolver import user_has_permission

logger = logging.getLogger(__name__)

TAB_LOG = "log"
TAB_RECORDINGS = "recordings"
TAB_RATINGS = "ratings"
TAB_RATING_SETTINGS = "rating-settings"
_VALID_TABS = {TAB_LOG, TAB_RECORDINGS, TAB_RATINGS, TAB_RATING_SETTINGS}
_LEGACY_TAB_MAP = {
    "settings": TAB_RATING_SETTINGS,
    "users": TAB_RATINGS,
}

_TAB_PERMISSIONS = {
    TAB_LOG: "calls.view",
    TAB_RECORDINGS: "recordings.view",
    TAB_RATINGS: "evaluations.view",
    TAB_RATING_SETTINGS: "evaluations.view",
}

_TAB_ORDER = [TAB_LOG, TAB_RECORDINGS, TAB_RATINGS, TAB_RATING_SETTINGS]


def _user_display_name(user) -> str:
    if not user:
        return "—"
    return (user.full_name or user.get_full_name() or user.username or "—").strip()


def _session_type_label(call: CallSession) -> str:
    if call.is_interview_call:
        return "مقابلة"
    return call.get_session_type_display()


def _duration_display(call: CallSession) -> str:
    if call.started_at and call.ended_at:
        delta = call.ended_at - call.started_at
        total = int(delta.total_seconds())
        minutes, seconds = divmod(total, 60)
        if minutes:
            return f"{minutes} د {seconds} ث"
        return f"{seconds} ث"
    if call.status == CallSession.Status.ACTIVE and call.started_at:
        return "جارية"
    return "—"


def _attach_playback_urls(rows) -> None:
    for row in rows:
        row.signed_playback_url = None
        row.signed_playback_type = "audio/mp4"
        row.playback_unavailable = False

        object_key = object_key_for_recording(row)
        if not object_key:
            continue

        row.signed_playback_type = playback_content_type_for_key(object_key)
        try:
            row.signed_playback_url, _ = generate_recording_signed_url(object_key)
        except RecordingStorageError as exc:
            row.playback_unavailable = True
            logger.warning(
                "Dashboard signed URL failed for recording %s (key=%s): %s",
                row.id,
                object_key,
                exc,
            )


def _user_can_access_tab(user, tab: str) -> bool:
    code = _TAB_PERMISSIONS.get(tab)
    return bool(code and user_has_permission(user, code))


def _first_allowed_tab(user) -> str | None:
    for tab in _TAB_ORDER:
        if _user_can_access_tab(user, tab):
            return tab
    return None


def _resolve_tab(user, raw_tab: str) -> str:
    tab = _LEGACY_TAB_MAP.get(raw_tab, raw_tab)
    if tab not in _VALID_TABS:
        tab = TAB_LOG
    if _user_can_access_tab(user, tab):
        return tab
    return _first_allowed_tab(user) or tab


def _recording_ui_summary(recording: CallRecording | None) -> dict:
    if recording is None:
        return {
            "has_recording": False,
            "playable": False,
            "recording_id": None,
        }
    return {
        "has_recording": True,
        "playable": bool(object_key_for_recording(recording)),
        "recording_id": recording.id,
    }


def _ratings_ui_summary(peer_ratings) -> dict:
    ratings = list(peer_ratings)
    total = len(ratings)
    completed = sum(
        1 for rating in ratings if rating.status == CallPeerRating.Status.COMPLETED
    )
    scores = []
    for rating in ratings:
        for value in (rating.competence, rating.clarity, rating.audio_quality):
            if value is not None:
                scores.append(value)
    if total == 0:
        return {
            "ratings_total": 0,
            "ratings_completed": 0,
            "ratings_ratio": "—",
            "ratings_status_label": "لا يوجد",
            "ratings_status_key": "none",
            "ratings_score_display": None,
        }
    if completed == total:
        status_label = "مكتمل"
        status_key = "complete"
    else:
        status_label = "غير مكتمل"
        status_key = "incomplete"
    if scores:
        avg_score = round(sum(scores) / len(scores), 1)
        score_display = f"{avg_score:g}/5"
    else:
        score_display = f"{completed}/{total}"
    return {
        "ratings_total": total,
        "ratings_completed": completed,
        "ratings_ratio": f"{completed}/{total}",
        "ratings_status_label": status_label,
        "ratings_status_key": status_key,
        "ratings_score_display": score_display,
    }


def _hidden_fields_for_tab(tab: str, extra: list[dict] | None = None) -> list[dict]:
    hidden = [{"name": "tab", "value": tab}]
    if extra:
        hidden.extend(extra)
    return hidden


def _build_log_context(request, tab: str):
    q = (request.GET.get("q") or "").strip()
    type_filter = (request.GET.get("type") or "all").strip()
    status_filter = (request.GET.get("status") or "all").strip()

    qs = (
        CallSession.objects.select_related("student", "teacher", "recording")
        .prefetch_related(
            Prefetch(
                "peer_ratings",
                queryset=CallPeerRating.objects.order_by("rater_role", "id"),
            )
        )
        .order_by("-created_at", "-id")
    )

    if q:
        qs = qs.filter(
            Q(student__username__icontains=q)
            | Q(student__email__icontains=q)
            | Q(student__full_name__icontains=q)
            | Q(teacher__username__icontains=q)
            | Q(teacher__email__icontains=q)
            | Q(channel_name__icontains=q)
        )

    if type_filter in {CallSession.SessionType.AUDIO, CallSession.SessionType.VIDEO}:
        qs = qs.filter(session_type=type_filter)

    if status_filter in {s[0] for s in CallSession.Status.choices}:
        qs = qs.filter(status=status_filter)

    page_obj, page_numbers, per_page_param, total_calls = paginate_with_smart_pages(
        request=request,
        queryset=qs,
        default_per_page="5",
    )

    rows = []
    for call in page_obj.object_list:
        recording = getattr(call, "recording", None)
        rows.append(
            {
                "call": call,
                "duration": _duration_display(call),
                "recording": _recording_ui_summary(recording),
                "ratings": _ratings_ui_summary(call.peer_ratings.all()),
            }
        )

    pagination_kwargs = {"tab": tab, "q": q, "per_page": per_page_param}
    if type_filter != "all":
        pagination_kwargs["type"] = type_filter
    if status_filter != "all":
        pagination_kwargs["status"] = status_filter
    pagination_qs = build_pagination_query_string(**pagination_kwargs)

    hidden_fields = _hidden_fields_for_tab(tab)
    if q:
        hidden_fields.append({"name": "q", "value": q})
    if type_filter != "all":
        hidden_fields.append({"name": "type", "value": type_filter})
    if status_filter != "all":
        hidden_fields.append({"name": "status", "value": status_filter})
    if per_page_param:
        hidden_fields.append({"name": "per_page", "value": per_page_param})

    return {
        "rows": rows,
        "page_obj": page_obj,
        "page_numbers": page_numbers,
        "per_page": per_page_param,
        "total_calls": total_calls,
        "q": q,
        "type_filter": type_filter,
        "status_filter": status_filter,
        "pagination_qs": pagination_qs,
        "pagination_hidden_fields": hidden_fields,
    }


def _build_recordings_context(request, tab: str):
    q = (request.GET.get("q") or "").strip()

    qs = CallRecording.objects.select_related(
        "call_session", "student", "teacher"
    ).order_by("-created_at", "-id")

    if q:
        qs = qs.filter(
            Q(student__username__icontains=q)
            | Q(teacher__username__icontains=q)
            | Q(recording_url__icontains=q)
            | Q(recording_object_key__icontains=q)
        )

    page_obj, page_numbers, per_page_param, total_recordings = paginate_with_smart_pages(
        request=request,
        queryset=qs,
        default_per_page="5",
    )

    rows = list(page_obj.object_list)
    _attach_playback_urls(rows)

    pagination_qs = build_pagination_query_string(
        tab=tab, q=q, per_page=per_page_param
    )

    hidden_fields = _hidden_fields_for_tab(tab)
    if q:
        hidden_fields.append({"name": "q", "value": q})
    if per_page_param:
        hidden_fields.append({"name": "per_page", "value": per_page_param})

    return {
        "rows": rows,
        "page_obj": page_obj,
        "page_numbers": page_numbers,
        "per_page": per_page_param,
        "total_recordings": total_recordings,
        "q": q,
        "pagination_qs": pagination_qs,
        "pagination_hidden_fields": hidden_fields,
    }


def _build_ratings_context(request, tab: str):
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
        tab=tab,
        q=q,
        status=status_filter,
        per_page=per_page_param,
    )

    hidden_fields = _hidden_fields_for_tab(tab)
    if q:
        hidden_fields.append({"name": "q", "value": q})
    if status_filter != "all":
        hidden_fields.append({"name": "status", "value": status_filter})
    if per_page_param:
        hidden_fields.append({"name": "per_page", "value": per_page_param})

    return {
        "rows": page_obj.object_list,
        "page_obj": page_obj,
        "page_numbers": page_numbers,
        "per_page": per_page_param,
        "total_rows": total_rows,
        "q": q,
        "status_filter": status_filter,
        "status_choices": CallPeerRating.Status.choices,
        "role_choices": CallPeerRating.RaterRole.choices,
        "pagination_qs": pagination_qs,
        "pagination_hidden_fields": hidden_fields,
    }


def _build_rating_settings_context():
    category_configs = {
        row.category: row for row in RatingCategoryConfig.objects.all()
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
    return {
        "question_groups": question_groups,
        "category_labels": CATEGORY_LABELS_AR,
    }


@login_required
@permissions_required("dashboard.access")
def call_hub_list(request):
    if not _first_allowed_tab(request.user):
        raise PermissionDenied

    raw_tab = (request.GET.get("tab") or "").strip()
    if raw_tab in {TAB_RECORDINGS, TAB_RATINGS}:
        return redirect(f"{reverse('dashboard:call_session_list')}?tab={TAB_LOG}")

    tab = _resolve_tab(request.user, raw_tab or TAB_LOG)

    context = {
        "tab": tab,
        "can_log": _user_can_access_tab(request.user, TAB_LOG),
        "can_recordings": _user_can_access_tab(request.user, TAB_RECORDINGS),
        "can_ratings": _user_can_access_tab(request.user, TAB_RATINGS),
        "can_rating_settings": _user_can_access_tab(request.user, TAB_RATING_SETTINGS),
        "tab_log_active": "1" if tab == TAB_LOG else "",
        "tab_recordings_active": "1" if tab == TAB_RECORDINGS else "",
        "tab_ratings_active": "1" if tab == TAB_RATINGS else "",
        "tab_settings_active": "1" if tab == TAB_RATING_SETTINGS else "",
    }

    if tab == TAB_LOG and context["can_log"]:
        context.update(_build_log_context(request, tab))
    elif tab == TAB_RECORDINGS and context["can_recordings"]:
        context.update(_build_recordings_context(request, tab))
    elif tab == TAB_RATINGS and context["can_ratings"]:
        context.update(_build_ratings_context(request, tab))
    elif tab == TAB_RATING_SETTINGS and context["can_rating_settings"]:
        context.update(_build_rating_settings_context())

    return render(request, "dashboard/pages/calls/hub.html", context)


@login_required
@permissions_required("dashboard.access", "calls.view")
def call_session_detail(request, session_id):
    call = get_object_or_404(
        CallSession.objects.select_related("student", "teacher", "recording")
        .prefetch_related(
            Prefetch(
                "peer_ratings",
                queryset=CallPeerRating.objects.select_related(
                    "rater", "rated"
                ).order_by("rater_role", "id"),
            )
        ),
        pk=session_id,
    )
    recording = getattr(call, "recording", None)
    user = request.user
    return render(
        request,
        "dashboard/pages/calls/session_detail.html",
        {
            "call": call,
            "duration": _duration_display(call),
            "session_type_label": _session_type_label(call),
            "peer_ratings": list(call.peer_ratings.all()),
            "recording": recording,
            "recording_summary": _recording_ui_summary(recording),
            "can_recordings": user_has_permission(user, "recordings.view"),
            "can_recordings_delete": user_has_permission(user, "recordings.delete"),
            "can_ratings": user_has_permission(user, "evaluations.view"),
        },
    )


@login_required
@permissions_required("dashboard.access", "recordings.view")
def call_recording_playback_url(request, pk):
    recording = get_object_or_404(
        CallRecording.objects.select_related("call_session"),
        pk=pk,
    )
    object_key = object_key_for_recording(recording)
    if not object_key:
        return JsonResponse(
            {"success": False, "error": "لا يوجد ملف تسجيل قابل للتشغيل."},
            status=404,
        )
    try:
        playback_url, expires_in = generate_recording_signed_url(object_key)
    except RecordingStorageError:
        return JsonResponse(
            {"success": False, "error": "تعذر تجهيز رابط التشغيل."},
            status=503,
        )
    return JsonResponse(
        {
            "success": True,
            "playback_url": playback_url,
            "content_type": playback_content_type_for_key(object_key),
            "expires_in": expires_in,
        }
    )


@login_required
@permissions_required("dashboard.access", "evaluations.view")
def call_session_ratings_detail(request, session_id):
    call = get_object_or_404(
        CallSession.objects.prefetch_related("peer_ratings"),
        pk=session_id,
    )
    ratings = []
    for rating in call.peer_ratings.all().order_by("rater_role", "id"):
        ratings.append(
            {
                "id": rating.id,
                "rater_role": rating.get_rater_role_display(),
                "status": rating.get_status_display(),
                "status_key": rating.status,
                "competence": rating.competence,
                "clarity": rating.clarity,
                "audio_quality": rating.audio_quality,
            }
        )
    summary = _ratings_ui_summary(call.peer_ratings.all())
    return JsonResponse(
        {
            "success": True,
            "call_id": call.id,
            "summary": summary,
            "ratings": ratings,
        }
    )
