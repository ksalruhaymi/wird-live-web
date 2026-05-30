import ipaddress
import json
import urllib.request

from django.db.models import F

from .models import AnalyticsIPAddress, AnalyticsVisitor, PageView


class SiteAnalyticsMiddleware:
    EXCLUDED_PREFIXES = (
        "/static/",
        "/media/",
        "/admin/",
        "/analytics/track/",
        "/favicon.ico",
        "/robots.txt",
        "/sitemap.xml",
    )

    EXCLUDED_SEGMENTS = (
        "/api/",
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if request.method != "GET":
            return response

        path = request.path or "/"
        if self._should_skip(path):
            return response

        if not request.session.session_key:
            request.session.save()

        session_key = request.session.session_key
        if not session_key:
            return response

        ip_address = self.get_ip(request)
        ua = request.META.get("HTTP_USER_AGENT", "")
        language_code = (getattr(request, "LANGUAGE_CODE", "") or "").strip()[:16]
        device_type, os_name, os_version, browser_name, browser_version = self.parse_user_agent(ua)
        visitor, created = AnalyticsVisitor.objects.get_or_create(
            session_key=session_key,
            defaults={
                "user": request.user if getattr(request.user, "is_authenticated", False) else None,
                "ip_address": ip_address,
                "os_name": os_name,
                "os_version": os_version,
                "browser_name": browser_name,
                "browser_version": browser_version,
                "device_type": device_type,
                "last_language": language_code,
                "user_agent": ua[:2000],
                "visits_count": 1,
                "is_authenticated": getattr(request.user, "is_authenticated", False),
            },
        )

        if not created:
            AnalyticsVisitor.objects.filter(pk=visitor.pk).update(
                visits_count=F("visits_count") + 1,
                user=request.user if getattr(request.user, "is_authenticated", False) else None,
                ip_address=ip_address,
                os_name=os_name,
                os_version=os_version,
                browser_name=browser_name,
                browser_version=browser_version,
                device_type=device_type,
                last_language=language_code,
                user_agent=ua[:2000],
                is_authenticated=getattr(request.user, "is_authenticated", False),
            )
            visitor.refresh_from_db(fields=["visits_count", "last_seen_at"])

        if ip_address:
            country_code, country_name = self.lookup_country(ip_address)
            ip_obj, ip_created = AnalyticsIPAddress.objects.get_or_create(
                ip_address=ip_address,
                defaults={
                    "hits_count": 1,
                    "country_code": country_code,
                    "country_name": country_name,
                    "last_language": language_code,
                },
            )
            if not ip_created:
                AnalyticsIPAddress.objects.filter(pk=ip_obj.pk).update(
                    hits_count=F("hits_count") + 1,
                    country_code=country_code or F("country_code"),
                    country_name=country_name or F("country_name"),
                    last_language=language_code,
                )

        PageView.objects.create(
            visitor=visitor,
            path=path[:255],
            full_path=request.get_full_path()[:500],
            method=request.method,
            referrer=request.META.get("HTTP_REFERER", "")[:2000],
        )
        return response

    def _should_skip(self, path: str) -> bool:
        if any(path.startswith(prefix) for prefix in self.EXCLUDED_PREFIXES):
            return True
        if any(segment in path for segment in self.EXCLUDED_SEGMENTS):
            return True
        return False

    def get_ip(self, request):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR")

    def parse_user_agent(self, user_agent: str):
        ua = (user_agent or "").lower()

        device_type = "desktop"
        if "bot" in ua or "spider" in ua or "crawler" in ua:
            device_type = "bot"
        if "tablet" in ua or "ipad" in ua:
            device_type = "tablet"
        elif "mobile" in ua or "iphone" in ua or "android" in ua:
            device_type = "mobile"

        os_name = "Unknown"
        os_version = ""
        if "windows nt 10.0" in ua:
            os_name, os_version = "Windows", "10/11"
        elif "windows nt 6.3" in ua:
            os_name, os_version = "Windows", "8.1"
        elif "windows nt 6.2" in ua:
            os_name, os_version = "Windows", "8"
        elif "windows nt 6.1" in ua:
            os_name, os_version = "Windows", "7"
        elif "android" in ua:
            os_name = "Android"
            os_version = self._extract_version(ua, "android ")
        elif "iphone os " in ua or "cpu iphone os " in ua or "ipad; cpu os " in ua:
            os_name = "iOS"
            os_version = (
                self._extract_version(ua, "iphone os ")
                or self._extract_version(ua, "cpu iphone os ")
                or self._extract_version(ua, "ipad; cpu os ")
            ).replace("_", ".")
        elif "mac os x " in ua or "macintosh" in ua:
            os_name = "macOS"
            os_version = self._extract_version(ua, "mac os x ").replace("_", ".")
        elif "cros " in ua:
            os_name = "ChromeOS"
            os_version = self._extract_version(ua, "cros ")
        elif "ubuntu" in ua:
            os_name = "Linux (Ubuntu)"
        elif "linux" in ua:
            os_name = "Linux"

        browser_name = "Unknown"
        browser_version = ""
        if "edg/" in ua or "edga/" in ua or "edgios/" in ua:
            browser_name = "Edge"
            browser_version = (
                self._extract_version(ua, "edg/")
                or self._extract_version(ua, "edga/")
                or self._extract_version(ua, "edgios/")
            )
        elif "opr/" in ua:
            browser_name = "Opera"
            browser_version = self._extract_version(ua, "opr/")
        elif "brave/" in ua:
            browser_name = "Brave"
            browser_version = self._extract_version(ua, "brave/")
        elif "vivaldi/" in ua:
            browser_name = "Vivaldi"
            browser_version = self._extract_version(ua, "vivaldi/")
        elif "yabrowser/" in ua:
            browser_name = "Yandex Browser"
            browser_version = self._extract_version(ua, "yabrowser/")
        elif "ucbrowser/" in ua:
            browser_name = "UC Browser"
            browser_version = self._extract_version(ua, "ucbrowser/")
        elif "samsungbrowser/" in ua:
            browser_name = "Samsung Internet"
            browser_version = self._extract_version(ua, "samsungbrowser/")
        elif "crios/" in ua:
            browser_name = "Chrome (iOS)"
            browser_version = self._extract_version(ua, "crios/")
        elif "fxios/" in ua:
            browser_name = "Firefox (iOS)"
            browser_version = self._extract_version(ua, "fxios/")
        elif "chrome/" in ua and "chromium" not in ua:
            browser_name = "Chrome"
            browser_version = self._extract_version(ua, "chrome/")
        elif "firefox/" in ua:
            browser_name = "Firefox"
            browser_version = self._extract_version(ua, "firefox/")
        elif "safari/" in ua and "chrome/" not in ua and "chromium" not in ua:
            browser_name = "Safari"
            browser_version = self._extract_version(ua, "version/")

        return device_type, os_name, os_version, browser_name, browser_version

    def _extract_version(self, ua: str, token: str) -> str:
        if token not in ua:
            return ""
        value = ua.split(token, 1)[1]
        stop_chars = [" ", ";", ")", "("]
        for ch in stop_chars:
            value = value.split(ch, 1)[0]
        return value.strip()

    def lookup_country(self, ip_address: str):
        try:
            ip_obj = ipaddress.ip_address(ip_address)
            if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_reserved:
                return "", ""
        except ValueError:
            return "", ""

        url = f"https://ipapi.co/{ip_address}/json/"
        try:
            with urllib.request.urlopen(url, timeout=1.5) as resp:
                if resp.status != 200:
                    return "", ""
                data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                return (data.get("country_code") or "", data.get("country_name") or "")
        except Exception:
            return "", ""
