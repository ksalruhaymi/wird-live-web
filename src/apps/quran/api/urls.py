# apps/quran/api/urls.py

from django.urls import path
from . import views

app_name = "quran_api"

urlpatterns = [
    path("surahs/", views.surah_list, name="surah-list"),
    path("surahs/<int:surah_number>/", views.surah_detail, name="surah-detail"),
    path("surahs/<int:surah_number>/ayahs/", views.surah_ayahs, name="surah-ayahs"),

    path("ayahs/", views.ayah_list, name="ayah-list"),
    path("ayahs/<int:pk>/", views.ayah_detail, name="ayah-detail"),

    path("pages/<int:page_number>/", views.page_detail, name="page-detail"),
    path("ayahs/<int:surah_number>/<int:ayah_number>/positions/",views.ayah_positions,name="ayah-positions",),
    # Alias متوافق مع عميل Flutter (`ApiConfig.ayahPositionUrl`).
    path("ayah-positions/<int:surah_number>/<int:ayah_number>/",views.ayah_positions,name="ayah-positions-alias",),
    path("pages/<int:page_number>/positions/",views.page_positions,name="page-positions",),
    path("tafsir/books/", views.tafsir_book_list, name="tafsir-book-list"),
    path("tafsir/books/<int:pk>/", views.tafsir_book_detail, name="tafsir-book-detail"),
    path("tafsir/books/<int:book_id>/surahs/<int:surah_number>/ayahs/<int:ayah_number>/", views.tafsir_by_book_surah_ayah, name="tafsir-by-book-surah-ayah"),
    path("ayahs/<int:ayah_number>/tafsir/", views.tafsir_by_ayah_number, name="tafsir-by-ayah_number"),

    path("qurra/", views.qurra_list, name="qurra-list"),
    path("qurra/<int:pk>/", views.qurra_detail, name="qurra-detail"),

    path("search/ayahs/", views.search_ayahs, name="search-ayahs"),
    path("search/tafsir/", views.search_tafsir, name="search-tafsir"),

    path("meta/config/", views.meta_config, name="meta-config"),
    path("mushafs/", views.mushafs_catalog, name="mushafs-catalog"),

    path("features/", views.feature_flags, name="feature_flags"),
    path("audio/readers/", views.available_audio_readers, name="available_audio_readers"),

    # Translation audio
    path("translations/<str:lang_code>/<int:surah_number>/<int:ayah_number>/", views.translation_ayah_audio, name="translation-ayah-audio"),

    # Reciter audio
    path("audio/<str:mushaf_code>/<str:reciter_code>/<int:surah_number>/<int:ayah_number>/", views.reciter_ayah_audio, name="reciter-ayah-audio"),
]