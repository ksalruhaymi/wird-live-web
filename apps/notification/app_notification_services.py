from django.db.models import Exists, OuterRef
from django.utils import timezone

from apps.notification.models import (
    AppNotification,
    AppNotificationRead,
    Notification,
    NotificationChannel,
)


def active_app_notifications_qs():
    return AppNotification.objects.filter(is_active=True).order_by(
        "-created_at", "-id"
    )


def _read_exists_subquery(user):
    return AppNotificationRead.objects.filter(
        notification_id=OuterRef("pk"),
        user=user,
    )


def _personal_notifications_qs(user):
    return Notification.objects.filter(
        user=user,
        channel=NotificationChannel.IN_APP,
    ).order_by("-created_at", "-id")


def _personal_notification_payload(notification: Notification) -> dict:
    return {
        "id": -notification.id,
        "title": notification.title,
        "body": notification.message,
        "is_active": True,
        "target_type": "personal",
        "created_at": notification.created_at.isoformat(),
        "updated_at": notification.created_at.isoformat(),
        "is_read": notification.is_read,
    }


def app_notification_to_payload(notification: AppNotification, *, user) -> dict:
    is_read = AppNotificationRead.objects.filter(
        user=user,
        notification=notification,
    ).exists()
    return {
        "id": notification.id,
        "title": notification.title,
        "body": notification.body,
        "is_active": notification.is_active,
        "target_type": notification.target_type,
        "created_at": notification.created_at.isoformat(),
        "updated_at": notification.updated_at.isoformat(),
        "is_read": is_read,
    }


def list_app_notifications_for_user(user) -> list[dict]:
    broadcast = [
        {
            "id": row.id,
            "title": row.title,
            "body": row.body,
            "is_active": row.is_active,
            "target_type": row.target_type,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
            "is_read": row.is_read,
        }
        for row in active_app_notifications_qs().annotate(
            is_read=Exists(_read_exists_subquery(user))
        )
    ]
    personal = [
        _personal_notification_payload(row)
        for row in _personal_notifications_qs(user)
    ]
    combined = broadcast + personal
    combined.sort(key=lambda item: item["created_at"], reverse=True)
    return combined


def unread_app_notifications_count(user) -> int:
    read_ids = AppNotificationRead.objects.filter(user=user).values_list(
        "notification_id",
        flat=True,
    )
    broadcast_unread = active_app_notifications_qs().exclude(id__in=read_ids).count()
    personal_unread = _personal_notifications_qs(user).filter(is_read=False).count()
    return broadcast_unread + personal_unread


def mark_app_notification_read(user, notification_id: int) -> bool:
    if notification_id < 0:
        notification = _personal_notifications_qs(user).filter(pk=-notification_id).first()
        if not notification:
            return False
        notification.mark_as_read()
        return True

    notification = active_app_notifications_qs().filter(pk=notification_id).first()
    if not notification:
        return False
    AppNotificationRead.objects.get_or_create(
        user=user,
        notification=notification,
        defaults={"read_at": timezone.now()},
    )
    return True


def mark_all_app_notifications_read(user) -> int:
    active_ids = list(active_app_notifications_qs().values_list("id", flat=True))
    existing_ids = set(
        AppNotificationRead.objects.filter(
            user=user,
            notification_id__in=active_ids,
        ).values_list("notification_id", flat=True)
    )
    to_create = [
        AppNotificationRead(
            user=user,
            notification_id=notification_id,
            read_at=timezone.now(),
        )
        for notification_id in active_ids
        if notification_id not in existing_ids
    ]
    marked = len(to_create)
    if to_create:
        AppNotificationRead.objects.bulk_create(to_create)

    personal_unread = _personal_notifications_qs(user).filter(is_read=False)
    personal_marked = personal_unread.count()
    if personal_marked:
        now = timezone.now()
        for notification in personal_unread:
            notification.is_read = True
            notification.read_at = now
        Notification.objects.bulk_update(
            personal_unread,
            ["is_read", "read_at"],
        )
    return marked + personal_marked
