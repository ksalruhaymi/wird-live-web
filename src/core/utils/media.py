from functools import lru_cache
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from django.conf import settings


def media_url(path: str = "") -> str:
    """Build a media URL from the active MEDIA_URL setting."""
    base = str(settings.MEDIA_URL)
    clean_path = str(path or "").lstrip("/")
    return urljoin(base, clean_path)


def uses_remote_media() -> bool:
    return bool(getattr(settings, "MEDIA_USES_REMOTE_SERVER", False))


@lru_cache(maxsize=4096)
def remote_media_file_exists(path: str) -> bool:
    """
    Check whether a media file exists on the configured remote MEDIA_URL.

    This is used only in local development when MEDIA_SOURCE=server, so the
    local machine does not need the heavy media/audio folder. The result is
    cached in-process to avoid repeated network checks while browsing pages.
    """
    if not uses_remote_media():
        return False

    clean_path = str(path or "").lstrip("/")
    if not clean_path:
        return False

    url = media_url(clean_path)

    try:
        request = Request(url, method="HEAD")
        with urlopen(request, timeout=2.5) as response:
            return 200 <= int(response.status) < 400
    except HTTPError as exc:
        if exc.code != 405:
            return False
    except (URLError, TimeoutError, ValueError, OSError):
        return False

    try:
        request = Request(url, headers={"Range": "bytes=0-0"}, method="GET")
        with urlopen(request, timeout=2.5) as response:
            return 200 <= int(response.status) < 400
    except (HTTPError, URLError, TimeoutError, ValueError, OSError):
        return False
