from django.http import JsonResponse

from ..models import Ayah


def search_ayahs(request):
    query = (request.GET.get("q") or "").strip()

    if not query:
        return JsonResponse([], safe=False)

    ayahs = (
        Ayah.objects.filter(text__icontains=query)
        .order_by("page_number", "surah_number", "ayah_number")[:50]
    )

    data = [
        {
            "id": ayah.id,
            "surah_id": ayah.surah_id,
            "surah_number": ayah.surah_number,
            "ayah_number": ayah.ayah_number,
            "page_number": ayah.page_number,
            "juz_number": ayah.juz_number,
            "text": ayah.text,
        }
        for ayah in ayahs
    ]

    return JsonResponse(data, safe=False)