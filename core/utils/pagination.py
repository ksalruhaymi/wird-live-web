from urllib.parse import quote

from django.core.paginator import Paginator


def build_pagination_query_string(**params: str) -> str:
    """
    Build a query-string prefix for pagination links.
    Skips empty values and common "all" filter sentinels.
    Returns a trailing "&" when non-empty (ready to append page=N).
    """
    skip_all_for = {"status", "type", "demo", "active", "target"}
    parts: list[str] = []
    for key, value in params.items():
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        if key in skip_all_for and text == "all":
            continue
        parts.append(f"{quote(key)}={quote(text)}")
    return "&".join(parts) + ("&" if parts else "")


def _sequence_total(items) -> int:
    if isinstance(items, (list, tuple)):
        return len(items)
    return items.count()


def paginate_with_smart_pages(
    request,
    queryset,
    edge_count: int = 2,
    around_current: int = 2,
    default_per_page: str = "5",
    per_page_param_name: str = "per_page",
    page_param_name: str = "page",
):
    """
    Full pagination helper:
    - Reads per_page from request.GET[per_page_param_name] or uses default_per_page
    - Supports "all"
    - Builds Paginator and page_obj
    - Builds smart pages list (with ellipsis)

    Returns:
        page_obj,
        smart_pages (list[int | None]),
        normalized_per_page (str),
        total_count (int)
    """
    total = _sequence_total(queryset)

    # Read per_page from request, but logic is centralized here
    per_page_param = request.GET.get(per_page_param_name, default_per_page)

    if per_page_param == "all":
        per_page = total or 1
    else:
        try:
            per_page = int(per_page_param)
        except (TypeError, ValueError):
            per_page = int(default_per_page)
            per_page_param = default_per_page

    page_param = request.GET.get(page_param_name)

    paginator = Paginator(queryset, per_page)
    page_obj = paginator.get_page(page_param)

    smart_pages = _build_smart_pages(page_obj, edge_count, around_current)

    return page_obj, smart_pages, per_page_param, total


def get_smart_pagination(page_obj, edge_count: int = 2, around_current: int = 2):
    return _build_smart_pages(page_obj, edge_count, around_current)


def _build_smart_pages(page_obj, edge_count: int = 2, around_current: int = 2):
    total = page_obj.paginator.num_pages
    current = page_obj.number

    if total <= (edge_count * 2) + (around_current * 2) + 2:
        return list(range(1, total + 1))

    pages = set()

    # First pages
    for i in range(1, edge_count + 1):
        if 1 <= i <= total:
            pages.add(i)

    # Last pages
    for i in range(total - edge_count + 1, total + 1):
        if 1 <= i <= total:
            pages.add(i)

    # Around current
    for i in range(current - around_current, current + around_current + 1):
        if 1 <= i <= total:
            pages.add(i)

    pages = sorted(pages)

    result = []
    prev = None
    for p in pages:
        if prev is not None and p - prev > 1:
            result.append(None)
        result.append(p)
        prev = p

    return result
