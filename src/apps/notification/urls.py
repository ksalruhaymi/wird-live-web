from django.urls import path
from . import views

app_name = "apps.notification"

urlpatterns = [
    path("", views.overview_notifications, name="overview_notifications"),
    path("create", views.notification_create, name="notification_create"),
    path("inapp/", views.notifications_inapp, name="notifications_inapp"),
    path("inapp/<int:pk>/", views.notification_detail, name="notification_detail"),
    path("inbox/", views.notifications_inbox, name="notifications_inbox"),
]
