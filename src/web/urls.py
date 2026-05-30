# web/urls.py
from django.urls import path
from . import views

app_name = "web"

urlpatterns = [
    path("", views.home, name="home"),
    path("about/", views.about, name="about"),
    path("privacy-policy/", views.privacy_policy, name="privacy_policy"),
    path("translation/", views.translation, name="translation"),
    path("translation/page-data/", views.translation_page_data, name="translation_page_data"),
    path("translation/<int:surah_number>/", views.translation, name="translation_surah"),
]
