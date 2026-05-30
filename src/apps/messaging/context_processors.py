from .models import MessageChannel, MessageDelivery


def notifications_counts(request):
    return {}


def messages_counts(request):
    if not request.user.is_authenticated:
        return {}

    unread_messages_count = MessageDelivery.objects.filter(
        user=request.user,
        is_read=False,
        broadcast__channel=MessageChannel.EMAIL,
    ).count()

    return {
        "messages_unread_count": unread_messages_count,
    }
