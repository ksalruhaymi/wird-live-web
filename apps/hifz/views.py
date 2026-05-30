# apps/hifz/views.py

from django.shortcuts import render

from apps.quran.mushaf_config import MUSHAFS
from apps.quran.services.quran_service import build_quran_context
from .models import AyahThematicClassification
from apps.quran.views.quran_views import (
    apply_mushaf_context,
    build_audio_items,
    get_active_tafasir,
    get_qurra_for_mushaf,
    get_juzs_for_ui,
    get_spread_pages,
    get_surahs_for_ui,
    resolve_current_qari,
)


def build_hifz_thematic_ayah_map():
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
                "color_id": topic.color_id,
                "color_name_ar": topic.color_name_ar,
                "color_hex": topic.color_hex,
                "range": f"{item.surah_number}:{item.ayah_from}-{item.ayah_to}",
                "notes": item.notes,
            }

    return ayah_map


def home(request, page=1, mushaf="hafs"):
    request.GET = request.GET.copy()
    request.GET["page"] = str(page)
    request.GET["mushaf"] = mushaf

    context = build_quran_context(request)

    raw_page = page
    raw_page = apply_mushaf_context(request, context, raw_page, mushaf)

    if not context.get("mushafs"):
        context["mushafs"] = [
            {
                "key": key,
                "code": key,
                "slug": key,
                "label": cfg.get("title_key", key),
                "name": cfg.get("title_key", key),
                "title": cfg.get("title_key", key),
            }
            for key, cfg in MUSHAFS.items()
        ]

    filtered_qurra = get_qurra_for_mushaf(context["current_mushaf"])
    context["qurra"] = filtered_qurra

    current_qari = resolve_current_qari(filtered_qurra, request)
    context["current_qari"] = current_qari
    context["current_qari_folder"] = current_qari.code if current_qari else ""

    context["tafasir"] = get_active_tafasir()

    right_page, left_page = get_spread_pages(raw_page)
    context["right_page"] = right_page
    context["left_page"] = left_page

    context["audio_items"] = build_audio_items(context["current_mushaf"])

    surahs = get_surahs_for_ui()
    for surah in surahs:
        surah.start_page = surah.page_start
    context["surahs"] = surahs
    context["juzs"] = get_juzs_for_ui()

    context["raw_page"] = raw_page
    context["mode"] = "mushaf"
    context["is_hifz_mode"] = True
    context["hifz_thematic_ayahs"] = build_hifz_thematic_ayah_map()

    return render(request, "hifz/home.html", context)
