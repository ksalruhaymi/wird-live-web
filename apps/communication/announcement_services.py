from apps.communication.models import Announcement


def get_current_announcement() -> Announcement | None:
    return (
        Announcement.objects.filter(is_active=True)
        .order_by("-created_at", "-announcement_date", "-id")
        .first()
    )


def announcement_to_payload(announcement: Announcement) -> dict:
    return {
        "id": announcement.id,
        "title": announcement.title,
        "message": announcement.message,
        "announcement_type": announcement.announcement_type,
        "announced_by": announcement.announced_by,
        "target_type": announcement.target_type,
        "target_group": announcement.target_group,
        "announcement_date": announcement.announcement_date.isoformat(),
    }


def deactivate_other_announcements(exclude_pk: int | None = None) -> None:
    qs = Announcement.objects.filter(is_active=True)
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    qs.update(is_active=False)
