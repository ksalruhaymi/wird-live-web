import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, F, Sum
from django.db.models.functions import TruncDate
from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_POST

from identity.rbac.decorators import permission_required

from .models import AnalyticsIPAddress, AnalyticsVisitor, InteractionEvent, PageView


def build_last_7_days_series(queryset, date_key="day", total_key="total"):
    today = timezone.localdate()
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]

    data_map = {
        item[date_key]: item[total_key]
        for item in queryset
        if item.get(date_key) is not None
    }

    labels = [day.strftime("%Y-%m-%d") for day in days]
    values = [data_map.get(day, 0) for day in days]

    return labels, values


def format_duration(seconds):
    total = int(seconds or 0)
    hrs, rem = divmod(total, 3600)
    mins, secs = divmod(rem, 60)
    if hrs:
        return f"{hrs:02d}:{mins:02d}:{secs:02d}"
    return f"{mins:02d}:{secs:02d}"


def build_page_numbers(page_obj, window=2):
    if not page_obj:
        return []
    return range(
        max(page_obj.number - window, 1),
        min(page_obj.number + window + 1, page_obj.paginator.num_pages + 1),
    )


def build_analytics_context(tab):
    now = timezone.now()
    today = timezone.localdate()
    last_7_days = now - timedelta(days=7)
    last_30_days = now - timedelta(days=30)

    total_visitors = AnalyticsVisitor.objects.count()

    unique_ip_visitors = AnalyticsIPAddress.objects.count()

    unique_ip_visitors_7_days = AnalyticsIPAddress.objects.filter(
        last_seen_at__gte=last_7_days
    ).count()
    visitors_today = AnalyticsVisitor.objects.filter(last_seen_at__date=today).count()
    unique_ip_visitors_today = AnalyticsIPAddress.objects.filter(last_seen_at__date=today).count()

    total_page_views = PageView.objects.count()
    total_audio_plays = InteractionEvent.objects.filter(
        event_type=InteractionEvent.EVENT_AUDIO_PLAY
    ).count()
    total_page_flips = InteractionEvent.objects.filter(
        event_type=InteractionEvent.EVENT_PAGE_FLIP
    ).count()
    total_audio_completions = InteractionEvent.objects.filter(
        event_type=InteractionEvent.EVENT_AUDIO_COMPLETE
    ).count()
    total_audio_progress_50 = InteractionEvent.objects.filter(
        event_type=InteractionEvent.EVENT_AUDIO_PROGRESS_50
    ).count()
    total_audio_pauses = InteractionEvent.objects.filter(
        event_type=InteractionEvent.EVENT_AUDIO_PAUSE
    ).count()
    audio_plays_today = InteractionEvent.objects.filter(
        event_type=InteractionEvent.EVENT_AUDIO_PLAY,
        created_at__date=today,
    ).count()
    audio_progress_50_today = InteractionEvent.objects.filter(
        event_type=InteractionEvent.EVENT_AUDIO_PROGRESS_50,
        created_at__date=today,
    ).count()
    audio_completions_today = InteractionEvent.objects.filter(
        event_type=InteractionEvent.EVENT_AUDIO_COMPLETE,
        created_at__date=today,
    ).count()
    audio_unique_visitors_today = (
        InteractionEvent.objects.filter(
            event_type=InteractionEvent.EVENT_AUDIO_PLAY,
            created_at__date=today,
            visitor__isnull=False,
        )
        .values("visitor_id")
        .distinct()
        .count()
    )
    audio_plays_7_days = InteractionEvent.objects.filter(
        event_type=InteractionEvent.EVENT_AUDIO_PLAY,
        created_at__gte=last_7_days,
    ).count()
    audio_progress_50_7_days = InteractionEvent.objects.filter(
        event_type=InteractionEvent.EVENT_AUDIO_PROGRESS_50,
        created_at__gte=last_7_days,
    ).count()
    audio_completions_7_days = InteractionEvent.objects.filter(
        event_type=InteractionEvent.EVENT_AUDIO_COMPLETE,
        created_at__gte=last_7_days,
    ).count()
    audio_completion_rate = round((total_audio_completions / total_audio_plays) * 100, 1) if total_audio_plays else 0
    audio_progress_50_rate = round((total_audio_progress_50 / total_audio_plays) * 100, 1) if total_audio_plays else 0
    total_tafsir_opens = InteractionEvent.objects.filter(
        event_type=InteractionEvent.EVENT_TAFSIR_OPEN
    ).count()

    unique_visitors_7_days = AnalyticsVisitor.objects.filter(
        last_seen_at__gte=last_7_days
    ).count()
    page_views_7_days = PageView.objects.filter(
        created_at__gte=last_7_days
    ).count()
    page_views_30_days = PageView.objects.filter(
        created_at__gte=last_30_days
    ).count()

    top_pages = (
        PageView.objects.values("path")
        .annotate(total=Count("id"))
        .order_by("-total", "path")[:15]
    )

    top_audio_pages = (
        InteractionEvent.objects.filter(
            event_type=InteractionEvent.EVENT_AUDIO_PLAY
        )
        .values("path")
        .annotate(total=Count("id"))
        .order_by("-total", "path")[:10]
    )

    top_qurra = (
        InteractionEvent.objects.filter(
            event_type=InteractionEvent.EVENT_AUDIO_PLAY
        )
        .exclude(qari="")
        .values("qari")
        .annotate(total=Count("id"))
        .order_by("-total", "qari")[:10]
    )

    top_audio_mushafs = (
        InteractionEvent.objects.filter(
            event_type=InteractionEvent.EVENT_AUDIO_PLAY
        )
        .exclude(payload__mushaf="")
        .values("payload__mushaf")
        .annotate(total=Count("id"))
        .order_by("-total", "payload__mushaf")[:10]
    )

    top_audio_sources = (
        InteractionEvent.objects.filter(
            event_type=InteractionEvent.EVENT_AUDIO_PLAY
        )
        .exclude(payload__source="")
        .values("payload__source")
        .annotate(total=Count("id"))
        .order_by("-total", "payload__source")[:10]
    )

    top_flipped_pages = (
        InteractionEvent.objects.filter(
            event_type=InteractionEvent.EVENT_PAGE_FLIP,
            page_number__isnull=False,
        )
        .values("page_number")
        .annotate(total=Count("id"))
        .order_by("-total", "page_number")[:10]
    )

    top_surahs = (
        InteractionEvent.objects.filter(
            event_type=InteractionEvent.EVENT_AUDIO_PLAY,
            surah_number__isnull=False,
        )
        .values("surah_number")
        .annotate(total=Count("id"))
        .order_by("-total", "surah_number")[:10]
    )

    top_tafsir_pages = (
        InteractionEvent.objects.filter(
            event_type=InteractionEvent.EVENT_TAFSIR_OPEN,
            page_number__isnull=False,
        )
        .values("page_number")
        .annotate(total=Count("id"))
        .order_by("-total", "page_number")[:10]
    )

    top_tafsir_surahs = (
        InteractionEvent.objects.filter(
            event_type=InteractionEvent.EVENT_TAFSIR_OPEN,
            surah_number__isnull=False,
        )
        .values("surah_number")
        .annotate(total=Count("id"))
        .order_by("-total", "surah_number")[:10]
    )

    top_tafsir_ayahs = (
        InteractionEvent.objects.filter(
            event_type=InteractionEvent.EVENT_TAFSIR_OPEN,
            surah_number__isnull=False,
            ayah_number__isnull=False,
        )
        .values("surah_number", "ayah_number")
        .annotate(total=Count("id"))
        .order_by("-total", "surah_number", "ayah_number")[:10]
    )

    top_tafsir_books = (
        InteractionEvent.objects.filter(
            event_type=InteractionEvent.EVENT_TAFSIR_OPEN
        )
        .exclude(payload__tafsir="")
        .values("payload__tafsir")
        .annotate(total=Count("id"))
        .order_by("-total", "payload__tafsir")[:10]
    )

    recent_events = (
        InteractionEvent.objects.select_related("visitor")
        .order_by("-created_at")[:25]
    )

    recent_audio_events = (
        InteractionEvent.objects.select_related("visitor")
        .filter(
            event_type__in=[
                InteractionEvent.EVENT_AUDIO_PLAY,
                InteractionEvent.EVENT_AUDIO_PAUSE,
                InteractionEvent.EVENT_AUDIO_PROGRESS_50,
                InteractionEvent.EVENT_AUDIO_COMPLETE,
            ]
        )
        .order_by("-created_at")[:25]
    )

    daily_page_views_qs = (
        PageView.objects.filter(created_at__gte=last_7_days)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total=Count("id"))
        .order_by("day")
    )

    daily_audio_plays_qs = (
        InteractionEvent.objects.filter(
            created_at__gte=last_7_days,
            event_type=InteractionEvent.EVENT_AUDIO_PLAY,
        )
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total=Count("id"))
        .order_by("day")
    )

    daily_audio_progress_50_qs = (
        InteractionEvent.objects.filter(
            created_at__gte=last_7_days,
            event_type=InteractionEvent.EVENT_AUDIO_PROGRESS_50,
        )
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total=Count("id"))
        .order_by("day")
    )

    daily_audio_completions_qs = (
        InteractionEvent.objects.filter(
            created_at__gte=last_7_days,
            event_type=InteractionEvent.EVENT_AUDIO_COMPLETE,
        )
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total=Count("id"))
        .order_by("day")
    )

    daily_tafsir_opens_qs = (
        InteractionEvent.objects.filter(
            created_at__gte=last_7_days,
            event_type=InteractionEvent.EVENT_TAFSIR_OPEN,
        )
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(total=Count("id"))
        .order_by("day")
    )

    chart_labels, chart_page_views = build_last_7_days_series(daily_page_views_qs)
    _, chart_audio_plays = build_last_7_days_series(daily_audio_plays_qs)
    _, chart_audio_progress_50 = build_last_7_days_series(daily_audio_progress_50_qs)
    _, chart_audio_completions = build_last_7_days_series(daily_audio_completions_qs)
    _, chart_tafsir_opens = build_last_7_days_series(daily_tafsir_opens_qs)

    User = get_user_model()
    top_visitors = (
        AnalyticsVisitor.objects.select_related("user")
        .annotate(total_pages=Count("page_views"))
        .order_by("-last_seen_at")[:50]
    )
    os_breakdown = (
        AnalyticsVisitor.objects.exclude(os_name__in=["", "Other", "Unknown"]).values("os_name")
        .annotate(total=Count("id"))
        .order_by("-total", "os_name")[:10]
    )
    browser_breakdown = (
        AnalyticsVisitor.objects.exclude(browser_name__in=["", "Other", "Unknown"]).values("browser_name")
        .annotate(total=Count("id"))
        .order_by("-total", "browser_name")[:10]
    )
    country_breakdown = (
        AnalyticsIPAddress.objects.exclude(country_name="")
        .values("country_name")
        .annotate(total=Count("id"))
        .order_by("-total", "country_name")[:10]
    )
    language_breakdown = (
        AnalyticsVisitor.objects.exclude(last_language="")
        .values("last_language")
        .annotate(total=Count("id"))
        .order_by("-total", "last_language")[:10]
    )
    recitation_corrections_today = (
        InteractionEvent.objects.filter(
            event_type=InteractionEvent.EVENT_RECITATION_CORRECTION,
            created_at__date=today,
            visitor__isnull=False,
        )
        .values("visitor_id")
        .distinct()
        .count()
    )
    daily_wird_users_today = (
        InteractionEvent.objects.filter(
            event_type=InteractionEvent.EVENT_DAILY_WIRD_OPEN,
            created_at__date=today,
            visitor__isnull=False,
        )
        .values("visitor_id")
        .distinct()
        .count()
    )
    language_changes_today = InteractionEvent.objects.filter(
        event_type=InteractionEvent.EVENT_LANGUAGE_CHANGE,
        created_at__date=today,
    ).count()
    visitor_ips = [item.ip_address for item in top_visitors if item.ip_address]
    country_map = dict(
        AnalyticsIPAddress.objects.filter(ip_address__in=visitor_ips).values_list(
            "ip_address", "country_name"
        )
    )
    visitor_rows = [
        {
            "name": item.user.username if item.user_id else "زائر",
            "ip_address": item.ip_address or "-",
            "os_name": item.os_name or "Unknown",
            "os_version": item.os_version or "-",
            "browser_name": item.browser_name or "Unknown",
            "browser_version": item.browser_version or "-",
            "device_type": item.device_type or "-",
            "language": item.last_language or "-",
            "country": (country_map.get(item.ip_address) or "-") if item.ip_address else "-",
            "pages_count": item.total_pages,
            "stay_seconds": item.total_active_seconds,
            "stay_label": format_duration(item.total_active_seconds),
            "last_seen_at": item.last_seen_at,
            "is_authenticated": item.is_authenticated,
        }
        for item in top_visitors
    ]

    return {
        "tab": tab,
        "users_count": User.objects.count(),
        "total_visitors": total_visitors,
        "unique_ip_visitors": unique_ip_visitors,
        "unique_ip_visitors_7_days": unique_ip_visitors_7_days,
        "visitors_today": visitors_today,
        "unique_ip_visitors_today": unique_ip_visitors_today,
        "total_page_views": total_page_views,
        "total_audio_plays": total_audio_plays,
        "total_page_flips": total_page_flips,
        "total_audio_completions": total_audio_completions,
        "total_audio_progress_50": total_audio_progress_50,
        "total_audio_pauses": total_audio_pauses,
        "audio_plays_today": audio_plays_today,
        "audio_progress_50_today": audio_progress_50_today,
        "audio_completions_today": audio_completions_today,
        "audio_unique_visitors_today": audio_unique_visitors_today,
        "audio_plays_7_days": audio_plays_7_days,
        "audio_progress_50_7_days": audio_progress_50_7_days,
        "audio_completions_7_days": audio_completions_7_days,
        "audio_completion_rate": audio_completion_rate,
        "audio_progress_50_rate": audio_progress_50_rate,
        "total_tafsir_opens": total_tafsir_opens,
        "unique_visitors_7_days": unique_visitors_7_days,
        "page_views_7_days": page_views_7_days,
        "page_views_30_days": page_views_30_days,
        "top_pages": top_pages,
        "top_audio_pages": top_audio_pages,
        "top_qurra": top_qurra,
        "top_audio_mushafs": top_audio_mushafs,
        "top_audio_sources": top_audio_sources,
        "top_flipped_pages": top_flipped_pages,
        "top_surahs": top_surahs,
        "top_tafsir_pages": top_tafsir_pages,
        "top_tafsir_surahs": top_tafsir_surahs,
        "top_tafsir_ayahs": top_tafsir_ayahs,
        "top_tafsir_books": top_tafsir_books,
        "recent_events": recent_events,
        "recent_audio_events": recent_audio_events,
        "daily_page_views": list(daily_page_views_qs),
        "daily_audio_plays": list(daily_audio_plays_qs),
        "daily_audio_progress_50": list(daily_audio_progress_50_qs),
        "daily_audio_completions": list(daily_audio_completions_qs),
        "daily_tafsir_opens": list(daily_tafsir_opens_qs),
        "chart_labels": chart_labels,
        "chart_page_views": chart_page_views,
        "chart_audio_plays": chart_audio_plays,
        "chart_audio_progress_50": chart_audio_progress_50,
        "chart_audio_completions": chart_audio_completions,
        "chart_tafsir_opens": chart_tafsir_opens,
        "total_listen_seconds": InteractionEvent.objects.filter(
            event_type=InteractionEvent.EVENT_AUDIO_COMPLETE
        ).aggregate(total=Sum("duration_seconds")).get("total") or 0,
        "visitor_rows": visitor_rows,
        "os_breakdown": os_breakdown,
        "browser_breakdown": browser_breakdown,
        "country_breakdown": country_breakdown,
        "language_breakdown": language_breakdown,
        "recitation_corrections_today": recitation_corrections_today,
        "daily_wird_users_today": daily_wird_users_today,
        "language_changes_today": language_changes_today,
    }


@require_POST
def track_event(request):
    if not request.session.session_key:
        request.session.save()

    try:
        data = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"status": "error", "message": "Invalid payload"}, status=400)

    visitor = None
    session_key = request.session.session_key
    if session_key:
        visitor = AnalyticsVisitor.objects.filter(session_key=session_key).first()

    event_type = (data.get("type") or "").strip()
    allowed_types = {choice[0] for choice in InteractionEvent.EVENT_CHOICES}
    if event_type not in allowed_types:
        return JsonResponse({"status": "error", "message": "Invalid event type"}, status=400)

    payload = data.get("data") or {}
    if not isinstance(payload, dict):
        payload = {"value": payload}

    InteractionEvent.objects.create(
        visitor=visitor,
        event_type=event_type,
        path=(data.get("path") or request.path)[:255],
        page_number=payload.get("page") or payload.get("page_number"),
        surah_number=payload.get("surah") or payload.get("surah_number"),
        ayah_number=payload.get("ayah") or payload.get("ayah_number"),
        qari=(payload.get("qari") or payload.get("reader") or "")[:100],
        duration_seconds=payload.get("duration") or payload.get("duration_seconds"),
        payload=payload,
    )

    if event_type == InteractionEvent.EVENT_SESSION_ACTIVE and visitor:
        seconds = payload.get("active_seconds") or payload.get("seconds") or 0
        try:
            seconds = int(seconds)
        except (TypeError, ValueError):
            seconds = 0
        # Guard against accidental huge values from clients.
        seconds = max(0, min(seconds, 300))
        if seconds:
            AnalyticsVisitor.objects.filter(pk=visitor.pk).update(
                total_active_seconds=F("total_active_seconds") + seconds
            )
    return JsonResponse({"status": "ok"})


@permission_required("analytics.access")
@login_required
def overview_dashboard(request):
    context = build_analytics_context("overview")
    return render(request, "analytics/overview/dashboard_overview.html", context)


@permission_required("analytics.access")
@login_required
def pages_dashboard(request):
    context = build_analytics_context("pages")
    pages_qs = (
        PageView.objects.values("path")
        .annotate(total=Count("id"))
        .order_by("-total", "path")
    )
    paginator = Paginator(pages_qs, 20)
    page_obj = paginator.get_page(request.GET.get("page"))
    context.update(
        {
            "top_pages": page_obj,
            "top_pages_page_obj": page_obj,
            "top_pages_page_numbers": build_page_numbers(page_obj),
            "top_pages_total_count": paginator.count,
        }
    )
    return render(request, "analytics/pages/dashboard_pages.html", context)


@permission_required("analytics.access")
@login_required
def audio_dashboard(request):
    context = build_analytics_context("audio")
    return render(request, "analytics/audio/dashboard_audio.html", context)


@permission_required("analytics.access")
@login_required
def mushaf_dashboard(request):
    context = build_analytics_context("mushaf")
    return render(request, "analytics/mushaf/dashboard_mushaf.html", context)


@permission_required("analytics.access")
@login_required
def tafsir_dashboard(request):
    context = build_analytics_context("tafsir")
    return render(request, "analytics/tafsir/dashboard_tafsir.html", context)


@permission_required("analytics.access")
@login_required
def events_dashboard(request):
    context = build_analytics_context("events")
    events_qs = InteractionEvent.objects.select_related("visitor").order_by("-created_at")
    paginator = Paginator(events_qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))
    context.update(
        {
            "recent_events": page_obj,
            "events_page_obj": page_obj,
            "events_page_numbers": build_page_numbers(page_obj),
            "events_total_count": paginator.count,
        }
    )
    return render(request, "analytics/events/dashboard_events.html", context)


@permission_required("analytics.access")
@login_required
def visitors_dashboard(request):
    context = build_analytics_context("visitors")
    visitors_qs = (
        AnalyticsVisitor.objects.select_related("user")
        .annotate(total_pages=Count("page_views"))
        .order_by("-last_seen_at")
    )
    paginator = Paginator(visitors_qs, 20)
    page_obj = paginator.get_page(request.GET.get("page"))
    visitor_rows = [
        {
            "name": item.user.username if item.user_id else "زائر",
            "ip_address": item.ip_address or "-",
            "os_name": item.os_name or "Unknown",
            "os_version": item.os_version or "-",
            "browser_name": item.browser_name or "Unknown",
            "browser_version": item.browser_version or "-",
            "device_type": item.device_type or "-",
            "language": item.last_language or "-",
            "country": "-",
            "pages_count": item.total_pages,
            "stay_seconds": item.total_active_seconds,
            "stay_label": format_duration(item.total_active_seconds),
            "last_seen_at": item.last_seen_at,
            "is_authenticated": item.is_authenticated,
        }
        for item in page_obj
    ]
    page_ips = [item.ip_address for item in page_obj if item.ip_address]
    page_country_map = dict(
        AnalyticsIPAddress.objects.filter(ip_address__in=page_ips).values_list(
            "ip_address", "country_name"
        )
    )
    for item in visitor_rows:
        ip = item["ip_address"]
        item["country"] = page_country_map.get(ip, "-") if ip != "-" else "-"
    context.update(
        {
            "visitor_rows": visitor_rows,
            "visitors_page_obj": page_obj,
            "visitors_page_numbers": build_page_numbers(page_obj),
            "visitors_total_count": paginator.count,
        }
    )
    return render(request, "analytics/visitors/dashboard_visitors.html", context)