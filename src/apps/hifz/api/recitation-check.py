from django.urls import path
from . import views
from .api_views import recitation_check_api

app_name = "hifz"

urlpatterns = [
    path("", views.home, name="home"),
    path("page/<int:page>/", views.home, name="home_page"),
    path("<str:mushaf>/", views.home, name="home_mushaf"),
    path("<str:mushaf>/page/<int:page>/", views.home, name="home_mushaf_page"),
    path("<str:mushaf>/<int:page>/", views.home, name="home_mushaf_page_legacy"),

    path("api/recitation-check/", recitation_check_api, name="recitation_check_api"),
]