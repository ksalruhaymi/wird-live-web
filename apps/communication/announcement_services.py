from django.http import HttpRequest

from apps.communication.models import Announcement
from core.utils.media import media_url


def get_current_announcement() -> Announcement | None:
    """Legacy single-announcement helper; returns newest active image ad."""
    return get_active_announcements(limit=1).first()


def get_active_announcements(*, limit: int = 3) -> list[Announcement]:
    qs = (
        Announcement.objects.filter(is_active=True)
        .exclude(image__isnull=True)
        .exclude(image="")
        .order_by("-created_at", "-id")
    )
    return list(qs[:limit])


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
        "image_url": _resolve_image_url(announcement, request),
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
        "image_url": _resolve_image_url(announcement, None),
    }
