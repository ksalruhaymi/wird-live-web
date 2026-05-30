from django.contrib.sitemaps import Sitemap
from django.urls import reverse


class StaticViewSitemap(Sitemap):
    protocol = "https"
    priority = 1.0
    changefreq = "daily"

    def items(self):
        items = ["web:home"]

        optional_routes = [
            "web:about",
            "contact:contact",
        ]

        for route_name in optional_routes:
            try:
                reverse(route_name)
                items.append(route_name)
            except Exception:
                pass

        return items

    def location(self, item):
        return reverse(item)
