from django.http import HttpRequest

from ..mushaf_config import (
    MUSHAFS,
    DEFAULT_MUSHAF_KEY,
    QURAN_START_IMAGE,
    QURAN_END_IMAGE,
)
from ..models import Surah


def get_surah_data():
    """
    Load surahs and page ranges from the database.
    Returns:
      surah_list: list of dicts {number, i18n_key, first_page}
      page_ranges: {surah_number: (first_page, last_page)}
      logical_first: first logical Quran page
      logical_last: last logical Quran page
    """
    surah_list = []
    page_ranges = {}

    qs = (
        Surah.objects
        .order_by("surah_number")
        .values("surah_number", "page_start", "page_end")
    )

    if not qs:
        return surah_list, page_ranges, QURAN_START_IMAGE, QURAN_END_IMAGE

    local_first_pages = []
    local_last_pages = []

    for row in qs:
        num = int(row["surah_number"] or 0)
        if num == 0:
            continue

        first_page = int(row.get("page_start") or QURAN_START_IMAGE)
        last_page = int(row.get("page_end") or first_page)

        surah_list.append({
            "number": num,
            "i18n_key": f"surah_{num}",
            "first_page": first_page,
        })

        page_ranges[num] = (first_page, last_page)
        local_first_pages.append(first_page)
        local_last_pages.append(last_page)

    logical_first = min(local_first_pages) if local_first_pages else QURAN_START_IMAGE
    logical_last = max(local_last_pages) if local_last_pages else QURAN_END_IMAGE

    return surah_list, page_ranges, logical_first, logical_last


def get_current_page(request: HttpRequest, logical_first: int, logical_last: int):
    """
    Reads ?page= from query string and clamps it between logical_first and logical_last.
    Returns current_page (int).
    """
    page_str = request.GET.get("page")
    try:
        current_page = int(page_str) if page_str else logical_first
    except (ValueError, TypeError):
        current_page = logical_first

    if current_page < logical_first:
        current_page = logical_first
    if current_page > logical_last:
        current_page = logical_last

    return current_page


def get_mushaf(request: HttpRequest):
    """
    Reads ?mushaf= from query string and returns (mushaf_key, mushaf_config).
    Falls back to DEFAULT_MUSHAF_KEY if invalid.
    """
    mushaf_key = request.GET.get("mushaf", DEFAULT_MUSHAF_KEY)
    if mushaf_key not in MUSHAFS:
        mushaf_key = DEFAULT_MUSHAF_KEY

    mushaf = MUSHAFS[mushaf_key]
    return mushaf_key, mushaf


def find_surah_by_page(page_ranges, surah_list, page: int):
    """
    Using page_ranges and surah_list, find which surah contains the given page.
    Returns the surah dict or None.
    """
    for num, (start, end) in page_ranges.items():
        if start <= page <= end:
            for s in surah_list:
                if s["number"] == num:
                    return s
    return None


def build_quran_context(request: HttpRequest):
    """
    Build the full context dictionary for the Quran view.
    """
    surah_list, page_ranges, logical_first, logical_last = get_surah_data()

    mushaf_key, mushaf = get_mushaf(request)
    image_prefix = mushaf.get("image_prefix", "")
    page_offset = mushaf.get("page_offset", 0)

    pages = list(range(logical_first, logical_last + 1))
    current_page = get_current_page(request, logical_first, logical_last)

    try:
        current_index = pages.index(current_page)
    except ValueError:
        current_index = 0

    physical_page = current_page + page_offset

    surah_obj = find_surah_by_page(page_ranges, surah_list, current_page)
    current_surah_number = surah_obj["number"] if surah_obj else None
    current_surah_key = surah_obj["i18n_key"] if surah_obj else None

    mushaf_list = [
        {
            "key": key,
            "title_key": cfg["title_key"],
        }
        for key, cfg in MUSHAFS.items()
    ]

    context = {
        "surahs": surah_list,
        "current_surah": current_surah_number,
        "current_surah_key": current_surah_key,
        "pages": pages,
        "current_page": current_page,
        "current_index": current_index,
        "mushaf_key": mushaf_key,
        "mushaf": mushaf,
        "mushaf_image_prefix": image_prefix,
        "page_offset": page_offset,
        "physical_page": physical_page,
        "mushaf_list": mushaf_list,
    }

    return context