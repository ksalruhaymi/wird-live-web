import re

from django.http import JsonResponse

from ..models import Ayah, TafsirBook, Tafsir


def _split_tafsir_text(raw_text: str):
    """
    تفصل النص إلى:
    - ayah_text: ما بين { }
    - tafsir_text: بقية النص
    """
    if not raw_text:
        return "", ""

    match = re.search(r"\{([^}]+)\}", raw_text)
    if match:
        ayah_text = match.group(1).strip()
        tafsir_text = raw_text.replace(match.group(0), "").strip()
    else:
        ayah_text = ""
        tafsir_text = raw_text.strip()

    return ayah_text, tafsir_text


def ayah_tafsir(request):
    """
    Ajax endpoint to return tafsir text for a single ayah.
    GET params: book_id, surah, ayah
    """
    book_id = request.GET.get("book_id")
    surah = request.GET.get("surah")
    ayah = request.GET.get("ayah")

    try:
        book_id = int(book_id)
        surah = int(surah)
        ayah = int(ayah)
    except (TypeError, ValueError):
        return JsonResponse(
            {"success": False, "error": "Invalid parameters."},
            status=400,
        )

    try:
        book = TafsirBook.objects.get(id=book_id, is_active=True)
    except TafsirBook.DoesNotExist:
        return JsonResponse(
            {"success": False, "error": "Tafsir book not found."},
            status=404,
        )

    tafsir = (
        Tafsir.objects.filter(book=book, surah_id=surah, ayah_number=ayah).first()
    )

    if not tafsir:
        return JsonResponse(
            {
                "success": False,
                "error": "Tafsir not found for this ayah.",
                "book_name": book.name,
                "surah": surah,
                "ayah": ayah,
            },
            status=404,
        )

    ayah_text, tafsir_text = _split_tafsir_text(tafsir.text or "")

    return JsonResponse(
        {
            "success": True,
            "book_id": book.id,
            "book_name": book.name,
            "surah": surah,
            "ayah": ayah,
            "ayah_text": ayah_text,
            "tafsir_text": tafsir_text,
        }
    )


def page_tafsir(request):
    """
    Return tafsir for the current right/left pages.
    GET params:
      - book_id: TafsirBook id
      - right_page: page number for the right side (optional)
      - left_page: page number for the left side (optional)
    """
    book_id = request.GET.get("book_id")
    right_page = request.GET.get("right_page")
    left_page = request.GET.get("left_page")

    # Validate book
    try:
        book_id_int = int(book_id)
        book = TafsirBook.objects.get(id=book_id_int, is_active=True)
    except (TypeError, ValueError, TafsirBook.DoesNotExist):
        return JsonResponse(
            {"success": False, "error": "Invalid or missing tafsir book."},
            status=400,
        )

    def build_page_tafsir(page_str):
       
        if not page_str:
            return {"page": None, "text": "", "items": []}

        try:
            page_num = int(page_str)
        except (TypeError, ValueError):
            return {"page": None, "text": "", "items": []}

        ayat = (
            Ayah.objects.filter(page_number=page_num)
            .order_by("surah_number", "ayah_number")
        )

        if not ayat.exists():
            return {"page": page_num, "text": "", "items": []}

        pieces = []
        items = []

        for a in ayat:
            t = (
                Tafsir.objects.filter(
                    book=book,
                    surah_id=a.surah_number,
                    ayah_number=a.ayah_number,
                ).first()
            )
            if not t:
                continue

            pieces.append(f"{a.surah_number}:{a.ayah_number} - {t.text}")

            ayah_text, tafsir_text = _split_tafsir_text(t.text or "")
            items.append(
                {
                    "surah": a.surah_number,
                    "ayah": a.ayah_number,
                    "ayah_key": f"{a.surah_number}:{a.ayah_number}",
                    "ayah_text": ayah_text,
                    "tafsir_text": tafsir_text,
                }
            )

        full_text = "\n\n".join(pieces) if pieces else ""
        return {"page": page_num, "text": full_text, "items": items}

    right_data = build_page_tafsir(right_page)
    left_data = build_page_tafsir(left_page)

    return JsonResponse(
        {
            "success": True,
            "book_id": book.id,
            "book_name": book.name,
            "right": right_data,
            "left": left_data,
        }
    )


def ayah_short_tafsir(request):
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

    book = (
        TafsirBook.objects.filter(is_active=True, name__icontains="السعدي")
        .order_by("sort_order", "number")
        .first()
    )

    if not book:
        return JsonResponse(
            {"success": False, "error": "Tafsir Al-Saadi not found."},
            status=404,
        )

    tafsir = Tafsir.objects.filter(
        book=book,
        surah_id=surah,
        ayah_number=ayah,
    ).first()

    if not tafsir:
        return JsonResponse(
            {"success": False, "error": "Tafsir not found for this ayah."},
            status=404,
        )

    ayah_text, tafsir_text = _split_tafsir_text(tafsir.text or "")

    return JsonResponse(
        {
            "success": True,
            "book_name": book.name,
            "surah": surah,
            "ayah": ayah,
            "ayah_text": ayah_text,
            "tafsir_text": tafsir_text,
        }
    )