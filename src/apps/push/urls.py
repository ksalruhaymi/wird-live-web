from django.urls import path
from . import views

app_name = "push"

urlpatterns = [
    path("", views.push_dashboard, name="dashboard"),
]
