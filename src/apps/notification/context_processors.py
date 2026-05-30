from .models import Notification


def notifications_counts(request):
    if not request.user.is_authenticated:
        return {
            "notifications_unread_count": 0,
        }

    unread_notifications_count = Notification.objects.filter(
        user=request.user,
        is_read=False,
    ).count()

    return {
        "notifications_unread_count": unread_notifications_count,
    }


def messages_counts(request):
    # الرسائل الآن ليست من Notification
    return {
        "messages_unread_count": 0,
    }