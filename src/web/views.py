import json
import random

from django.db.models.functions import Length
from django.http import JsonResponse
from django.shortcuts import render

from core.models import SiteStat
from apps.quran.models import Qurra, TafsirBook, Tafsir, Surah, Ayah, AyahTranslation
from apps.quran.mushaf_config import MUSHAFS, get_all_mushaf_dimensions
from apps.quran.views.quran_views import get_qurra_for_mushaf
from django.utils.translation import get_language

# Audio translation folders available in /media/translations/.
TRANSLATION_AUDIO_FOLDERS = {
    # The URL pattern is:
    # /media/translations/{folder}/{surah_3_digits}/{surah_3_digits}{ayah_3_digits}.mp3
    # Example: /media/translations/english_rwwad/001/001006.mp3
    "en": "english_rwwad",
    "fr": "french_rashid",
    "fa": "persian_ih",
    "zh": "chinese_suliman",
    "fil": "tagalog_rwwad",
    "tl": "tagalog_rwwad",
    "pt": "portuguese_nasr",
    "as": "assamese_rafeeq",
    "az": "azeri_musayev",
    "nl": "dutch_center",
    "si": "sinhalese_mahir",
    "so": "somali_yacob",
    "vi": "vietnamese_rwwad",
}

RTL_LANGUAGES = {"ar", "ur", "fa"}


def _normalize_translation_language():
    current_language = (get_language() or "ar").split("-")[0]
    if current_language == "tl":
        return "fil"
    return current_language


def _get_total_quran_pages():
    max_page_value = Ayah.objects.order_by("-page_number").values_list("page_number", flat=True).first()
    return max_page_value or 604


def _build_translation_page(page_number, language, surah_by_number=None):
    if surah_by_number is None:
        surah_by_number = {
            item.surah_number: item
            for item in Surah.objects.order_by("surah_number")
        }

    ayahs = list(
        Ayah.objects.filter(page_number=page_number)
        .order_by("page_number", "surah_number", "ayah_number")
        .only("surah_number", "ayah_number", "page_number", "text")
    )

    translations_by_key = {}
    if language != "ar" and ayahs:
        translations = AyahTranslation.objects.filter(
            language=language,
            surah_number__in=sorted({ayah.surah_number for ayah in ayahs}),
        ).only("surah_number", "ayah_number", "translation")
        translations_by_key = {
            (item.surah_number, item.ayah_number): item.translation
            for item in translations
        }

    previous_surah_number = None
    items = []
    for ayah in ayahs:
        surah = surah_by_number.get(ayah.surah_number)
        show_surah_header = previous_surah_number != ayah.surah_number
        previous_surah_number = ayah.surah_number
        translation_text = ""
        if language != "ar":
            translation_text = translations_by_key.get((ayah.surah_number, ayah.ayah_number), "")

        surah_name = ""
        if surah:
            if language != "ar" and surah.surah_name_en:
                surah_name = surah.surah_name_en
            else:
                surah_name = surah.surah_name_ar

        items.append({
            "surah_number": ayah.surah_number,
            "ayah_number": ayah.ayah_number,
            "page_number": ayah.page_number,
            "surah_name": surah_name,
            "surah_name_ar": surah.surah_name_ar if surah else "",
            "surah_name_en": surah.surah_name_en if surah else "",
            "ayah_count": surah.ayah_count if surah else "",
            "show_surah_header": show_surah_header,
            "arabic_text": ayah.text or "",
            "translation": translation_text,
            "key": f"{ayah.surah_number}:{ayah.ayah_number}:{language}",
        })

    return {"page": page_number, "items": items}


def get_home_qurra(mushaf_key="hafs"):
    qurra = Qurra.objects.all().order_by("code")[:6]
    return qurra


def get_home_tafasir():
    tafasir = TafsirBook.objects.filter(is_active=True).order_by("sort_order", "number")
    return tafasir


def get_home_mushaf_list():
    return [
        {
            "key": key,
            "title_key": cfg["title_key"],
            "image": f"{key}.png",
        }
        for key, cfg in MUSHAFS.items()
    ]


HAFS_RECITER_CODES = [
    "alhudhaify",
    "maher_almuaiqly",
    "ali_jaber",
    "abdulbasit_abdulsamad",
    "alsudais",
    "ibrahim_alakhdar",
    "khalid_almuhanna",
    "alminshawi",
    "abdullah_alJuhani",
    "ibrahim_aldosary",
]

ARABIC_SCRIPT_LANGUAGES = {"ar", "ur", "fa"}

# Surahs with complete MP3 files for all reciters (well-known, popular)
HOME_SURAH_POOL = [1, 2, 3, 12, 18, 36, 55, 56, 67, 78]


def _get_home_reciters():
    all_reciters = list(
        Qurra.objects.filter(code__in=HAFS_RECITER_CODES)
        .values("code", "name_ar", "name_en")
    )
    random.shuffle(all_reciters)
    return all_reciters[:4]


def _get_home_surahs():
    surahs = list(
        Surah.objects.filter(surah_number__in=HOME_SURAH_POOL)
        .values("surah_number", "surah_name_ar", "surah_name_en", "ayah_count")
    )
    return {s["surah_number"]: s for s in surahs}


TAFSIR_MAX_CHARS = 320


def _get_tafsir_samples(count=5):
    book_ids = list(TafsirBook.objects.filter(is_active=True).values_list("id", flat=True))
    if not book_ids:
        return []
    samples = []
    used = set()
    tries = 0
    while len(samples) < count and tries < 80:
        tries += 1
        book_id = random.choice(book_ids)
        entry = (
            Tafsir.objects.filter(book_id=book_id)
            .annotate(_tlen=Length("text"))
            .filter(_tlen__lte=TAFSIR_MAX_CHARS)
            .select_related("book", "ayah__surah")
            .order_by("?")
            .first()
        )
        if not entry:
            continue
        key = (book_id, entry.surah_id, entry.ayah_number)
        if key in used:
            continue
        used.add(key)
        surah = Surah.objects.filter(surah_number=entry.surah_id).first()
        ayah_obj = Ayah.objects.filter(surah_number=entry.surah_id, ayah_number=entry.ayah_number).first()
        ayah_text = ayah_obj.text if ayah_obj else ""
        samples.append({
            "book_name": entry.book.name,
            "surah_name_ar": surah.surah_name_ar if surah else "",
            "surah_name_en": surah.surah_name_en if surah else "",
            "surah_number": entry.surah_id,
            "ayah_number": entry.ayah_number,
            "ayah_text": ayah_text,
            "tafsir_text": entry.text,
        })
    return samples


def _get_translation_samples(language, count=5):
    entries = list(
        AyahTranslation.objects.filter(language=language)
        .select_related()
        .order_by("?")[:count * 3]
    )
    samples = []
    seen_surahs = set()
    for entry in entries:
        if entry.surah_number in seen_surahs:
            continue
        seen_surahs.add(entry.surah_number)
        surah = Surah.objects.filter(surah_number=entry.surah_number).first()
        ayah = Ayah.objects.filter(
            surah_number=entry.surah_number, ayah_number=entry.ayah_number
        ).first()
        samples.append({
            "surah_name_ar": surah.surah_name_ar if surah else "",
            "surah_name_en": surah.surah_name_en if surah else "",
            "surah_number": entry.surah_number,
            "ayah_number": entry.ayah_number,
            "ayah_text": ayah.text if ayah else "",
            "translation": entry.translation,
        })
        if len(samples) >= count:
            break
    return samples


def home(request):
    lang = (get_language() or "ar").split("-")[0]
    if lang == "tl":
        lang = "fil"
    is_arabic = lang in ARABIC_SCRIPT_LANGUAGES

    visitors = SiteStat.objects.filter(key="visitors").first()

    # Pick 4 random reciters and assign each a random surah from the pool
    reciters = _get_home_reciters()
    surahs_map = _get_home_surahs()
    surah_pool = list(surahs_map.values())

    reciters_data = []
    used_surahs = []
    for r in reciters:
        # Try to assign a unique surah to each reciter
        available = [s for s in surah_pool if s["surah_number"] not in used_surahs]
        if not available:
            available = surah_pool
        surah = random.choice(available)
        used_surahs.append(surah["surah_number"])
        reciters_data.append({
            "code": r["code"],
            "name_ar": r["name_ar"],
            "name_en": r["name_en"],
            "surah_number": surah["surah_number"],
            "surah_name_ar": surah["surah_name_ar"],
            "surah_name_en": surah["surah_name_en"],
            "ayah_count": surah["ayah_count"],
        })

    # Hero: first reciter/surah for static display
    hero_reciter_ar = reciters_data[0]["name_ar"] if reciters_data else "علي الحذيفي"
    hero_reciter_en = reciters_data[0]["name_en"] if reciters_data else "Ali Al Hudhaify"
    hero_surah_ar = reciters_data[0]["surah_name_ar"] if reciters_data else "سورة يوسف"
    hero_surah_en = reciters_data[0]["surah_name_en"] if reciters_data else "Surah Yusuf"

    # Tafsir only for Arabic; Urdu/Farsi and all others get translation card
    show_tafsir = lang == "ar"
    if show_tafsir:
        tafsir_samples = _get_tafsir_samples(5)
        translation_samples = []
    else:
        tafsir_samples = []
        translation_samples = _get_translation_samples(lang, 5)

    context = {
        "visitors_count": visitors.value if visitors else 0,
        "qurra": get_home_qurra("hafs"),
        "tafasir": get_home_tafasir(),
        "mushaf_list": get_home_mushaf_list(),
        "home_lang": lang,
        "is_arabic": is_arabic,
        "show_tafsir": show_tafsir,
        "translation_audio_folder": TRANSLATION_AUDIO_FOLDERS.get(lang, ""),
        "reciters_json": json.dumps(reciters_data, ensure_ascii=False),
        "tafsir_samples_json": json.dumps(tafsir_samples, ensure_ascii=False),
        "translation_samples_json": json.dumps(translation_samples, ensure_ascii=False),
        "hero_reciter_ar": hero_reciter_ar,
        "hero_reciter_en": hero_reciter_en,
        "hero_surah_ar": hero_surah_ar,
        "hero_surah_en": hero_surah_en,
    }

    return render(request, "web/pages/home.html", context)


def about(request):
    return render(request, "web/pages/about.html")


def privacy_policy(request):
    return render(request, "web/pages/privacy_policy.html")


def translation(request, surah_number=None):
    current_language = _normalize_translation_language()

    surahs = list(Surah.objects.order_by("surah_number"))
    surah_by_number = {item.surah_number: item for item in surahs}
    total_pages = _get_total_quran_pages()

    selected_surah = None
    if surah_number is not None:
        selected_surah = surah_by_number.get(surah_number)

    requested_page = request.GET.get("page")
    if requested_page:
        try:
            current_page = int(requested_page)
        except (TypeError, ValueError):
            current_page = selected_surah.page_start if selected_surah else 1
    elif selected_surah:
        current_page = selected_surah.page_start
    else:
        current_page = 1

    if current_page < 1:
        current_page = 1
    if current_page > total_pages:
        current_page = total_pages

    if selected_surah is None:
        first_page_ayah = (
            Ayah.objects.filter(page_number=current_page)
            .order_by("surah_number", "ayah_number")
            .only("surah_number")
            .first()
        )
        if first_page_ayah:
            selected_surah = surah_by_number.get(first_page_ayah.surah_number)

    prev_page = current_page - 1 if current_page > 1 else None
    next_page = current_page + 1 if current_page < total_pages else None

    context = {
        "surahs": surahs,
        "selected_surah": selected_surah,
        "pages": list(range(1, total_pages + 1)),
        "current_page": current_page,
        "prev_page": prev_page,
        "next_page": next_page,
        "total_pages": total_pages,
        "current_translation_language": current_language,
        "is_translation_rtl": current_language in RTL_LANGUAGES,
        "translation_audio_folder": TRANSLATION_AUDIO_FOLDERS.get(current_language, ""),
        "has_text_translation": current_language != "ar",
        "is_ar_ui": current_language == "ar",
        "trans_audio_folders": TRANSLATION_AUDIO_FOLDERS,
        "mushaf_dimensions": get_all_mushaf_dimensions(),
    }

    return render(request, "web/pages/translation.html", context)


def translation_page_data(request):
    ui_language = _normalize_translation_language()
    if ui_language == "ar":
        lang_param = request.GET.get("lang", "en")
        current_language = lang_param if lang_param in TRANSLATION_AUDIO_FOLDERS else "en"
    else:
        current_language = ui_language
    total_pages = _get_total_quran_pages()
    surah_by_number = {
        item.surah_number: item
        for item in Surah.objects.order_by("surah_number")
    }

    def parse_page(value):
        try:
            page = int(value)
        except (TypeError, ValueError):
            return None
        if page < 1 or page > total_pages:
            return None
        return page

    right_page = parse_page(request.GET.get("right_page"))
    left_page = parse_page(request.GET.get("left_page"))

    return JsonResponse({
        "success": True,
        "language": current_language,
        "is_rtl": current_language in RTL_LANGUAGES,
        "right": _build_translation_page(right_page, current_language, surah_by_number) if right_page else None,
        "left": _build_translation_page(left_page, current_language, surah_by_number) if left_page else None,
    })
