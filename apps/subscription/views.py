from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.mail import EmailMessage, get_connection
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import NewsletterSubscriber


@login_required
def subscription_create(request):
    subscribers = NewsletterSubscriber.objects.filter(
        is_active=True,
        is_confirmed=True,
    ).order_by("-subscribed_at")

    if request.method == "POST":
        title = (request.POST.get("title") or "").strip()
        body = (request.POST.get("body") or "").strip()

        if not title or not body:
            messages.error(request, _("title_and_body_required"))
            return redirect("apps.subscription:subscription_create")

        if not subscribers.exists():
            messages.warning(request, _("no_subscribers_available"))
            return redirect("apps.subscription:subscription_create")

        sent_count = 0
        failed_count = 0

        connection = get_connection()
        connection.open()

        try:
            for subscriber in subscribers:
                try:
                    unsubscribe_url = request.build_absolute_uri(
                        reverse(
                            "apps.subscription:newsletter_unsubscribe",
                            kwargs={"token": str(subscriber.unsubscribe_token)},
                        )
                    )

                    full_body = (
                        f"{body}\n\n"
                        f"{_('email_separator')}\n"
                        f"{_('newsletter_subscription_notice')}\n"
                        f"{_('unsubscribe_label')}:\n{unsubscribe_url}"
                    )

                    message = EmailMessage(
                        subject=title,
                        body=full_body,
                        from_email=settings.DEFAULT_FROM_EMAIL,
                        to=[subscriber.email],
                        connection=connection,
                    )
                    message.send()
                    sent_count += 1
                except Exception:
                    failed_count += 1
        finally:
            connection.close()

        if sent_count and not failed_count:
            messages.success(
                request,
                _("message_sent_to_subscribers") % {"count": sent_count},
            )
        elif sent_count and failed_count:
            messages.warning(
                request,
                _("message_sent_with_failures") % {
                    "sent_count": sent_count,
                    "failed_count": failed_count,
                },
            )
        else:
            messages.error(request, _("message_send_failed"))

        return redirect("apps.subscription:subscription_create")

    return render(
        request,
        "subscription/create/subscription_create.html",
        {
            "tab": "center",
            "subscribers_count": subscribers.count(),
        },
    )


@login_required
def overview_subscription(request):
    total_subscribers = NewsletterSubscriber.objects.count()
    active_subscribers = NewsletterSubscriber.objects.filter(is_active=True).count()
    confirmed_subscribers = NewsletterSubscriber.objects.filter(is_confirmed=True).count()

    return render(
        request,
        "subscription/overview/overview_subscription.html",
        {
            "tab": "overview_subscription",
            "total_subscribers": total_subscribers,
            "active_subscribers": active_subscribers,
            "confirmed_subscribers": confirmed_subscribers,
        },
    )


def newsletter_subscribe(request):
    referer = request.META.get("HTTP_REFERER", "/")
    redirect_url = f"{referer}#newsletter-form"

    if request.method == "POST":
        email = (request.POST.get("email") or "").strip().lower()

        if not email:
            messages.error(request, _("please_enter_email"))
            return redirect(redirect_url)

        subscriber, created = NewsletterSubscriber.objects.get_or_create(
            email=email,
            defaults={
                "is_active": True,
                "is_confirmed": True,
            },
        )

        if created:
            unsubscribe_url = request.build_absolute_uri(
                reverse(
                    "apps.subscription:newsletter_unsubscribe",
                    kwargs={"token": str(subscriber.unsubscribe_token)},
                )
            )

            subject = _("newsletter_welcome_subject")
            body = (
                f"{_('newsletter_greeting')}\n\n"
                f"{_('newsletter_thank_you_for_subscribing')}\n"
                f"{_('newsletter_joined_successfully')}\n\n"
                f"{_('newsletter_unsubscribe_anytime')}\n"
                f"{unsubscribe_url}\n\n"
                f"{_('newsletter_closing')}\n"
                f"{_('wird-live_platform_name')}"
            )

            try:
                EmailMessage(
                    subject=subject,
                    body=body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[subscriber.email],
                ).send()
            except Exception:
                pass

            messages.success(
                request,
                _("newsletter_subscription_success"),
            )

        else:
            if not subscriber.is_active:
                subscriber.is_active = True
                subscriber.unsubscribed_at = None
                subscriber.save(update_fields=["is_active", "unsubscribed_at"])

                messages.success(
                    request,
                    _("newsletter_subscription_reactivated"),
                )
            else:
                messages.info(request, _("email_already_subscribed"))

        return redirect(redirect_url)

    return redirect("/")


def newsletter_unsubscribe(request, token):
    subscriber = get_object_or_404(NewsletterSubscriber, unsubscribe_token=token)

    if subscriber.is_active:
        subscriber.is_active = False
        subscriber.unsubscribed_at = timezone.now()
        subscriber.save(update_fields=["is_active", "unsubscribed_at"])

        messages.success(
            request,
            _("unsubscribe_success_message"),
            extra_tags="toast",
        )
    else:
        messages.info(
            request,
            _("unsubscribe_already_done"),
            extra_tags="toast",
        )

    return render(
        request,
        "subscription/unsubscribe/unsubscribe_done.html",
        {
            "subscriber_email": subscriber.email,
        },
    )


@login_required
def newsletter_subscriber(request):
    try:
        per_page = int(request.GET.get("per_page", 10))
    except (TypeError, ValueError):
        per_page = 10

    if per_page <= 0:
        per_page = 10

    qs = NewsletterSubscriber.objects.all().order_by("-subscribed_at")
    total_subscribers = qs.count()

    paginator = Paginator(qs, per_page)
    page_number = request.GET.get("page")
    subscribers = paginator.get_page(page_number)

    return render(
        request,
        "subscription/subscriber/newsletter_subscriber.html",
        {
            "tab": "subscribers",
            "subscribers": subscribers,
            "total_subscribers": total_subscribers,
            "per_page": per_page,
            "subscribers_page_numbers": range(
                max(subscribers.number - 2, 1),
                min(subscribers.number + 3, paginator.num_pages + 1),
            ),
        },
    )