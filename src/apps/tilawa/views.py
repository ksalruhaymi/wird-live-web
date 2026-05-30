from pathlib import Path

from django.conf import settings
from django.shortcuts import render, get_object_or_404
from django.utils.translation import get_language

from apps.quran.models import Qurra, Surah
from apps.quran.services.quran_service import build_quran_context
from core.utils.media import uses_remote_media


# Arabic display labels for each mushaf/riwaya
MUSHAF_LABELS = {
    "hafs":   "حفص عن عاصم",
    "warsh":  "ورش عن نافع",
    "qaloun": "قالون عن نافع",
    "shuba":  "شعبة عن عاصم",
    "douri":  "الدوري عن أبي عمرو",
    "sousi":  "السوسي عن أبي عمرو",
}

# Preferred order for display
MUSHAF_ORDER = ["hafs", "warsh", "qaloun", "shuba", "douri", "sousi"]


def _find_available_mushafs(qari_code: str) -> list[dict]:
    """
    Return all mushafs that have audio files for this qari,
    sorted by MUSHAF_ORDER with 'hafs' first if available.
    """
    audio_base = Path(settings.MEDIA_ROOT) / "audio"
    if not audio_base.is_dir():
        return [{"key": key, "label": MUSHAF_LABELS.get(key, key)} for key in MUSHAF_ORDER] if uses_remote_media() else []

    found = {
        d.name
        for d in audio_base.iterdir()
        if d.is_dir() and (d / qari_code).is_dir()
    }

    result = []
    for key in MUSHAF_ORDER:
        if key in found:
            result.append({"key": key, "label": MUSHAF_LABELS.get(key, key)})
    # any remaining not in order list
    for key in sorted(found):
        if key not in MUSHAF_ORDER:
            result.append({"key": key, "label": MUSHAF_LABELS.get(key, key)})

    return result


def qari_list(request):
    """
    List all quraa (audio-only).
    """
    base_context = build_quran_context(request)

    current_language = (get_language() or "ar").split("-")[0]
    is_arabic_ui = current_language in ("ar", "ur")

    quraa = list(Qurra.objects.filter(is_visible=True).order_by("code"))

    # For non-Arabic UI: only show reciters who have hafs audio available
    if not is_arabic_ui:
        audio_base = Path(settings.MEDIA_ROOT) / "audio" / "hafs"
        if audio_base.is_dir():
            quraa = [q for q in quraa if (audio_base / q.code).is_dir()]

    context = {
        **base_context,
        "quraa": quraa,
        "is_arabic_ui": is_arabic_ui,
    }
    return render(request, "tilawa/qari_list.html", context)


def qari_listen(request, qari_code: str):
    """
    Single qari listening page – plays individual ayah files sequentially.
    """
    base_context = build_quran_context(request)

    qari = get_object_or_404(Qurra, code=qari_code)
    surahs = Surah.objects.all().order_by("surah_number")

    current_language = (get_language() or "ar").split("-")[0]
    is_arabic_ui = current_language in ("ar", "ur")

    available_mushafs = _find_available_mushafs(qari_code)

    # Non-Arabic UI: force hafs only
    if not is_arabic_ui:
        available_mushafs = [m for m in available_mushafs if m["key"] == "hafs"]

    # Default: hafs if available, else first found
    default_mushaf = "hafs"
    if available_mushafs:
        keys = [m["key"] for m in available_mushafs]
        default_mushaf = "hafs" if "hafs" in keys else keys[0]

    for surah in surahs:
        surah.i18n_key = f"surah_{surah.surah_number}"

    context = {
        **base_context,
        "qari": qari,
        "surahs": surahs,
        "mushaf_key": default_mushaf,
        "available_mushafs": available_mushafs,
        "is_arabic_ui": is_arabic_ui,
    }
    return render(request, "tilawa/qari_listen.html", context)