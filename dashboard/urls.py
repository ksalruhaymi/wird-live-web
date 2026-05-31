from django.shortcuts import redirect
from django.urls import path

from .views import (
    announcement_create,
    announcement_delete,
    announcement_list,
    announcement_toggle_active,
    announcement_update,
    call_session_list,
    dashboard,
    home,
    overview,
    subscription_plan_create,
    subscription_plan_delete,
    subscription_plan_list,
    subscription_plan_toggle_active,
    subscription_plan_update,
    student_subscription_list,
    teacher_availability_list,
    session_evaluation_list,
    call_recording_list,
    chat_conversation_list,
    chat_conversation_detail,
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
    path("announcements/", announcement_list, name="announcement_list"),
    path("announcements/create/", announcement_create, name="announcement_create"),
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
    path("chat/", chat_conversation_list, name="chat_conversation_list"),
    path("chat/<int:pk>/", chat_conversation_detail, name="chat_conversation_detail"),
]
