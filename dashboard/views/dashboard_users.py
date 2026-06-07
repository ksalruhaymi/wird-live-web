import logging
import mimetypes

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, render

from apps.calls.models import CallPeerRating, CallSession, SessionEvaluation
from apps.calls.recording_storage import (
    RecordingStorageError,
    generate_recording_signed_url,
    object_key_for_recording,
    playback_content_type_for_key,
)
from apps.tutoring.models import TeacherProfile
from apps.tutoring.teacher_approval_service import (
    approval_status_label,
    teacher_approval_payload,
)
from apps.tutoring.teacher_services import (
    COMPUTED_AVAILABLE,
    COMPUTED_BUSY,
    COMPUTED_OFFLINE,
    compute_teacher_status,
    computed_status_label,
    teacher_display_name,
    _active_teacher_ids,
)
from apps.subscription.models import StudentSubscription
from apps.subscription.services import (
    balance_display_status,
    display_status,
    display_status_label,
    get_user_subscription_balance,
)
from core.utils.pagination import build_pagination_query_string, paginate_with_smart_pages
from identity.accounts.auth.profile_service import build_profile_payload
from identity.accounts.user_types import USER_TYPE_STUDENT, USER_TYPE_TEACHER, user_type_label
from identity.rbac.decorators import permissions_required

User = get_user_model()
logger = logging.getLogger(__name__)


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


TAB_TEACHERS = "teachers"
TAB_STUDENTS = "students"
_LIST_TABS = {TAB_TEACHERS, TAB_STUDENTS}

DETAIL_TAB_PROFILE = "profile"
DETAIL_TAB_SESSIONS = "sessions"
DETAIL_TAB_CALLS = "calls"
DETAIL_TAB_EVALUATIONS = "evaluations"
DETAIL_TAB_SUBSCRIPTIONS = "subscriptions"
_TEACHER_DETAIL_TABS = {
    DETAIL_TAB_PROFILE,
    DETAIL_TAB_SESSIONS,
    DETAIL_TAB_CALLS,
    DETAIL_TAB_EVALUATIONS,
}
_STUDENT_DETAIL_TABS = _TEACHER_DETAIL_TABS | {DETAIL_TAB_SUBSCRIPTIONS}

FILTER_ALL = "all"
FILTER_ACTIVE = "active"
FILTER_INACTIVE = "inactive"
FILTER_SUB_ACTIVE = "active"
FILTER_SUB_EXPIRED = "expired"
FILTER_SUB_NONE = "none"

_GENDER_LABELS = {
    "male": "ذكر",
    "female": "أنثى",
}


def _gender_label(user) -> str:
    gender = (getattr(user, "gender", None) or "").strip()
    return _GENDER_LABELS.get(gender, "—")


def _ijazah_file_kind(filename: str) -> str:
    ext = (filename or "").rsplit(".", 1)[-1].lower()
    if ext in {"png", "jpg", "jpeg", "gif", "webp"}:
        return "image"
    if ext == "pdf":
        return "pdf"
    return "file"


def _session_counts_for_teachers(teacher_ids: list[int]) -> dict[int, int]:
    if not teacher_ids:
        return {}
    rows = (
        CallSession.objects.filter(teacher_id__in=teacher_ids)
        .values("teacher_id")
        .annotate(count=Count("id"))
    )
    return {row["teacher_id"]: row["count"] for row in rows}


def _session_counts_for_students(student_ids: list[int]) -> dict[int, int]:
    if not student_ids:
        return {}
    rows = (
        CallSession.objects.filter(student_id__in=student_ids)
        .values("student_id")
        .annotate(count=Count("id"))
    )
    return {row["student_id"]: row["count"] for row in rows}


def _build_teacher_rows(q: str, status_filter: str, account_filter: str):
    qs = User.objects.filter(
        user_type=USER_TYPE_TEACHER,
        teacher_profile__isnull=False,
    ).select_related("teacher_profile", "teacher_availability")

    if q:
        qs = qs.filter(
            Q(username__icontains=q)
            | Q(email__icontains=q)
            | Q(full_name__icontains=q)
            | Q(mobile__icontains=q)
            | Q(teacher_profile__display_name__icontains=q)
        )

    teachers = list(qs.order_by("teacher_profile__display_name", "username"))
    active_ids = _active_teacher_ids()
    session_counts = _session_counts_for_teachers([t.id for t in teachers])

    rows = []
    for user in teachers:
        profile = user.teacher_profile
        availability = getattr(user, "teacher_availability", None)
        status = compute_teacher_status(user, active_teacher_ids=active_ids)
        approval = profile.approval_status or TeacherProfile.ApprovalStatus.PENDING
        rows.append(
            {
                "user": user,
                "display_name": teacher_display_name(user),
                "username": user.username,
                "email": user.email or "—",
                "mobile": user.mobile or "—",
                "status": status,
                "status_label": computed_status_label(status),
                "approval_status": approval,
                "approval_status_label": approval_status_label(approval),
                "session_count": session_counts.get(user.id, 0),
                "last_seen": availability.last_seen if availability else None,
                "is_active": user.is_active,
            }
        )

    if status_filter in {COMPUTED_AVAILABLE, COMPUTED_BUSY, COMPUTED_OFFLINE}:
        rows = [r for r in rows if r["status"] == status_filter]

    if account_filter == FILTER_ACTIVE:
        rows = [r for r in rows if r["is_active"]]
    elif account_filter == FILTER_INACTIVE:
        rows = [r for r in rows if not r["is_active"]]

    return rows


def _student_subscription_label(user) -> tuple[str, str]:
    balance = getattr(user, "subscription_balance", None)
    if balance is None:
        return FILTER_SUB_NONE, "بدون اشتراك"
    display = balance_display_status(balance)
    return display, display_status_label(display)


def _build_student_rows(q: str, account_filter: str, subscription_filter: str):
    qs = User.objects.filter(user_type=USER_TYPE_STUDENT).select_related(
        "student_profile",
        "subscription_balance",
    )

    if q:
        qs = qs.filter(
            Q(username__icontains=q)
            | Q(email__icontains=q)
            | Q(full_name__icontains=q)
            | Q(mobile__icontains=q)
            | Q(student_profile__display_name__icontains=q)
        )

    students = list(qs.order_by("username"))
    session_counts = _session_counts_for_students([s.id for s in students])

    rows = []
    for user in students:
        profile = getattr(user, "student_profile", None)
        display_name = (
            (profile.display_name if profile and profile.display_name else None)
            or user.full_name
            or user.get_full_name()
            or user.username
        )
        sub_key, sub_label = _student_subscription_label(user)
        rows.append(
            {
                "user": user,
                "display_name": display_name,
                "username": user.username,
                "email": user.email or "—",
                "mobile": user.mobile or "—",
                "subscription_key": sub_key,
                "subscription_label": sub_label,
                "session_count": session_counts.get(user.id, 0),
                "is_active": user.is_active,
            }
        )

    if account_filter == FILTER_ACTIVE:
        rows = [r for r in rows if r["is_active"]]
    elif account_filter == FILTER_INACTIVE:
        rows = [r for r in rows if not r["is_active"]]

    if subscription_filter == FILTER_SUB_ACTIVE:
        rows = [r for r in rows if r["subscription_key"] == FILTER_SUB_ACTIVE]
    elif subscription_filter == FILTER_SUB_EXPIRED:
        rows = [r for r in rows if r["subscription_key"] == FILTER_SUB_EXPIRED]
    elif subscription_filter == FILTER_SUB_NONE:
        rows = [r for r in rows if r["subscription_key"] == FILTER_SUB_NONE]

    return rows


def _list_hidden_fields(q, tab, status_filter, account_filter, subscription_filter):
    hidden = [{"name": "tab", "value": tab}]
    if q:
        hidden.append({"name": "q", "value": q})
    if tab == TAB_TEACHERS and status_filter != FILTER_ALL:
        hidden.append({"name": "status", "value": status_filter})
    if account_filter != FILTER_ALL:
        hidden.append({"name": "account", "value": account_filter})
    if tab == TAB_STUDENTS and subscription_filter != FILTER_ALL:
        hidden.append({"name": "subscription", "value": subscription_filter})
    return hidden


def _detail_hidden_fields(detail_tab, q=""):
    hidden = [{"name": "tab", "value": detail_tab}]
    if q:
        hidden.append({"name": "q", "value": q})
    return hidden


def _build_attached_files(user, *, is_teacher: bool) -> list[dict]:
    files = []
    profile_image = getattr(user, "profile_image", None)
    if profile_image and profile_image.name:
        filename = profile_image.name.rsplit("/", 1)[-1]
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        files.append(
            {
                "label": "الصورة الشخصية",
                "filename": filename,
                "kind": "image" if ext in {"png", "jpg", "jpeg", "gif", "webp"} else "file",
                "uploaded_at": None,
                "url_name": (
                    "dashboard:dashboard_user_teacher_profile_image"
                    if is_teacher
                    else "dashboard:dashboard_user_student_profile_image"
                ),
            }
        )

    if is_teacher:
        profile = getattr(user, "teacher_profile", None)
        ijazah = getattr(profile, "ijazah", None) if profile else None
        if ijazah and ijazah.name:
            filename = ijazah.name.rsplit("/", 1)[-1]
            files.append(
                {
                    "label": "الإجازة",
                    "filename": filename,
                    "kind": _ijazah_file_kind(filename),
                    "uploaded_at": profile.updated_at if profile else None,
                    "url_name": "dashboard:dashboard_user_teacher_ijazah",
                }
            )
    return files


@login_required
@permissions_required("dashboard.access", "users.view")
def dashboard_users_list(request):
    active_tab = (request.GET.get("tab") or TAB_TEACHERS).strip()
    if active_tab not in _LIST_TABS:
        active_tab = TAB_TEACHERS

    q = (request.GET.get("q") or "").strip()
    status_filter = (request.GET.get("status") or FILTER_ALL).strip()
    account_filter = (request.GET.get("account") or FILTER_ALL).strip()
    subscription_filter = (request.GET.get("subscription") or FILTER_ALL).strip()

    if active_tab == TAB_TEACHERS:
        rows = _build_teacher_rows(q, status_filter, account_filter)
    else:
        rows = _build_student_rows(q, account_filter, subscription_filter)

    page_obj, page_numbers, per_page_param, total_rows = paginate_with_smart_pages(
        request=request,
        queryset=rows,
        default_per_page="5",
    )

    pagination_kwargs = {"tab": active_tab, "q": q, "per_page": per_page_param}
    if active_tab == TAB_TEACHERS and status_filter != FILTER_ALL:
        pagination_kwargs["status"] = status_filter
    if account_filter != FILTER_ALL:
        pagination_kwargs["account"] = account_filter
    if active_tab == TAB_STUDENTS and subscription_filter != FILTER_ALL:
        pagination_kwargs["subscription"] = subscription_filter
    pagination_qs = build_pagination_query_string(**pagination_kwargs)

    hidden_fields = _list_hidden_fields(
        q, active_tab, status_filter, account_filter, subscription_filter
    )
    if per_page_param:
        hidden_fields.append({"name": "per_page", "value": per_page_param})

    return render(
        request,
        "dashboard/pages/users/list.html",
        {
            "tab": active_tab,
            "rows": page_obj.object_list,
            "page_obj": page_obj,
            "page_numbers": page_numbers,
            "per_page": per_page_param,
            "total_rows": total_rows,
            "q": q,
            "status_filter": status_filter,
            "account_filter": account_filter,
            "subscription_filter": subscription_filter,
            "pagination_qs": pagination_qs,
            "pagination_hidden_fields": hidden_fields,
        },
    )


def _paginate_detail_queryset(request, queryset, detail_tab, q=""):
    page_obj, page_numbers, per_page_param, total_rows = paginate_with_smart_pages(
        request=request,
        queryset=queryset,
        default_per_page="5",
    )
    pagination_qs = build_pagination_query_string(
        tab=detail_tab,
        q=q,
        per_page=per_page_param,
    )
    hidden_fields = _detail_hidden_fields(detail_tab, q=q)
    if per_page_param:
        hidden_fields.append({"name": "per_page", "value": per_page_param})
    return page_obj, page_numbers, per_page_param, total_rows, pagination_qs, hidden_fields


@login_required
@permissions_required("dashboard.access", "users.teachers.view")
def dashboard_user_teacher_detail(request, user_id):
    user = get_object_or_404(
        User.objects.select_related("teacher_profile", "teacher_availability"),
        pk=user_id,
        user_type=USER_TYPE_TEACHER,
        teacher_profile__isnull=False,
    )

    detail_tab = (request.GET.get("tab") or DETAIL_TAB_PROFILE).strip()
    if detail_tab not in _TEACHER_DETAIL_TABS:
        detail_tab = DETAIL_TAB_PROFILE

    q = (request.GET.get("q") or "").strip()
    profile = user.teacher_profile
    availability = getattr(user, "teacher_availability", None)
    active_ids = _active_teacher_ids()
    status = compute_teacher_status(user, active_teacher_ids=active_ids)

    context = {
        "user_obj": user,
        "tab": detail_tab,
        "gender_label": _gender_label(user),
        "user_type_label": user_type_label(user),
        "riwayat_value": build_profile_payload(user).get("riwayat") or "—",
        "status_label": computed_status_label(status),
        "last_seen": availability.last_seen if availability else None,
        "attached_files": _build_attached_files(user, is_teacher=True),
        "profile": profile,
        "approval": teacher_approval_payload(profile),
        "q": q,
    }

    if detail_tab == DETAIL_TAB_SESSIONS:
        qs = (
            CallSession.objects.filter(teacher=user)
            .select_related("student", "recording")
            .order_by("-created_at", "-id")
        )
        if q:
            qs = qs.filter(
                Q(student__username__icontains=q)
                | Q(student__email__icontains=q)
                | Q(student__full_name__icontains=q)
            )
        page_obj, page_numbers, per_page, total, pagination_qs, hidden = (
            _paginate_detail_queryset(request, qs, detail_tab, q=q)
        )
        session_rows = []
        recordings = []
        for call in page_obj.object_list:
            session_rows.append({"call": call, "duration": _duration_display(call)})
            rec = getattr(call, "recording", None)
            if rec:
                recordings.append(rec)
        _attach_playback_urls(recordings)
        context.update(
            {
                "session_rows": session_rows,
                "page_obj": page_obj,
                "page_numbers": page_numbers,
                "per_page": per_page,
                "total_rows": total,
                "pagination_qs": pagination_qs,
                "pagination_hidden_fields": hidden,
            }
        )

    elif detail_tab == DETAIL_TAB_CALLS:
        qs = (
            CallSession.objects.filter(teacher=user)
            .select_related("student")
            .order_by("-created_at", "-id")
        )
        if q:
            qs = qs.filter(
                Q(student__username__icontains=q)
                | Q(channel_name__icontains=q)
            )
        page_obj, page_numbers, per_page, total, pagination_qs, hidden = (
            _paginate_detail_queryset(request, qs, detail_tab, q=q)
        )
        context.update(
            {
                "call_rows": [
                    {"call": c, "duration": _duration_display(c)}
                    for c in page_obj.object_list
                ],
                "page_obj": page_obj,
                "page_numbers": page_numbers,
                "per_page": per_page,
                "total_rows": total,
                "pagination_qs": pagination_qs,
                "pagination_hidden_fields": hidden,
            }
        )

    elif detail_tab == DETAIL_TAB_EVALUATIONS:
        peer_qs = CallPeerRating.objects.filter(
            Q(rater=user) | Q(rated=user) | Q(call_session__teacher=user)
        ).select_related(
            "call_session",
            "call_session__student",
            "call_session__teacher",
            "rater",
            "rated",
        )
        session_eval_qs = SessionEvaluation.objects.filter(teacher=user).select_related(
            "call_session", "student"
        )
        if q:
            peer_qs = peer_qs.filter(
                Q(call_session__student__username__icontains=q)
                | Q(call_session__student__full_name__icontains=q)
            )
            session_eval_qs = session_eval_qs.filter(
                Q(student__username__icontains=q) | Q(student__full_name__icontains=q)
            )
        context["peer_ratings"] = list(peer_qs.order_by("-created_at", "-id")[:50])
        context["session_evaluations"] = list(
            session_eval_qs.order_by("-created_at", "-id")[:50]
        )

    return render(request, "dashboard/pages/users/teacher_detail.html", context)


@login_required
@permissions_required("dashboard.access", "users.students.view")
def dashboard_user_student_detail(request, user_id):
    user = get_object_or_404(
        User.objects.select_related("student_profile", "subscription_balance"),
        pk=user_id,
        user_type=USER_TYPE_STUDENT,
    )

    detail_tab = (request.GET.get("tab") or DETAIL_TAB_PROFILE).strip()
    if detail_tab not in _STUDENT_DETAIL_TABS:
        detail_tab = DETAIL_TAB_PROFILE

    q = (request.GET.get("q") or "").strip()
    profile = getattr(user, "student_profile", None)
    balance = get_user_subscription_balance(user)
    _, sub_label = _student_subscription_label(user)

    context = {
        "user_obj": user,
        "tab": detail_tab,
        "gender_label": _gender_label(user),
        "user_type_label": user_type_label(user),
        "riwayat_value": build_profile_payload(user).get("riwayat") or "—",
        "attached_files": _build_attached_files(user, is_teacher=False),
        "profile": profile,
        "balance": balance,
        "subscription_label": sub_label,
        "q": q,
    }

    if detail_tab == DETAIL_TAB_SESSIONS:
        qs = (
            CallSession.objects.filter(student=user)
            .select_related("teacher", "recording")
            .order_by("-created_at", "-id")
        )
        if q:
            qs = qs.filter(
                Q(teacher__username__icontains=q)
                | Q(teacher__full_name__icontains=q)
            )
        page_obj, page_numbers, per_page, total, pagination_qs, hidden = (
            _paginate_detail_queryset(request, qs, detail_tab, q=q)
        )
        session_rows = []
        recordings = []
        for call in page_obj.object_list:
            session_rows.append({"call": call, "duration": _duration_display(call)})
            rec = getattr(call, "recording", None)
            if rec:
                recordings.append(rec)
        _attach_playback_urls(recordings)
        context.update(
            {
                "session_rows": session_rows,
                "page_obj": page_obj,
                "page_numbers": page_numbers,
                "per_page": per_page,
                "total_rows": total,
                "pagination_qs": pagination_qs,
                "pagination_hidden_fields": hidden,
            }
        )

    elif detail_tab == DETAIL_TAB_CALLS:
        qs = (
            CallSession.objects.filter(student=user)
            .select_related("teacher")
            .order_by("-created_at", "-id")
        )
        if q:
            qs = qs.filter(
                Q(teacher__username__icontains=q) | Q(channel_name__icontains=q)
            )
        page_obj, page_numbers, per_page, total, pagination_qs, hidden = (
            _paginate_detail_queryset(request, qs, detail_tab, q=q)
        )
        context.update(
            {
                "call_rows": [
                    {"call": c, "duration": _duration_display(c)}
                    for c in page_obj.object_list
                ],
                "page_obj": page_obj,
                "page_numbers": page_numbers,
                "per_page": per_page,
                "total_rows": total,
                "pagination_qs": pagination_qs,
                "pagination_hidden_fields": hidden,
            }
        )

    elif detail_tab == DETAIL_TAB_EVALUATIONS:
        peer_qs = CallPeerRating.objects.filter(
            Q(rater=user) | Q(rated=user) | Q(call_session__student=user)
        ).select_related(
            "call_session",
            "call_session__student",
            "call_session__teacher",
            "rater",
            "rated",
        )
        session_eval_qs = SessionEvaluation.objects.filter(student=user).select_related(
            "call_session", "teacher"
        )
        if q:
            peer_qs = peer_qs.filter(
                Q(call_session__teacher__username__icontains=q)
                | Q(call_session__teacher__full_name__icontains=q)
            )
            session_eval_qs = session_eval_qs.filter(
                Q(teacher__username__icontains=q) | Q(teacher__full_name__icontains=q)
            )
        context["peer_ratings"] = list(peer_qs.order_by("-created_at", "-id")[:50])
        context["session_evaluations"] = list(
            session_eval_qs.order_by("-created_at", "-id")[:50]
        )

    elif detail_tab == DETAIL_TAB_SUBSCRIPTIONS:
        history_qs = StudentSubscription.objects.filter(user=user).select_related(
            "plan"
        ).order_by("-created_at", "-id")
        history_rows = []
        for sub in history_qs:
            computed = display_status(sub)
            history_rows.append(
                {
                    "subscription": sub,
                    "display_status": computed,
                    "display_label": display_status_label(computed),
                }
            )
        context["history_rows"] = history_rows

    return render(request, "dashboard/pages/users/student_detail.html", context)


@login_required
@permissions_required("dashboard.access", "users.teachers.view")
def dashboard_user_teacher_profile_image(request, user_id):
    user_obj = get_object_or_404(User, pk=user_id, user_type=USER_TYPE_TEACHER)
    image = getattr(user_obj, "profile_image", None)
    if not image or not image.name:
        raise Http404
    content_type, _ = mimetypes.guess_type(image.name)
    try:
        return FileResponse(
            image.open("rb"),
            content_type=content_type or "image/jpeg",
        )
    except (ValueError, FileNotFoundError) as exc:
        raise Http404 from exc


@login_required
@permissions_required("dashboard.access", "users.teachers.view")
def dashboard_user_teacher_ijazah(request, user_id):
    user_obj = get_object_or_404(
        User.objects.select_related("teacher_profile"),
        pk=user_id,
        user_type=USER_TYPE_TEACHER,
    )
    profile = getattr(user_obj, "teacher_profile", None)
    ijazah = getattr(profile, "ijazah", None) if profile else None
    if not ijazah or not ijazah.name:
        raise Http404
    content_type, _ = mimetypes.guess_type(ijazah.name)
    filename = ijazah.name.rsplit("/", 1)[-1]
    try:
        response = FileResponse(
            ijazah.open("rb"),
            content_type=content_type or "application/octet-stream",
        )
        disposition = (
            "inline" if _ijazah_file_kind(filename) in {"image", "pdf"} else "attachment"
        )
        response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
        return response
    except (ValueError, FileNotFoundError) as exc:
        raise Http404 from exc


@login_required
@permissions_required("dashboard.access", "users.students.view")
def dashboard_user_student_profile_image(request, user_id):
    user_obj = get_object_or_404(User, pk=user_id, user_type=USER_TYPE_STUDENT)
    image = getattr(user_obj, "profile_image", None)
    if not image or not image.name:
        raise Http404
    content_type, _ = mimetypes.guess_type(image.name)
    try:
        return FileResponse(
            image.open("rb"),
            content_type=content_type or "image/jpeg",
        )
    except (ValueError, FileNotFoundError) as exc:
        raise Http404 from exc
