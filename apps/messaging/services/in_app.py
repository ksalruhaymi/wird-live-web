from apps.notification.models import Notification

def send_in_app(broadcast, recipients):
    Notification.objects.bulk_create([
        Notification(
            user=u,
            title=broadcast.title,
            body=broadcast.body,
            broadcast=broadcast,
        )
        for u in recipients
    ])
