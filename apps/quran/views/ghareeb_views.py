from django.http import JsonResponse

from ..models import AyahWordMeaning


def ayah_word_meanings(request):
    surah = request.GET.get("surah")
    ayah = request.GET.get("ayah")

    try:
        surah = int(surah)
        ayah = int(ayah)
    except (TypeError, ValueError):
        return JsonResponse(
            {"success": False, "error": "Invalid parameters."},
            status=400,
        )

    items = list(
        AyahWordMeaning.objects.filter(
            surah_number=surah,
            ayah_number=ayah,
        )
        .order_by("sort_order", "id")
        .values("word", "word_plain", "meaning", "sort_order")
    )

    return JsonResponse(
        {
            "success": True,
            "surah": surah,
            "ayah": ayah,
            "items": items,
        }
    )