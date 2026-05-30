from django.urls import path
from .views import quran, ayah_tafsir, page_tafsir, search_ayahs, page_positions_json, ayah_word_meanings, ayah_short_tafsir, start_khatma, complete_current_wird, update_khatma_progress, toggle_tracking_mode, record_audio_listen_event


app_name = "quran"

urlpatterns = [
    path("", quran, name="quran"),

    path("page/<int:page>/", quran, name="quran_page"),
    path("page/<int:page>/positions/", page_positions_json, name="page_positions_json"),
    path("surah/<int:surah>/", quran, name="quran_surah"),
    path("quraa/<str:qari>/", quran, name="quran_qari"),
    path("tafsir/<int:page>/", quran, {"forced_mode": "tafsir"}, name="quran_tafsir"),
    path("ayah-short-tafsir/", ayah_short_tafsir, name="ayah_short_tafsir"),

    path("ayah-tafsir/", ayah_tafsir, name="ayah_tafsir"),
    path("page-tafsir/", page_tafsir, name="page_tafsir"),
    path("search-ayahs/", search_ayahs, name="search_ayahs"),
    path("ayah-word-meanings/", ayah_word_meanings, name="ayah_word_meanings"),

    path("<str:mushaf>/page/<int:page>/", quran, name="quran_mushaf_page"),
    path("<str:mushaf>/surah/<int:surah>/", quran, name="quran_mushaf_surah"),
    path("<str:mushaf>/quraa/<str:qari>/", quran, name="quran_mushaf_qari"),
    path("<str:mushaf>/tafsir/<int:page>/", quran, {"forced_mode": "tafsir"}, name="quran_mushaf_tafsir"),
    path("<str:mushaf>/", quran, name="quran_mushaf"),

    path("khatma/start/", start_khatma, name="start_khatma"),
    path("khatma/complete-wird/", complete_current_wird, name="complete_current_wird"),
    path("khatma/progress/", update_khatma_progress, name="update_khatma_progress"),
    path("khatma/toggle-tracking/", toggle_tracking_mode, name="toggle_tracking_mode"),
    path("audio/listen-event/", record_audio_listen_event, name="audio_listen_event"),
]