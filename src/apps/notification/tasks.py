from celery import shared_task
from django.conf import settings
from django.utils import timezone
from django.core.mail import get_connection, EmailMessage

from .models import (
    MessageBroadcast,
    MessageDelivery,
    DeliveryStatus,
    Communicationtatus,
)


@shared_task
def send_broadcast_emails(broadcast_id: int):
    """Send broadcast emails in background using Celery."""
    broadcast = MessageBroadcast.objects.get(id=broadcast_id)

    deliveries = MessageDelivery.objects.filter(
        broadcast=broadcast,
        status=DeliveryStatus.PENDING,
    )

    if not deliveries.exists():
        return

    broadcast.status = Communicationtatus.SENDING
    broadcast.save(update_fields=["status"])

    connection = get_connection()
    connection.open()

    failed_count = 0

    try:
        for delivery in deliveries:
            email = (delivery.email or "").strip()

            if not email and delivery.user_id:
                email = (getattr(delivery.user, "email", "") or "").strip()

            if "@" not in email:
                delivery.status = DeliveryStatus.FAILED
                delivery.error_message = "Invalid email format."
                delivery.save(update_fields=["status", "error_message"])
                failed_count += 1
                continue

            try:
                message = EmailMessage(
                    subject=broadcast.title,
                    body=broadcast.body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[email],
                    connection=connection,
                )
                message.send(fail_silently=False)
            except Exception as exc:
                delivery.status = DeliveryStatus.FAILED
                delivery.error_message = str(exc)
                delivery.save(update_fields=["status", "error_message"])
                failed_count += 1
            else:
                delivery.status = DeliveryStatus.SENT
                delivery.sent_at = timezone.now()
                delivery.error_message = ""
                delivery.save(update_fields=["status", "sent_at", "error_message"])
    finally:
        connection.close()

    broadcast.failed_recipients = failed_count
    broadcast.sent_at = timezone.now()
    broadcast.status = (
        Communicationtatus.SENT if failed_count == 0 else Communicationtatus.FAILED
    )
    broadcast.save(update_fields=["failed_recipients", "sent_at", "status"])