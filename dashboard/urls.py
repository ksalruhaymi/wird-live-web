from django.urls import path

from .views import dashboard,home,overview

app_name = "dashboard" 


urlpatterns = [
    path("manage/", dashboard, name="manage"),
    path("dashboard/", home, name="home"),
    path("overview_dashboard/", overview, name="overview_dashboard"),
]
