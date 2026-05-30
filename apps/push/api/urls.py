from django.urls import path
from . import views

app_name = "push_api"

urlpatterns = [
    path("devices/register/", views.register_device, name="register-device"),
]
