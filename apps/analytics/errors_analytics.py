import hashlib
import re

from django.db.models import Count
from django.utils.translation import gettext as _

from .models import InteractionEvent

ERROR_EVENT_TYPES = (
    InteractionEvent.EVENT_CLIENT_ERROR,
    InteractionEvent.EVENT_AUDIO_ERROR,
    InteractionEvent.EVENT_API_ERROR,
    InteractionEvent.EVENT_PAGE_LOAD_ERROR,
)

ERROR_TYPE_LABELS = {
    InteractionEvent.EVENT_CLIENT_ERROR: "analytics_event_client_error",
    InteractionEvent.EVENT_AUDIO_ERROR: "analytics_event_audio_error",
    InteractionEvent.EVENT_API_ERROR: "analytics_event_api_error",
    InteractionEvent.EVENT_PAGE_LOAD_ERROR: "analytics_event_page_load_error",
}

SECTION_LABELS = {
    "calls": "analytics_error_section_calls",
    "recordings": "analytics_error_section_recordings",
    "live": "analytics_error_section_live",
    "site": "analytics_error_section_site",
}


def filter_error_queryset(since):
    qs = InteractionEvent.objects.filter(event_type__in=ERROR_EVENT_TYPES)
    if since is not None:
        qs = qs.filter(created_at__gte=since)
    return qs


def sanitize_error_payload(payload):
    if not isinstance(payload, dict):
        payload = {"message": str(payload)[:300]}
    clean = {}
    message = str(payload.get("message") or "unknown")[:300]
    clean["message"] = message
    clean["error_category"] = str(payload.get("error_category") or "")[:32]
    clean["section"] = str(payload.get("section") or "")[:32]
    clean["kind"] = str(payload.get("kind") or "")[:64]
    if payload.get("status_code") is not None:
        try:
            clean["status_code"] = int(payload.get("status_code"))
        except (TypeError, ValueError):
            pass
    if payload.get("line") is not None:
        try:
            clean["line"] = int(payload.get("line"))
        except (TypeError, ValueError):
            pass
    for key in ("source", "src", "url", "endpoint"):
        if payload.get(key):
            clean[key] = str(payload.get(key))[:500]
    if payload.get("network"):
        clean["network"] = True
    stack = str(payload.get("stack") or "")[:800]
    if stack:
        clean["stack"] = stack
        clean["fingerprint"] = hashlib.sha1(stack.encode("utf-8")).hexdigest()[:16]
    else:
        clean["fingerprint"] = hashlib.sha1(message.encode("utf-8")).hexdigest()[:16]
    return clean


def error_label(event_type):
    msgid = ERROR_TYPE_LABELS.get(event_type)
    return _(msgid) if msgid else event_type


def section_label(section):
    msgid = SECTION_LABELS.get(section)
    return _(msgid) if msgid else section or _("analytics_unknown_label")


def build_error_rows(error_qs):
    rows = list(
        error_qs.values("event_type", "payload__message", "payload__fingerprint")
        .annotate(total=Count("id"))
        .order_by("-total", "payload__message")[:20]
    )
    for row in rows:
        row["label"] = row.get("payload__message") or _("analytics_unknown_label")
        row["type_label"] = error_label(row.get("event_type"))
    return rows


def build_error_section_breakdown(error_qs):
    rows = list(
        error_qs.exclude(payload__section="")
        .values("payload__section")
        .annotate(total=Count("id"))
        .order_by("-total", "payload__section")[:8]
    )
    for row in rows:
        row["section"] = row.pop("payload__section", "") or ""
        row["label"] = section_label(row["section"])
    return rows


def build_error_path_breakdown(error_qs):
    return list(
        error_qs.values("path")
        .annotate(total=Count("id"))
        .order_by("-total", "path")[:12]
    )


def build_error_type_breakdown(error_qs):
    rows = list(
        error_qs.values("event_type")
        .annotate(total=Count("id"))
        .order_by("-total", "event_type")
    )
    for row in rows:
        row["label"] = error_label(row.get("event_type"))
    return rows


def build_affected_visitors(error_qs):
    return (
        error_qs.exclude(visitor__isnull=True)
        .values("visitor_id")
        .distinct()
        .count()
    )


def humanize_error_message(message):
    text = str(message or "").strip()
    if not text:
        return _("analytics_unknown_label")
    text = re.sub(r"\s+", " ", text)
    return text[:120]


def count_errors_between(since, until=None):
    qs = InteractionEvent.objects.filter(event_type__in=ERROR_EVENT_TYPES)
    if since is not None:
        qs = qs.filter(created_at__gte=since)
    if until is not None:
        qs = qs.filter(created_at__lt=until)
    return qs.count()


def build_error_insights(range_ctx, error_qs):
    from .insights import comparison_window, pct_change

    window = comparison_window(range_ctx)
    current = count_errors_between(window["current_since"], window["current_until"])
    previous = count_errors_between(window["previous_since"], window["previous_until"])
    delta = pct_change(current, previous)

    insights = []
    if current > 0 and abs(delta) >= 5:
        direction = "down" if delta > 0 else "up" if delta < 0 else "neutral"
        insights.append(
            {
                "direction": direction,
                "title": _("analytics_errors_total"),
                "text": _("analytics_insight_errors_trend"),
                "icon": "bi-bug",
                "delta": abs(delta),
            }
        )

    top_row = (
        error_qs.values("payload__message")
        .annotate(total=Count("id"))
        .order_by("-total")
        .first()
    )
    if top_row and top_row.get("payload__message"):
        insights.append(
            {
                "direction": "neutral",
                "title": _("analytics_errors_top_message"),
                "text": humanize_error_message(top_row["payload__message"]),
                "icon": "bi-exclamation-triangle",
                "delta": top_row["total"],
            }
        )

    top_path = error_qs.values("path").annotate(total=Count("id")).order_by("-total").first()
    if top_path:
        insights.append(
            {
                "direction": "neutral",
                "title": _("analytics_errors_top_page"),
                "text": top_path["path"],
                "icon": "bi-file-earmark-x",
                "delta": top_path["total"],
            }
        )

    return insights[:4]
