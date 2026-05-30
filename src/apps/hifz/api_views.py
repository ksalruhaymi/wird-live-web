from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
import re

from apps.quran.models import Ayah
from core.utils.media import media_url
from .services.audio_guard import detect_speech_presence
from .services.recitation_service import transcribe_uploaded_audio
from .services.recitation_compare import analyze_recitation_score


def get_ayah_text_value(ayah):
    return (
        getattr(ayah, "text", None)
        or getattr(ayah, "text_uthmani", None)
        or getattr(ayah, "uthmani_text", None)
        or getattr(ayah, "content", None)
        or ""
    )


def build_empty_analysis_response(message, expected_text="", audio_debug=None, error_type="no_speech", tajweed_tip=""):
    return {
        "score": 0,
        "is_correct": False,
        "message": message,
        "selected_ayah_text": expected_text,
        "recognized_text": "",
        "expected_parts": [],
        "recognized_parts": [],
        "word_analysis": [],
        "errors": [
            {
                "expected_word": "",
                "recognized_word": "",
                "error_type": error_type,
                "score": 0,
                "tajweed_tip": tajweed_tip,
            }
        ],
        "audio_debug": audio_debug or {},
    }


@require_GET
def ayah_text_api(request):
    surah_number = request.GET.get("surah_number")
    ayah_number = request.GET.get("ayah_number")

    if not surah_number or not ayah_number:
        return JsonResponse({"error": "Surah and ayah are required."}, status=400)

    try:
        ayah = Ayah.objects.get(
            surah_number=int(surah_number),
            ayah_number=int(ayah_number),
        )
    except Ayah.DoesNotExist:
        return JsonResponse({"error": "Ayah not found."}, status=404)

    expected_text = get_ayah_text_value(ayah)

    if not expected_text:
        return JsonResponse({"error": "Ayah text field not found in model."}, status=500)

    return JsonResponse({
        "surah_number": ayah.surah_number,
        "ayah_number": ayah.ayah_number,
        "text": expected_text,
    })


@require_POST
def recitation_check_api(request):
    audio_file = request.FILES.get("audio")
    surah_number = request.POST.get("surah_number")
    ayah_number = request.POST.get("ayah_number")

    if not audio_file:
        return JsonResponse({"error": "Audio file is required."}, status=400)

    if not surah_number or not ayah_number:
        return JsonResponse({"error": "Surah and ayah are required."}, status=400)

    try:
        ayah = Ayah.objects.get(
            surah_number=int(surah_number),
            ayah_number=int(ayah_number),
        )
    except Ayah.DoesNotExist:
        return JsonResponse({"error": "Ayah not found."}, status=404)

    expected_text = get_ayah_text_value(ayah)
    if not expected_text:
        return JsonResponse({"error": "Ayah text field not found in model."}, status=500)

    qari_folder = (request.POST.get("qari") or "alhudhaify").strip().lower()
    mushaf_key = (request.POST.get("mushaf") or "hafs").strip().lower()

    if not re.fullmatch(r"[a-z0-9_-]+", qari_folder or ""):
        qari_folder = "alhudhaify"
    if not re.fullmatch(r"[a-z0-9_-]+", mushaf_key or ""):
        mushaf_key = "hafs"

    shaykh_audio_url = media_url(
        f"audio/{mushaf_key}/{qari_folder}/"
        f"{ayah.surah_number:03d}/"
        f"{ayah.surah_number:03d}{ayah.ayah_number:03d}.mp3"
    )

    try:
        audio_file.seek(0)
        speech_check = detect_speech_presence(audio_file)
    except Exception:
        speech_check = {
            "has_speech": True,
            "reason": "guard_skipped",
            "duration": 0.0,
            "rms": 0.0,
            "non_silent_ratio": 0.0,
            "non_silent_duration": 0.0,
        }

    if not speech_check.get("has_speech", False):
        payload = build_empty_analysis_response(
            message="لم يتم اكتشاف تلاوة واضحة في التسجيل. يرجى التحدث بوضوح ثم إعادة المحاولة.",
            expected_text=expected_text,
            audio_debug=speech_check,
            error_type="no_speech",
            tajweed_tip="يبدو أن التسجيل صامت أو يحتوي على ضوضاء فقط. اقترب من الميكروفون وأعد القراءة بصوت واضح.",
        )
        payload["shaykh_audio_url"] = shaykh_audio_url
        return JsonResponse(payload)

    audio_file.seek(0)
    recognized_text = transcribe_uploaded_audio(audio_file)
    recognized_text = (recognized_text or "").strip()

    if not recognized_text or len(recognized_text) < 2:
        payload = build_empty_analysis_response(
            message="لم يتم التقاط تلاوة مفهومة. أعد التسجيل في مكان أهدأ وبصوت أوضح.",
            expected_text=expected_text,
            audio_debug=speech_check,
            error_type="unclear_audio",
            tajweed_tip="التسجيل غير واضح بما يكفي للتحليل. أعد القراءة في مكان هادئ واقترب من الميكروفون.",
        )
        payload["shaykh_audio_url"] = shaykh_audio_url
        return JsonResponse(payload)

    result = analyze_recitation_score(expected_text, recognized_text)

    return JsonResponse({
        "score": result["score"],
        "is_correct": result["is_correct"],
        "message": result["message"],
        "selected_ayah_text": expected_text,
        "recognized_text": result["recognized_text"],
        "expected_parts": result["expected_parts"],
        "recognized_parts": result["recognized_parts"],
        "word_analysis": result["word_analysis"],
        "errors": result["errors"],
        "shaykh_audio_url": shaykh_audio_url,
        "audio_debug": speech_check,
    })