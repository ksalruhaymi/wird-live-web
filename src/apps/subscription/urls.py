from django.urls import path
from . import views

app_name = "subscription"

urlpatterns = [
    path("", views.overview_subscription, name="overview_subscription"),
    path("create/", views.subscription_create, name="subscription_create"),
    path("subscribers/", views.newsletter_subscriber, name="newsletter_subscriber"),
    path("subscribe/", views.newsletter_subscribe, name="newsletter_subscribe"),
    path("unsubscribe/<uuid:token>/",views.newsletter_unsubscribe,name="newsletter_unsubscribe",),
]