from django.urls import path

from apps.notification.api import views

app_name = "notification_api"

urlpatterns = [
    path("app-notifications/", views.app_notifications_list, name="app_notifications_list"),
    path(
        "app-notifications/unread-count/",
        views.app_notifications_unread_count,
        name="app_notifications_unread_count",
    ),
    path(
        "app-notifications/mark-all-read/",
        views.app_notifications_mark_all_read,
        name="app_notifications_mark_all_read",
    ),
    path(
        "app-notifications/<int:notification_id>/read/",
        views.app_notification_mark_read,
        name="app_notification_mark_read",
    ),
]
