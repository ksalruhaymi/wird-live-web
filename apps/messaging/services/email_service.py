from django.core.mail import EmailMultiAlternatives
from django.utils.html import strip_tags
from django.conf import settings


def send_email(to_email, subject, html_body):
    plain_body = strip_tags(html_body)

    msg = EmailMultiAlternatives(
        subject=subject,
        body=plain_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[to_email],
    )

    msg.attach_alternative(html_body, "text/html")
    msg.send()