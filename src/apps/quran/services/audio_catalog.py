from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from types import SimpleNamespace

from django.conf import settings

from apps.quran.mushaf_config import MUSHAFS
from apps.quran.models import Qurra

_REMOTE_CACHE: dict[tuple[str, bool], tuple[float, list[dict]]] = {}


def _normalize_mushaf_key(mushaf_key: str | None) -> str:
    key = (mushaf_key or "").strip().lower()
    if key in MUSHAFS:
        return key
    return "hafs"


def _reader_dir_has_audio(reader_dir: Path) -> bool:
    try:
        return next(reader_dir.rglob("*.mp3"), None) is not None
    except Exception:
        return False


def _local_reader_codes(mushaf_key: str, require_audio: bool = False) -> list[str]:
    base_dir = Path(settings.MEDIA_ROOT) / "audio" / mushaf_key

    if not base_dir.exists() or not base_dir.is_dir():
        return []

    codes: list[str] = []

    for item in sorted(base_dir.iterdir(), key=lambda item: item.name.lower()):
        if not item.is_dir():
            continue

        if require_audio and not _reader_dir_has_audio(item):
            continue

        codes.append(item.name)

    return codes


def _catalog_url() -> str:
    configured = (getattr(settings, "AUDIO_CATALOG_URL", "") or "").strip()
    if configured:
        return configured

    server_media_url = (getattr(settings, "SERVER_MEDIA_URL", "") or "").strip()
    parsed = urllib.parse.urlparse(server_media_url)

    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}/api/v1/audio/readers/"

    return ""


def _catalog_api_key() -> str:
    return (getattr(settings, "AUDIO_CATALOG_API_KEY", "") or "").strip()


def _remote_request_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "WirdLocalDjango/1.0",
    }

    api_key = _catalog_api_key()
    if api_key:
        headers["X-API-KEY"] = api_key

    return headers


def _fetch_remote_payload(mushaf_key: str, require_audio: bool = False) -> dict:
    catalog_url = _catalog_url()

    if not catalog_url:
        return {}

    query = urllib.parse.urlencode(
        {
            "mushaf": mushaf_key,
            "require_audio": "1" if require_audio else "0",
        }
    )

    separator = "&" if "?" in catalog_url else "?"
    url = f"{catalog_url}{separator}{query}"

    request = urllib.request.Request(
        url,
        headers=_remote_request_headers(),
        method="GET",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=float(getattr(settings, "AUDIO_CATALOG_TIMEOUT", 5) or 5),
        ) as response:
            raw = response.read().decode("utf-8")
            payload = json.loads(raw)
    except (
        OSError,
        urllib.error.URLError,
        urllib.error.HTTPError,
        TimeoutError,
        json.JSONDecodeError,
        UnicodeDecodeError,
    ):
        return {}

    if not isinstance(payload, dict):
        return {}

    return payload


def _normalize_remote_readers(payload: dict) -> list[dict]:
    readers = payload.get("readers")

    if isinstance(readers, list):
        normalized: list[dict] = []

        for reader in readers:
            if not isinstance(reader, dict):
                continue

            code = str(reader.get("code") or "").strip()
            if not code:
                continue

            normalized.append(reader)

        return normalized

    reader_codes = payload.get("reader_codes")

    if isinstance(reader_codes, list):
        normalized = []

        for code in reader_codes:
            clean_code = str(code or "").strip()
            if not clean_code:
                continue

            normalized.append(
                {
                    "code": clean_code,
                    "name_ar": clean_code.replace("_", " "),
                    "name_en": clean_code.replace("_", " ").title(),
                    "image": "",
                }
            )

        return normalized

    return []


def _fetch_remote_readers(mushaf_key: str, require_audio: bool = False) -> list[dict]:
    cache_seconds = int(getattr(settings, "AUDIO_CATALOG_CACHE_SECONDS", 60) or 0)
    cache_key = (mushaf_key, require_audio)
    now = time.time()

    if cache_seconds > 0:
        cached = _REMOTE_CACHE.get(cache_key)
        if cached and now - cached[0] < cache_seconds:
            return cached[1]

    payload = _fetch_remote_payload(mushaf_key, require_audio=require_audio)
    readers = _normalize_remote_readers(payload)

    if cache_seconds > 0:
        _REMOTE_CACHE[cache_key] = (now, readers)

    return readers


def audio_reader_codes_for_mushaf(
    mushaf_key: str | None,
    require_audio: bool = False,
) -> list[str]:
    key = _normalize_mushaf_key(mushaf_key)
    media_source = (getattr(settings, "MEDIA_SOURCE", "local") or "local").strip().lower()

    if media_source == "server":
        remote_readers = _fetch_remote_readers(key, require_audio=require_audio)
        codes = [str(item.get("code") or "").strip() for item in remote_readers]
        return [code for code in codes if code]

    return _local_reader_codes(key, require_audio=require_audio)


def qari_objects_for_mushaf(mushaf_key: str | None) -> list:
    key = _normalize_mushaf_key(mushaf_key)
    media_source = (getattr(settings, "MEDIA_SOURCE", "local") or "local").strip().lower()

    if media_source == "server":
        remote_readers = _fetch_remote_readers(key, require_audio=False)

        if remote_readers:
            local_by_code = {
                q.code.strip().lower(): q
                for q in Qurra.objects.filter(is_visible=True)
            }

            out = []

            for item in remote_readers:
                code = str(item.get("code") or "").strip()
                if not code:
                    continue

                local_qari = local_by_code.get(code.lower())

                if local_qari is not None:
                    out.append(local_qari)
                    continue

                out.append(
                    SimpleNamespace(
                        id=item.get("id"),
                        number=item.get("number"),
                        code=code,
                        name_ar=item.get("name_ar") or code.replace("_", " "),
                        name_en=item.get("name_en") or code.replace("_", " ").title(),
                        fullname=item.get("fullname")
                        or item.get("name_ar")
                        or code.replace("_", " "),
                        info=item.get("info") or "",
                        image=item.get("image") or "",
                        supported_mushafs=item.get("supported_mushafs") or [key],
                        is_visible=True,
                    )
                )

            return out

        return []

    local_codes = _local_reader_codes(key, require_audio=False)

    if not local_codes:
        return []

    by_code = {
        q.code.strip().lower(): q
        for q in Qurra.objects.filter(is_visible=True)
    }

    return [
        by_code[code.lower()]
        for code in local_codes
        if code.lower() in by_code
    ]