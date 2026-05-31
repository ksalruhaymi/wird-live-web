from django.urls import path

from . import views

app_name = "subscription_api"

urlpatterns = [
    path("subscription/plans/", views.list_plans, name="list-plans"),
    path("subscription/current/", views.current_subscription, name="current"),
    path("subscription/call-eligibility/", views.call_eligibility, name="call-eligibility"),
    path("subscription/subscribe/", views.subscribe, name="subscribe"),
    path("subscription/my-subscriptions/", views.my_subscriptions, name="my-subscriptions"),
]
