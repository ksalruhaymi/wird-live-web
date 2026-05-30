# apps/quran/views/quran_views.py

import json
from django.db.models import Min
from django.urls import reverse

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.utils.translation import get_language
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST

from ..models import Ayah, AyahPosition, Qurra, TafsirBook, Surah, KhatmaProgress
from ..quran_divisions import wird_page_range, total_wirds_for
from ..services.quran_service import build_quran_context
from ..services.audio_catalog import qari_objects_for_mushaf
from ..mushaf_config import (
    MUSHAFS,
    DEFAULT_MUSHAF_KEY,
    TOTAL_PAGES,
    get_all_mushaf_dimensions,
)


def build_quran_thematic_ayah_map():
    from apps.hifz.models import AyahThematicClassification

    items = (
        AyahThematicClassification.objects.select_related("topic")
        .order_by("surah_number", "ayah_from", "ayah_to", "topic__topic_id")
    )

    ayah_map = {}
    for item in items:
        topic = item.topic
        for ayah_number in range(item.ayah_from, item.ayah_to + 1):
            key = f"{item.surah_number}:{ayah_number}"
            ayah_map[key] = {
                "topic_id": topic.topic_id,
                "topic_ar": topic.topic_ar,
                "topic_text": item.topic_text,
                "color_id": topic.color_id,
                "color_name_ar": topic.color_name_ar,
                "color_hex": topic.color_hex,
                "range": f"{item.surah_number}:{item.ayah_from}-{item.ayah_to}",
            }

    return ayah_map


def handle_legacy_redirects(request, page=None, surah=None, qari=None, forced_mode=None):
    if page is not None or surah is not None or qari is not None or forced_mode is not None:
        return None

    mushaf = request.GET.get("mushaf")

    if "page" in request.GET:
        page_value = request.GET.get("page")
        if mushaf:
            return redirect(f"/quran/{mushaf}/page/{page_value}/", permanent=True)
        return redirect(f"/quran/page/{page_value}/", permanent=True)

    if "surah" in request.GET:
        surah_value = request.GET.get("surah")
        if mushaf:
            return redirect(f"/quran/{mushaf}/surah/{surah_value}/", permanent=True)
        return redirect(f"/quran/surah/{surah_value}/", permanent=True)

    if "qari" in request.GET:
        qari_value = request.GET.get("qari")
        if mushaf:
            return redirect(f"/quran/{mushaf}/quraa/{qari_value}/", permanent=True)
        return redirect(f"/quran/quraa/{qari_value}/", permanent=True)

    if "tafsir_page" in request.GET:
        page_value = request.GET.get("tafsir_page")
        if mushaf:
            return redirect(f"/quran/{mushaf}/tafsir/{page_value}/", permanent=True)
        return redirect(f"/quran/tafsir/{page_value}/", permanent=True)

    return None


def resolve_raw_page(page=None, surah=None):
    if surah is not None:
        first_ayah = (
            Ayah.objects.filter(surah_number=surah)
            .order_by("ayah_number")
            .first()
        )
        raw_page = first_ayah.page_number if first_ayah else 1
    else:
        raw_page = page or 1

    if raw_page < 1:
        raw_page = 1

    return raw_page


def build_base_context(request, raw_page, mushaf=None):
    request.GET = request.GET.copy()
    request.GET["page"] = str(raw_page)

    if mushaf:
        request.GET["mushaf"] = mushaf

    return build_quran_context(request)


def resolve_mode(request, forced_mode=None):
    mode = forced_mode or request.GET.get("mode", "mushaf")
    if mode not in ("mushaf", "tafsir"):
        mode = "mushaf"
    return mode


def apply_mushaf_context(request, context, raw_page, mushaf=None):
    mushaf_key = (
        request.GET.get("mushaf")
        or mushaf
        or context.get("current_mushaf")
        or DEFAULT_MUSHAF_KEY
    )

    if mushaf_key not in MUSHAFS:
        mushaf_key = DEFAULT_MUSHAF_KEY

    mushaf_cfg = MUSHAFS[mushaf_key]
    dims = get_all_mushaf_dimensions()

    context["current_mushaf"] = mushaf_key
    context["current_mushaf_label"] = mushaf_cfg["title_key"]
    context["current_mushaf_prefix"] = mushaf_cfg["image_prefix"]
    context["total_pages"] = mushaf_cfg.get("total_pages", TOTAL_PAGES)

    context["mushaf_dimensions"] = dims

    # Backward compatibility for current templates and JavaScript
    context["mushaf_page_width"] = dims["normal"]["page_width"]
    context["mushaf_page_height"] = dims["normal"]["page_height"]
    context["mushaf_min_width"] = dims["normal"]["min_width"]
    context["mushaf_max_width"] = dims["normal"]["max_width"]
    context["mushaf_min_height"] = dims["normal"]["min_height"]
    context["mushaf_max_height"] = dims["normal"]["max_height"]

    context["mushaf_fullscreen_width_vw"] = dims["fullscreen"]["width_vw"]
    context["mushaf_fullscreen_height_ratio"] = dims["fullscreen"]["height_ratio"]
    context["mushaf_fullscreen_max_width_vw"] = dims["fullscreen"]["max_width_vw"]
    context["mushaf_fullscreen_max_height_vh"] = dims["fullscreen"]["max_height_vh"]

    if raw_page > context["total_pages"]:
        raw_page = context["total_pages"]

    if raw_page < 1:
        raw_page = 1

    context["raw_page"] = raw_page
    context["current_page"] = raw_page

    return raw_page


def get_qurra_for_mushaf(mushaf_key):
    return qari_objects_for_mushaf(mushaf_key)


def resolve_current_qari(filtered_qurra, request, qari=None):
    qari_code = qari or request.GET.get("qari")

    if not qari_code:
        mushaf_key = request.GET.get("mushaf") or DEFAULT_MUSHAF_KEY
        cookie_key = f"quran_selected_qari__{mushaf_key}"
        qari_code = request.COOKIES.get(cookie_key)

    current_qari = None

    if filtered_qurra:
        if qari_code:
            for q in filtered_qurra:
                if q.code == qari_code:
                    current_qari = q
                    break

        if current_qari is None:
            current_qari = filtered_qurra[0]

    return current_qari


def get_active_tafasir():
    return TafsirBook.objects.filter(is_active=True).order_by(
        "sort_order", "number"
    )


def get_spread_pages(raw_page):
    left_page = raw_page
    right_page = raw_page - 1 if raw_page > 1 else None
    return right_page, left_page


def build_audio_items(mushaf_key):
    mushaf_key = (mushaf_key or DEFAULT_MUSHAF_KEY).strip().lower()

    if mushaf_key not in MUSHAFS:
        mushaf_key = DEFAULT_MUSHAF_KEY

    positions = (
        AyahPosition.objects.filter(
            mushaf_key=mushaf_key,
            ayah_number__isnull=False,
        )
        .values("surah_number", "ayah_number", "page_number")
        .distinct()
        .order_by("page_number", "surah_number", "ayah_number")
    )

    audio_items = []
    for pos in positions:
        audio_items.append(
            {
                "surah_number": pos["surah_number"],
                "ayah_number": pos["ayah_number"],
                "page_number": pos["page_number"],
                "is_basmala": False,
            }
        )

    return audio_items


def get_surahs_for_ui():
    surahs = list(Surah.objects.all().order_by("surah_number"))

    for surah in surahs:
        surah.i18n_key = f"surah_{surah.surah_number}"
        surah.number = surah.surah_number
        surah.first_page = surah.page_start

    return surahs


def get_juzs_for_ui():
    standard_juz_first_pages = {
        1: 1,
        2: 22,
        3: 42,
        4: 62,
        5: 82,
        6: 102,
        7: 122,
        8: 142,
        9: 162,
        10: 182,
        11: 201,
        12: 222,
        13: 242,
        14: 262,
        15: 282,
        16: 302,
        17: 322,
        18: 342,
        19: 362,
        20: 382,
        21: 402,
        22: 422,
        23: 442,
        24: 462,
        25: 482,
        26: 502,
        27: 522,
        28: 542,
        29: 562,
        30: 582,
    }
    arabic_ordinals = {
        1: "الأول",
        2: "الثاني",
        3: "الثالث",
        4: "الرابع",
        5: "الخامس",
        6: "السادس",
        7: "السابع",
        8: "الثامن",
        9: "التاسع",
        10: "العاشر",
        11: "الحادي عشر",
        12: "الثاني عشر",
        13: "الثالث عشر",
        14: "الرابع عشر",
        15: "الخامس عشر",
        16: "السادس عشر",
        17: "السابع عشر",
        18: "الثامن عشر",
        19: "التاسع عشر",
        20: "العشرون",
        21: "الحادي والعشرون",
        22: "الثاني والعشرون",
        23: "الثالث والعشرون",
        24: "الرابع والعشرون",
        25: "الخامس والعشرون",
        26: "السادس والعشرون",
        27: "السابع والعشرون",
        28: "الثامن والعشرون",
        29: "التاسع والعشرون",
        30: "الثلاثون",
    }

    first_pages_by_juz = {
        item["juz_number"]: item["first_page"]
        for item in (
            Ayah.objects
            .filter(juz_number__gte=1, juz_number__lte=30)
            .values("juz_number")
            .annotate(first_page=Min("page_number"))
        )
        if item["first_page"]
    }

    return [
        {
            "number": juz_number,
            "label": arabic_ordinals[juz_number],
            "first_page": first_pages_by_juz.get(
                juz_number,
                standard_juz_first_pages[juz_number],
            ),
            "search_terms": f"الجزء {arabic_ordinals[juz_number]} جزء {juz_number} {juz_number}",
        }
        for juz_number in range(1, 31)
    ]


def _normalize_polygon(poly):
    if isinstance(poly, str):
        try:
            poly = json.loads(poly)
        except json.JSONDecodeError:
            poly = []

    if not isinstance(poly, list):
        return []

    normalized = []
    for item in poly:
        if not isinstance(item, dict):
            continue

        try:
            x = float(item.get("x"))
            y = float(item.get("y"))
            width = float(item.get("width"))
            height = float(item.get("height"))
        except (TypeError, ValueError):
            continue

        normalized.append(
            {
                "x": x,
                "y": y,
                "width": width,
                "height": height,
            }
        )

    return normalized


def serialize_page_positions(page_number, mushaf_key=None):
    mushaf_key = (mushaf_key or DEFAULT_MUSHAF_KEY).strip().lower()

    if mushaf_key not in MUSHAFS:
        mushaf_key = DEFAULT_MUSHAF_KEY

    positions = (
        AyahPosition.objects.filter(
            mushaf_key=mushaf_key,
            page_number=page_number,
            ayah_number__isnull=False,
        )
        .order_by("surah_number", "ayah_number")
    )

    data = []
    for pos in positions:
        item = {
            "id": pos.id,
            "surah_number": pos.surah_number,
            "ayah_number": pos.ayah_number,
            "page_number": pos.page_number,
            "x": float(pos.x),
            "y": float(pos.y),
            "width": float(pos.width),
            "height": float(pos.height),
            "polygon": _normalize_polygon(pos.polygon),
            "is_basmala": False,
        }

        data.append(item)

    return data


def page_positions_json(request, page):
    mushaf_key = request.GET.get("mushaf", DEFAULT_MUSHAF_KEY)
    return JsonResponse(
        serialize_page_positions(page, mushaf_key=mushaf_key),
        safe=False,
    )


def get_last_page_from_cookie(request, mushaf_key):
    cookie_key = f"quran_last_page__{mushaf_key}"
    value = request.COOKIES.get(cookie_key)

    try:
        page = int(value)
    except (TypeError, ValueError):
        return None

    if page < 1:
        return None

    max_pages = MUSHAFS.get(mushaf_key, {}).get("total_pages", TOTAL_PAGES)
    if page > max_pages:
        return None

    return page


def quran(request, page=1, surah=None, qari=None, mushaf="hafs", forced_mode=None):
    redirect_response = handle_legacy_redirects(
        request,
        page=page,
        surah=surah,
        qari=qari,
        forced_mode=forced_mode,
    )
    mushaf_key = mushaf or request.GET.get("mushaf") or DEFAULT_MUSHAF_KEY

    if mushaf_key not in MUSHAFS:
        mushaf_key = DEFAULT_MUSHAF_KEY

    is_base_entry = (
        surah is None
        and qari is None
        and forced_mode is None
        and page == 1
        and request.path.rstrip("/") in {"/quran", f"/quran/{mushaf_key}"}
    )

    if is_base_entry:
        last_page = get_last_page_from_cookie(request, mushaf_key)
        if last_page and last_page != 1:
            return redirect(f"/quran/{mushaf_key}/page/{last_page}/")
    if redirect_response:
        return redirect_response

    raw_page = resolve_raw_page(page=page, surah=surah)

    context = build_base_context(request, raw_page, mushaf)
    context["mode"] = resolve_mode(request, forced_mode)

    raw_page = apply_mushaf_context(request, context, raw_page, mushaf)

    filtered_qurra = get_qurra_for_mushaf(context["current_mushaf"])
    context["qurra"] = filtered_qurra

    current_qari = resolve_current_qari(filtered_qurra, request, qari=qari)
    if current_qari:
        context["current_qari"] = current_qari
        context["current_qari_folder"] = current_qari.code
    else:
        context["current_qari"] = None
        context["current_qari_folder"] = ""

    context["tafasir"] = get_active_tafasir()

    right_page, left_page = get_spread_pages(raw_page)
    context["right_page"] = right_page
    context["left_page"] = left_page

    context["audio_items"] = build_audio_items(context["current_mushaf"])
    context["surahs"] = get_surahs_for_ui()
    context["juzs"] = get_juzs_for_ui()
    context["daily_reading"] = build_khatma_context_for_user(request.user)
    context["quran_thematic_ayahs"] = build_quran_thematic_ayah_map()

    return render(request, "quran/home.html", context)


def get_surah_display_name(surah_obj):
    lang = get_language()
    if not surah_obj:
        return ""
    if lang == "en" and surah_obj.surah_name_en:
        return surah_obj.surah_name_en
    return surah_obj.surah_name_ar


def get_or_create_khatma_progress(user):
    if not user.is_authenticated:
        return None
    progress, _ = KhatmaProgress.objects.get_or_create(user=user)
    return progress


def get_page_surah_ayah_bounds(start_page, end_page):
    start_ayah = (
        Ayah.objects.filter(page_number=start_page)
        .order_by("surah_number", "ayah_number")
        .first()
    )
    end_ayah = (
        Ayah.objects.filter(page_number=end_page)
        .order_by("-surah_number", "-ayah_number")
        .first()
    )

    return start_ayah, end_ayah


def apply_wird_bounds_to_progress(progress, start_page, end_page, wird_number=None):
    start_ayah, end_ayah = get_page_surah_ayah_bounds(start_page, end_page)

    progress.current_wird_start_page = start_page
    progress.current_wird_end_page = end_page
    progress.current_page = start_page

    if wird_number is not None:
        progress.current_wird_number = wird_number

    if start_ayah:
        progress.start_surah_number = start_ayah.surah_number
        progress.start_ayah_number = start_ayah.ayah_number

    if end_ayah:
        progress.end_surah_number = end_ayah.surah_number
        progress.end_ayah_number = end_ayah.ayah_number


def build_khatma_context_for_user(user):
    default_data = {
        "is_active": False,
        "khatma_count": 0,
        "current_wird_number": 1,
        "current_khatma_percent": 0,
        "wird_progress_percent": 0,
        "wird_status": KhatmaProgress.WIRD_NOT_STARTED,
        "tracking_mode": KhatmaProgress.TRACKING_AUTO,
        "daily_amount_type": "juz",
        "start_surah_name": "",
        "start_ayah_number": 1,
        "end_surah_name": "",
        "end_ayah_number": 1,
        "start_page": 1,
        "end_page": 20,
        "current_page": 1,
        "duration_days": 30,
        "remaining_wirds": 29,
        "total_wirds": 30,
        "continue_url": "",
        "current_ayah_text": "",
        "current_juz_number": 1,
    }

    if not user.is_authenticated:
        return default_data

    progress = get_or_create_khatma_progress(user)

    start_surah = Surah.objects.filter(surah_number=progress.start_surah_number).first()
    end_surah   = Surah.objects.filter(surah_number=progress.end_surah_number).first()
    start_ayah  = Ayah.objects.filter(
        surah_number=progress.start_surah_number,
        ayah_number=progress.start_ayah_number,
    ).first()

    current_mushaf = getattr(user, "current_mushaf", None) or "hafs"
    continue_url = reverse(
        "quran:quran_mushaf_page",
        args=[current_mushaf, progress.current_page],
    ) + (
        f"?resume_page={progress.current_page}"
        f"&surah={progress.start_surah_number}"
        f"&ayah={progress.start_ayah_number}"
    )

    default_data.update({
        "is_active":              progress.is_active,
        "khatma_count":           progress.khatma_count,
        "current_wird_number":    progress.current_wird_number,
        "current_khatma_percent": progress.current_khatma_percent,
        "wird_progress_percent":  progress.wird_progress_percent,
        "wird_status":            progress.wird_status,
        "tracking_mode":          progress.tracking_mode,
        "daily_amount_type":      progress.daily_amount_type,
        "start_surah_name":       get_surah_display_name(start_surah),
        "start_ayah_number":      progress.start_ayah_number,
        "end_surah_name":         get_surah_display_name(end_surah),
        "end_ayah_number":        progress.end_ayah_number,
        "start_page":             progress.current_wird_start_page,
        "end_page":               progress.current_wird_end_page,
        "current_page":           progress.current_page,
        "duration_days":          progress.duration_days,
        "remaining_wirds":        max(progress.total_wirds - progress.current_wird_number, 0),
        "total_wirds":            progress.total_wirds,
        "continue_url":           continue_url,
        "current_ayah_text":      getattr(start_ayah, "text", "") or "",
        "current_juz_number":     getattr(start_ayah, "juz_number", 1) or 1,
    })

    return default_data


@require_POST
@login_required
def start_khatma(request):
    progress = get_or_create_khatma_progress(request.user)

    try:
        data = json.loads(request.body.decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)

    duration_days     = int(data.get("duration_days", 30))
    daily_amount_type = data.get("daily_amount_type", "juz")
    tracking_mode     = data.get("tracking_mode", KhatmaProgress.TRACKING_MANUAL)

    duration_days = max(3, min(240, duration_days))

    from ..quran_divisions import AMOUNT_RUB3_UNITS
    if daily_amount_type not in AMOUNT_RUB3_UNITS:
        daily_amount_type = KhatmaProgress.amount_label_for_days(duration_days)

    if tracking_mode not in {KhatmaProgress.TRACKING_AUTO, KhatmaProgress.TRACKING_MANUAL}:
        tracking_mode = KhatmaProgress.TRACKING_MANUAL

    start_page, end_page = wird_page_range(1, daily_amount_type)

    progress.is_active           = True
    progress.start_mode          = KhatmaProgress.START_FROM_BEGINNING
    progress.duration_days       = duration_days
    progress.daily_amount_type   = daily_amount_type
    progress.tracking_mode       = tracking_mode
    progress.wird_status         = KhatmaProgress.WIRD_NOT_STARTED
    progress.current_wird_number = 1
    progress.total_wirds         = total_wirds_for(daily_amount_type)

    apply_wird_bounds_to_progress(progress, start_page=start_page, end_page=end_page, wird_number=1)
    progress.save()

    return JsonResponse({
        "ok": True,
        "message": "started",
        "daily_reading": build_khatma_context_for_user(request.user),
    })


@require_POST
@login_required
def complete_current_wird(request):
    progress = get_or_create_khatma_progress(request.user)

    if not progress.is_active:
        return JsonResponse({"ok": False, "error": "no_active_khatma"}, status=400)

    if progress.current_wird_number >= progress.total_wirds:
        reset_start, reset_end = wird_page_range(1, progress.daily_amount_type)
        progress.khatma_count        += 1
        progress.is_active            = False
        progress.wird_status          = KhatmaProgress.WIRD_NOT_STARTED
        progress.current_wird_number  = 1
        apply_wird_bounds_to_progress(progress, reset_start, reset_end, wird_number=1)
        progress.save()

        return JsonResponse({
            "ok": True,
            "finished_khatma": True,
            "khatma_count": progress.khatma_count,
            "daily_reading": build_khatma_context_for_user(request.user),
        })

    next_wird_number        = progress.current_wird_number + 1
    next_start, next_end    = wird_page_range(next_wird_number, progress.daily_amount_type)

    apply_wird_bounds_to_progress(progress, next_start, next_end, wird_number=next_wird_number)
    progress.current_wird_number = next_wird_number
    progress.current_page        = next_start
    progress.wird_status         = KhatmaProgress.WIRD_NOT_STARTED
    progress.save()

    return JsonResponse({
        "ok": True,
        "finished_khatma": False,
        "khatma_count": progress.khatma_count,
        "daily_reading": build_khatma_context_for_user(request.user),
    })


@require_POST
@login_required
def update_khatma_progress(request):
    progress = get_or_create_khatma_progress(request.user)

    if not progress.is_active:
        return JsonResponse({"ok": True, "current_page": progress.current_page})

    try:
        data = json.loads(request.body.decode("utf-8"))
        current_page = int(data.get("current_page"))
    except (ValueError, TypeError, json.JSONDecodeError):
        return JsonResponse({"ok": False}, status=400)

    # Clamp to current wird range
    current_page = max(current_page, progress.current_wird_start_page)
    current_page = min(current_page, progress.current_wird_end_page)

    update_fields = ["current_page", "updated_at"]

    # Auto-tracking: advance wird_status based on page position
    if progress.tracking_mode == KhatmaProgress.TRACKING_AUTO:
        if (
            progress.wird_status == KhatmaProgress.WIRD_NOT_STARTED
            and current_page >= progress.current_wird_start_page
        ):
            progress.wird_status = KhatmaProgress.WIRD_IN_PROGRESS
            update_fields.append("wird_status")

        if (
            current_page >= progress.current_wird_end_page
            and progress.wird_status != KhatmaProgress.WIRD_COMPLETED
        ):
            progress.wird_status = KhatmaProgress.WIRD_COMPLETED
            update_fields.append("wird_status")

    progress.current_page = current_page
    progress.save(update_fields=list(dict.fromkeys(update_fields)))

    return JsonResponse({
        "ok": True,
        "current_page": progress.current_page,
        "wird_status": progress.wird_status,
        "wird_progress_percent": progress.wird_progress_percent,
    })


@require_POST
@login_required
def toggle_tracking_mode(request):
    progress = get_or_create_khatma_progress(request.user)
    if not progress:
        return JsonResponse({"ok": False, "error": "no_progress"}, status=400)

    progress.tracking_mode = (
        KhatmaProgress.TRACKING_MANUAL
        if progress.tracking_mode == KhatmaProgress.TRACKING_AUTO
        else KhatmaProgress.TRACKING_AUTO
    )
    progress.save(update_fields=["tracking_mode", "updated_at"])

    return JsonResponse({
        "ok": True,
        "tracking_mode": progress.tracking_mode,
    })
