from django.shortcuts import redirect
from django.urls import path

from .views import (
    announcement_create,
    announcement_delete,
    announcement_detail,
    announcement_list,
    announcement_toggle_active,
    announcement_update,
    app_notification_create,
    app_notification_delete,
    app_notification_detail,
    app_notification_list,
    app_notification_toggle_active,
    app_notification_update,
    call_session_list,
    dashboard,
    home,
    overview,
    subscription_plan_create,
    subscription_plan_delete,
    subscription_plan_list,
    subscription_plan_toggle_active,
    subscription_plan_update,
    student_subscription_balance_update,
    student_subscription_delete,
    student_subscription_detail,
    student_subscription_list,
    student_subscription_update,
    teacher_availability_list,
    session_evaluation_list,
    call_recording_delete,
    call_recording_list,
)

app_name = "dashboard"


urlpatterns = [
    path("", lambda request: redirect("dashboard:home_dashboard")),
    path("home/", home, name="home_dashboard"),
    path("manage/", dashboard, name="manage"),
    path("dashboard/", home, name="home"),
    path("overview_dashboard/", overview, name="overview_dashboard"),
    path("subscription-plans/", subscription_plan_list, name="subscription_plan_list"),
    path(
        "subscription-plans/create/",
        subscription_plan_create,
        name="subscription_plan_create",
    ),
    path(
        "subscription-plans/<int:pk>/edit/",
        subscription_plan_update,
        name="subscription_plan_update",
    ),
    path(
        "subscription-plans/<int:pk>/delete/",
        subscription_plan_delete,
        name="subscription_plan_delete",
    ),
    path(
        "subscription-plans/<int:pk>/toggle-active/",
        subscription_plan_toggle_active,
        name="subscription_plan_toggle_active",
    ),
    path("subscriptions/", student_subscription_list, name="student_subscription_list"),
    path(
        "subscriptions/user/<int:user_id>/",
        student_subscription_detail,
        name="student_subscription_detail",
    ),
    path(
        "subscriptions/user/<int:user_id>/balance/edit/",
        student_subscription_balance_update,
        name="student_subscription_balance_update",
    ),
    path(
        "subscriptions/<int:pk>/edit/",
        student_subscription_update,
        name="student_subscription_update",
    ),
    path(
        "subscriptions/<int:pk>/delete/",
        student_subscription_delete,
        name="student_subscription_delete",
    ),
    path("app-notifications/", app_notification_list, name="app_notification_list"),
    path(
        "app-notifications/create/",
        app_notification_create,
        name="app_notification_create",
    ),
    path(
        "app-notifications/<int:pk>/",
        app_notification_detail,
        name="app_notification_detail",
    ),
    path(
        "app-notifications/<int:pk>/edit/",
        app_notification_update,
        name="app_notification_update",
    ),
    path(
        "app-notifications/<int:pk>/delete/",
        app_notification_delete,
        name="app_notification_delete",
    ),
    path(
        "app-notifications/<int:pk>/toggle-active/",
        app_notification_toggle_active,
        name="app_notification_toggle_active",
    ),
    path("announcements/", announcement_list, name="announcement_list"),
    path("announcements/create/", announcement_create, name="announcement_create"),
    path(
        "announcements/<int:pk>/",
        announcement_detail,
        name="announcement_detail",
    ),
    path("announcements/<int:pk>/edit/", announcement_update, name="announcement_update"),
    path("announcements/<int:pk>/delete/", announcement_delete, name="announcement_delete"),
    path(
        "announcements/<int:pk>/toggle-active/",
        announcement_toggle_active,
        name="announcement_toggle_active",
    ),
    path("calls/", call_session_list, name="call_session_list"),
    path(
        "teachers/availability/",
        teacher_availability_list,
        name="teacher_availability_list",
    ),
    path("evaluations/", session_evaluation_list, name="session_evaluation_list"),
    path("recordings/", call_recording_list, name="call_recording_list"),
    path(
        "recordings/<int:pk>/delete/",
        call_recording_delete,
        name="call_recording_delete",
    ),
]
