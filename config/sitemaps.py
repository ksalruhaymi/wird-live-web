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
            "web:contact",
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


class QuranPagesSitemap(Sitemap):
    protocol = "https"
    priority = 0.9
    changefreq = "weekly"
    limit = 2000

    def items(self):
        mushafs = ["hafs", "warsh", "qaloun", "douri", "shuba", "sousi"]
        pages = range(1, 605)
        return [(mushaf, page) for mushaf in mushafs for page in pages]

    def location(self, item):
        mushaf, page = item
        return reverse(
            "quran:quran_mushaf_page",
            kwargs={"mushaf": mushaf, "page": page},
        )


class SurahPagesSitemap(Sitemap):
    protocol = "https"
    priority = 0.9
    changefreq = "weekly"
    limit = 2000

    def items(self):
        mushafs = ["hafs", "warsh", "qaloun", "douri", "shuba", "sousi"]
        surahs = range(1, 115)
        return [(mushaf, surah) for mushaf in mushafs for surah in surahs]

    def location(self, item):
        mushaf, surah = item
        return reverse(
            "quran:quran_mushaf_surah",
            kwargs={"mushaf": mushaf, "surah": surah},
        )


class QurraPagesSitemap(Sitemap):
    protocol = "https"
    priority = 0.7
    changefreq = "monthly"
    limit = 2000

    def items(self):
        mushafs = ["hafs", "warsh", "qaloun", "douri", "shuba", "sousi"]
        qurra = range(1, 31)
        return [(mushaf, qari) for mushaf in mushafs for qari in qurra]

    def location(self, item):
        mushaf, qari = item
        return reverse(
            "quran:quran_mushaf_qari",
            kwargs={"mushaf": mushaf, "qari": qari},
        )


class TafsirPagesSitemap(Sitemap):
    protocol = "https"
    priority = 0.6
    changefreq = "weekly"
    limit = 2000

    def items(self):
        mushafs = ["hafs", "warsh", "qaloun", "douri", "shuba", "sousi"]
        pages = range(1, 605)
        return [(mushaf, page) for mushaf in mushafs for page in pages]

    def location(self, item):
        mushaf, page = item
        return reverse(
            "quran:quran_mushaf_tafsir",
            kwargs={"mushaf": mushaf, "page": page},
        )