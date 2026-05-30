from pathlib import Path

from django.conf import settings
from django.db.models import Q
from django.http import HttpResponseRedirect, JsonResponse

from apps.quran.models import (
    Ayah,
    AyahPosition,
    Qurra,
    Surah,
    Tafsir,
    TafsirBook,
)
from apps.quran.mushaf_config import DEFAULT_MUSHAF_KEY, MUSHAFS
from core.utils.media import media_url, remote_media_file_exists, uses_remote_media

from .auth import require_api_key


def resolve_mushaf_key(request):
    mushaf_key = (request.GET.get("mushaf") or DEFAULT_MUSHAF_KEY).strip().lower()
    if mushaf_key not in MUSHAFS:
        return DEFAULT_MUSHAF_KEY
    return mushaf_key


def _reader_dir_has_audio(reader_dir: Path) -> bool:
    """True إذا وُجد ملف MP3 واحد على الأقل داخل مجلد القارئ."""
    try:
        return next(reader_dir.rglob("*.mp3"), None) is not None
    except Exception:
        return False


def _normalize_mushaf_values(values) -> set[str]:
    if not values:
        return set()

    if isinstance(values, str):
        import json

        try:
            values = json.loads(values)
        except Exception:
            values = [values]

    if not isinstance(values, (list, tuple, set)):
        return set()

    return {str(value).strip().lower() for value in values if str(value).strip()}


def _remote_reader_has_audio(mushaf_key: str, reader_code: str) -> bool:
    reader_code = (reader_code or "").strip()
    mushaf_key = (mushaf_key or DEFAULT_MUSHAF_KEY).strip().lower()

    if not reader_code:
        return False

    sample_files = (
        f"audio/{mushaf_key}/{reader_code}/001/001001.mp3",
        f"audio/{mushaf_key}/{reader_code}/001/001002.mp3",
        f"audio/{mushaf_key}/{reader_code}/002/002001.mp3",
    )

    return any(remote_media_file_exists(path) for path in sample_files)


def _supported_mushafs_for_reader_code(reader_code: str) -> list[str]:
    """
    Return only the mushafs that actually support this reader.

    Local media mode keeps the old behavior by checking local folders.
    Remote media mode checks the configured SERVER_MEDIA_URL instead of returning
    every reader for every mushaf.
    """
    if not reader_code or not reader_code.strip():
        return []

    code = reader_code.strip()
    audio_root = Path(settings.MEDIA_ROOT) / "audio"
    out: list[str] = []

    for mushaf_key in MUSHAFS.keys():
        reader_dir = audio_root / mushaf_key / code
        if reader_dir.is_dir():
            out.append(mushaf_key)

    if out or not uses_remote_media():
        return sorted(out)

    q = Qurra.objects.filter(code__iexact=code).first()
    db_mushafs = _normalize_mushaf_values(getattr(q, "mushafs", None)) if q else set()
    if db_mushafs:
        return sorted(key for key in db_mushafs if key in MUSHAFS)

    for mushaf_key in MUSHAFS.keys():
        if _remote_reader_has_audio(mushaf_key, code):
            out.append(mushaf_key)

    return sorted(out)


def _qurra_to_api_dict(q) -> dict:
    """توحيد شكل الحقول مع عميل Flutter (QariModel)."""
    return {
        "id": q.id,
        "number": getattr(q, "number", None) or q.id,
        "name_ar": q.name_ar,
        "name_en": q.name_en,
        "fullname": getattr(q, "fullname", "") or q.name_ar,
        "code": q.code,
        "info": getattr(q, "info", "") or "",
        "image": q.image,
        "supported_mushafs": _supported_mushafs_for_reader_code(q.code),
    }


@require_api_key
def surah_list(request):
    surahs = Surah.objects.all().order_by("surah_number").values()
    return JsonResponse(list(surahs), safe=False)


@require_api_key
def surah_detail(request, surah_number):
    try:
        surah = Surah.objects.get(surah_number=surah_number)
        return JsonResponse(
            {
                "surah_number": surah.surah_number,
                "surah_name_ar": surah.surah_name_ar,
                "surah_name_en": surah.surah_name_en,
                "page_start": surah.page_start,
                "page_end": surah.page_end,
                "ayah_count": surah.ayah_count,
                "revelation_type": surah.revelation_type,
            }
        )
    except Surah.DoesNotExist:
        return JsonResponse({"error": "Surah not found"}, status=404)


@require_api_key
def surah_ayahs(request, surah_number):
    ayahs = Ayah.objects.filter(
        surah_number=surah_number
    ).order_by("ayah_number").values()
    return JsonResponse(list(ayahs), safe=False)


@require_api_key
def ayah_list(request):
    qs = Ayah.objects.all().order_by("surah_number", "ayah_number")

    surah = request.GET.get("surah")
    page = request.GET.get("page")
    juz = request.GET.get("juz")

    if surah:
        qs = qs.filter(surah_number=surah)
    if page:
        qs = qs.filter(page_number=page)
    if juz:
        qs = qs.filter(juz_number=juz)

    return JsonResponse(list(qs.values()), safe=False)


@require_api_key
def ayah_detail(request, pk):
    try:
        ayah = Ayah.objects.get(pk=pk)
        return JsonResponse(
            {
                "id": ayah.id,
                "surah_number": ayah.surah_number,
                "ayah_number": ayah.ayah_number,
                "page_number": ayah.page_number,
                "juz_number": ayah.juz_number,
                "text": ayah.text,
            }
        )
    except Ayah.DoesNotExist:
        return JsonResponse({"error": "Ayah not found"}, status=404)


@require_api_key
def page_detail(request, page_number):
    mushaf_key = resolve_mushaf_key(request)

    ayahs = Ayah.objects.filter(page_number=page_number).values()
    positions = AyahPosition.objects.filter(
        mushaf_key=mushaf_key,
        page_number=page_number,
    ).values()

    return JsonResponse(
        {
            "page_number": page_number,
            "mushaf_key": mushaf_key,
            "ayahs": list(ayahs),
            "positions": list(positions),
        }
    )


@require_api_key
def ayah_positions(request, surah_number, ayah_number):
    mushaf_key = resolve_mushaf_key(request)

    positions = AyahPosition.objects.filter(
        mushaf_key=mushaf_key,
        surah_number=surah_number,
        ayah_number=ayah_number
    ).values()

    return JsonResponse(list(positions), safe=False)


@require_api_key
def page_positions(request, page_number):
    mushaf_key = resolve_mushaf_key(request)

    positions = AyahPosition.objects.filter(
        mushaf_key=mushaf_key,
        page_number=page_number
    ).values(
        "id",
        "mushaf_key",
        "surah_number",
        "ayah_number",
        "page_number",
        "x",
        "y",
        "width",
        "height",
        "polygon",
    )

    return JsonResponse(list(positions), safe=False)


@require_api_key
def tafsir_book_list(request):
    books = TafsirBook.objects.filter(is_active=True).values()
    return JsonResponse(list(books), safe=False)


@require_api_key
def tafsir_book_detail(request, pk):
    try:
        book = TafsirBook.objects.get(pk=pk)
        return JsonResponse(
            {
                "id": book.id,
                "name": book.name,
                "lang": book.lang,
                "api": book.api,
                "author": book.author,
                "info": book.info,
            }
        )
    except TafsirBook.DoesNotExist:
        return JsonResponse({"error": "Book not found"}, status=404)


@require_api_key
def tafsir_by_book_surah_ayah(request, book_id, surah_number, ayah_number):
    tafsir = Tafsir.objects.filter(
        book_id=book_id,
        surah_id=surah_number,
        ayah_number=ayah_number,
    ).values().first()

    if not tafsir:
        return JsonResponse({"error": "Tafsir not found"}, status=404)

    return JsonResponse(tafsir)


@require_api_key
def tafsir_by_ayah_number(request, ayah_number):
    tafasir = Tafsir.objects.filter(ayah_number=ayah_number).values()
    return JsonResponse(list(tafasir), safe=False)


@require_api_key
def qurra_list(request):
    rows = [_qurra_to_api_dict(q) for q in Qurra.objects.all().order_by("pk")]
    return JsonResponse(rows, safe=False)


@require_api_key
def qurra_detail(request, pk):
    try:
        qari = Qurra.objects.get(pk=pk)
        return JsonResponse(_qurra_to_api_dict(qari))
    except Qurra.DoesNotExist:
        return JsonResponse({"error": "Qari not found"}, status=404)


@require_api_key
def search_ayahs(request):
    query = request.GET.get("query", "")
    qs = Ayah.objects.filter(text__icontains=query).values()
    return JsonResponse(list(qs), safe=False)


@require_api_key
def search_tafsir(request):
    query = request.GET.get("query", "")
    qs = Tafsir.objects.filter(text__icontains=query).values()
    return JsonResponse(list(qs), safe=False)


@require_api_key
def meta_config(request):
    return JsonResponse(
        {
            "default_mushaf": DEFAULT_MUSHAF_KEY,
            "available_mushafs": list(MUSHAFS.keys()),
            "total_pages": 604,
        }
    )


@require_api_key
def mushafs_catalog(request):
    """قائمة أكواد المصاحف المتوفرة (مثل تطبيق Flutter `MushafCatalogRemote`)."""
    keys = list(MUSHAFS.keys())
    return JsonResponse(
        {
            "mushafs": keys,
            "default": DEFAULT_MUSHAF_KEY,
            "detail": [
                {"code": code, **meta} for code, meta in MUSHAFS.items()
            ],
            "count": len(keys),
        }
    )


@require_api_key
def feature_flags(request):
    return JsonResponse(
        {
            "audio": True,
            "adhkar": True,
            "qurra": True,
            "readingPlan": True,
            "quranIndex": True,
            "quranPages": True,
            "tafsir": True,
            "search": True,
            "audioSource": "api",
            "tafsirSource": "sqlite",
            "qurraSource": "api",
            "qurraImageSource": "api",
            "mushafSource": "api"
        }
    )


def _synthesize_qari_dict_from_code(code: str, mushaf: str) -> dict:
    """يُنشئ كائن قارئ مبسطاً عند وجود مجلد للقارئ ولا يوجد له صف في Qurra."""
    label_parts = [p for p in code.replace("-", "_").split("_") if p]
    label = " ".join(p.capitalize() for p in label_parts) or code
    # معرف سالب ثابت مشتق من الكود لضمان عدم تصادمه مع id حقيقي وثبات قيمته بين الطلبات
    synth_id = -(abs(hash(code)) % 10_000_000) - 1
    return {
        "id": synth_id,
        "number": synth_id,
        "name_ar": label,
        "name_en": label,
        "fullname": label,
        "code": code,
        "info": "",
        "image": "",
        "supported_mushafs": [mushaf],
    }


# Mapping from Flutter locale codes to actual media/translation folder names.
# None = language defined but audio not yet available.
TRANSLATION_LANG_MAP: dict[str, str | None] = {
    # Flutter app locales
    "en": "english_rwwad",
    "ar": None,              # Arabic — coming soon
    "de": None,              # German — coming soon
    "es": None,              # Spanish — coming soon
    "hi": None,              # Hindi — coming soon
    "ur": None,              # Urdu — coming soon
    "fa": "persian_ih",
    "id": None,              # Indonesian — coming soon
    "fr": "french_rashid",
    "ja": None,              # Japanese — coming soon
    # Extra languages (audio available — add to Flutter when needed)
    "zh": "chinese_suliman",
    "pt": "portuguese_nasr",
    "tl": "tagalog_rwwad",
    "fil": "tagalog_rwwad",
    "as": "assamese_rafeeq",
    "az": "azeri_musayev",
    "nl": "dutch_center",
    "si": "sinhalese_mahir",
    "so": "somali_yacob",
    "vi": "vietnamese_rwwad",
}

# Human-readable names for the catalog response
_LANG_NAMES: dict[str, dict[str, str]] = {
    "en": {"name_ar": "الإنجليزية",   "name_en": "English"},
    "ar": {"name_ar": "العربية",       "name_en": "Arabic"},
    "de": {"name_ar": "الألمانية",     "name_en": "German"},
    "es": {"name_ar": "الإسبانية",     "name_en": "Spanish"},
    "hi": {"name_ar": "الهندية",       "name_en": "Hindi"},
    "ur": {"name_ar": "الأردية",       "name_en": "Urdu"},
    "fa": {"name_ar": "الفارسية",      "name_en": "Persian"},
    "id": {"name_ar": "الإندونيسية",   "name_en": "Indonesian"},
    "fr": {"name_ar": "الفرنسية",      "name_en": "French"},
    "ja": {"name_ar": "اليابانية",     "name_en": "Japanese"},
    "zh": {"name_ar": "الصينية",       "name_en": "Chinese"},
    "pt": {"name_ar": "البرتغالية",    "name_en": "Portuguese"},
    "tl": {"name_ar": "التاغالوغية",   "name_en": "Tagalog"},
    "fil": {"name_ar": "الفلبينية",     "name_en": "Filipino / Tagalog"},
    "as": {"name_ar": "الأسامية",      "name_en": "Assamese"},
    "az": {"name_ar": "الأذربيجانية",  "name_en": "Azerbaijani"},
    "nl": {"name_ar": "الهولندية",     "name_en": "Dutch"},
    "si": {"name_ar": "السنهالية",     "name_en": "Sinhala"},
    "so": {"name_ar": "الصومالية",     "name_en": "Somali"},
    "vi": {"name_ar": "الفيتنامية",    "name_en": "Vietnamese"},
}


def _resolve_translation_folder(lang_code: str) -> tuple[str | None, str | None]:
    """يُرجع (folder_name, error_message). error_message=None عند النجاح."""
    if lang_code not in TRANSLATION_LANG_MAP:
        return None, "Language code not supported"
    folder = TRANSLATION_LANG_MAP[lang_code]
    if folder is None:
        return None, "Translation audio not yet available for this language"
    return folder, None


@require_api_key
def translation_ayah_audio(request, lang_code, surah_number, ayah_number):
    """يُعيد توجيهاً لملف صوت الترجمة. lang_code = كود Flutter (en, fa, fr …)."""
    folder, error = _resolve_translation_folder(lang_code)
    if error:
        return JsonResponse({"error": error}, status=404)

    filename = f"{surah_number:03d}{ayah_number:03d}.mp3"
    api_key = request.GET.get("api_key") or request.headers.get("X-API-KEY", "")
    url = media_url(f"translations/{folder}/{surah_number:03d}/{filename}")
    if api_key:
        url = f"{url}?api_key={api_key}"
    return HttpResponseRedirect(url)


@require_api_key
def reciter_ayah_audio(request, mushaf_code, reciter_code, surah_number, ayah_number):
    """يُعيد توجيهاً لملف صوت القارئ."""
    filename = f"{surah_number:03d}{ayah_number:03d}.mp3"
    api_key = request.GET.get("api_key") or request.headers.get("X-API-KEY", "")
    url = media_url(f"audio/{mushaf_code}/{reciter_code}/{surah_number:03d}/{filename}")
    if api_key:
        url = f"{url}?api_key={api_key}"
    return HttpResponseRedirect(url)



def available_audio_readers(request):
    """قائمة القراء لمصحف معيَّن — تعتمد على وجود مجلد القارئ فقط افتراضياً.

    استعلامات:
    - `mushaf`: مفتاح المصحف (إجباري، مثل hafs/warsh).
    - `require_audio=1`: لاشتراط وجود ملف MP3 واحد على الأقل داخل مجلد القارئ.

    الاستجابة تتضمن `reader_codes` (للتوافق الخلفي) و`readers` (كائنات قارئ
    كاملة بنفس عقد QariModel في تطبيق Flutter)؛ بحيث لا يحتاج العميل لجلب
    `/qurra/` بشكل منفصل أو الاعتماد على قاعدة بيانات محلية.
    """
    mushaf = request.GET.get("mushaf", "").strip().lower()
    require_audio = request.GET.get("require_audio", "0").strip() in {"1", "true", "yes"}

    if not mushaf:
        return JsonResponse({"error": "mushaf is required"}, status=400)

    base_dir = Path(settings.MEDIA_ROOT) / "audio" / mushaf

    folders: list[str] = []
    if base_dir.exists() and base_dir.is_dir():
        for item in sorted(base_dir.iterdir(), key=lambda x: x.name.lower()):
            if not item.is_dir():
                continue
            if require_audio and not _reader_dir_has_audio(item):
                continue
            folders.append(item.name)

    # In local remote-media mode, the 36GB media folder may be absent.
    # Fall back to DB reciters so the API and Flutter can still work.
    if not folders and uses_remote_media():
        for q in Qurra.objects.filter(is_visible=True).order_by("code"):
            supported = _supported_mushafs_for_reader_code(q.code)
            if mushaf in supported:
                folders.append(q.code)

    # خَرِّط أكواد المجلدات على صفوف Qurra في قاعدة البيانات (مطابقة غير حساسة لحالة الأحرف).
    qurra_by_code = {q.code.strip().lower(): q for q in Qurra.objects.all()}

    readers: list[dict] = []
    for folder_code in folders:
        lc = folder_code.strip().lower()
        q = qurra_by_code.get(lc)
        if q is not None:
            data = _qurra_to_api_dict(q)
            # تأكيد أن مجلد المصحف الحالي ضمن المصاحف المدعومة
            supported = list(data.get("supported_mushafs") or [])
            if mushaf not in supported:
                supported.append(mushaf)
                supported.sort()
            data["supported_mushafs"] = supported
            # كود الـ folder حرفياً لأن مسارات MP3 تعتمد عليه كما هو
            data["code"] = folder_code
            readers.append(data)
        else:
            readers.append(_synthesize_qari_dict_from_code(folder_code, mushaf))

    return JsonResponse(
        {
            "mushaf": mushaf,
            "reader_codes": folders,
            "readers": readers,
            "count": len(folders),
        }
    )