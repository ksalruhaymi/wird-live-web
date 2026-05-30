from celery import shared_task
from django.utils import timezone

from .models import MessageBroadcast, MessageDelivery, DeliveryStatus, MessageStatus
from .services.email_service import send_email


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

    failed_count = 0

    for delivery in deliveries:
        email = (delivery.email or "").strip()

        if "@" not in email:
            delivery.status = DeliveryStatus.FAILED
            delivery.error_message = "Invalid email format."
            delivery.save(update_fields=["status", "error_message"])
            failed_count += 1
            continue

        try:
            send_email(
                to_email=email,
                subject=broadcast.title,
                html_body=broadcast.body,
            )
        except Exception as exc:
            delivery.status = DeliveryStatus.FAILED
            delivery.error_message = str(exc)
            delivery.save(update_fields=["status", "error_message"])
            failed_count += 1
        else:
            delivery.status = DeliveryStatus.SENT
            delivery.sent_at = timezone.now()
            delivery.save(update_fields=["status", "sent_at"])

    broadcast.failed_recipients = failed_count
    broadcast.sent_at = timezone.now()
    broadcast.status = MessageStatus.SENT if failed_count == 0 else MessageStatus.FAILED
    broadcast.save(update_fields=["failed_recipients", "sent_at", "status"])