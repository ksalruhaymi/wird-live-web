from django.http import HttpRequest

from apps.communication.models import Announcement
from core.utils.media import media_url


def _announcement_has_display_content(announcement: Announcement) -> bool:
    if announcement.display_format == Announcement.DisplayFormat.TEXT:
        return bool((announcement.message or "").strip())
    if announcement.display_format == Announcement.DisplayFormat.IMAGE:
        return bool(announcement.image and announcement.image.name)
    return False


def get_current_announcement() -> Announcement | None:
    """Legacy single-announcement helper; returns newest active displayable ad."""
    return get_active_announcements(limit=1).first()


def get_active_announcements(*, limit: int = 3) -> list[Announcement]:
    qs = (
        Announcement.objects.filter(is_active=True)
        .order_by("-created_at", "-id")
    )
    results: list[Announcement] = []
    for item in qs.iterator():
        if not _announcement_has_display_content(item):
            continue
        results.append(item)
        if len(results) >= limit:
            break
    return results


def _resolve_image_url(announcement: Announcement, request: HttpRequest | None) -> str:
    if not announcement.image:
        return ""
    name = announcement.image.name
    if not name:
        return ""
    relative = announcement.image.url
    if relative.startswith(("http://", "https://")):
        return relative
    if request is not None:
        return request.build_absolute_uri(relative)
    return media_url(name)


def announcement_to_payload(
    announcement: Announcement,
    *,
    request: HttpRequest | None = None,
) -> dict:
    return {
        "id": announcement.id,
        "display_format": announcement.display_format,
        "image_url": _resolve_image_url(announcement, request),
        "message": announcement.message or "",
        "link_url": announcement.link_url or "",
        "is_active": announcement.is_active,
        "created_at": announcement.created_at.isoformat(),
    }


def announcement_to_legacy_payload(announcement: Announcement) -> dict:
    """Backward-compatible payload for the old current endpoint."""
    return {
        "id": announcement.id,
        "title": announcement.title,
        "message": announcement.message,
        "announcement_type": announcement.announcement_type,
        "announced_by": announcement.announced_by,
        "target_type": announcement.target_type,
        "target_group": announcement.target_group,
        "announcement_date": (
            announcement.announcement_date.isoformat()
            if announcement.announcement_date
            else ""
        ),
        "display_format": announcement.display_format,
        "image_url": _resolve_image_url(announcement, None),
        "link_url": announcement.link_url or "",
    }
