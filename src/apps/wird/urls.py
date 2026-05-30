from django.urls import path
from . import views

app_name = "wird"

urlpatterns = [
    path("reminders/", views.reminders, name="reminders"),
    path("reminders/toggle/", views.toggle_reminder, name="toggle_reminder"),
    path("reminders/save-time/", views.save_reminder_time, name="save_reminder_time"),
]
