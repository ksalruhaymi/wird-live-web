from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path, re_path
from django.conf.urls.i18n import set_language
from django.views.static import serve

from core.media_views import protected_media

from .sitemaps import StaticViewSitemap

sitemaps = {
    "static": StaticViewSitemap,
}

urlpatterns = [
    path("", include("web.urls", namespace="web")),
    path("rbac/", include("identity.rbac.urls", namespace="rbac")),
    path("accounts/", include(("identity.accounts.urls", "accounts"), namespace="accounts")),
    path("dashboard/", include("dashboard.urls", namespace="dashboard")),

    path("notifications/", include(("apps.notification.urls", "apps.notification"), namespace="apps.notification")),
    path("messaging/", include(("apps.messaging.urls", "apps.messaging"), namespace="apps.messaging")),

    path("communication/", include("apps.communication.urls")),
    path("contact/", include("apps.contact.urls")),
    path("subscription/", include(("apps.subscription.urls", "subscription"), namespace="apps.subscription")),
    path("api/v1/", include("apps.contact.api.urls", namespace="contact_api")),
    path("api/v1/", include("apps.push.api.urls", namespace="push_api")),
    path("api/v1/", include("apps.subscription.api.urls", namespace="subscription_api")),
    path("api/v1/", include("apps.communication.api.urls", namespace="communication_api")),
    path("api/v1/", include("apps.maqraa.api.urls", namespace="maqraa_api")),
    path("api/v1/", include("apps.calls.api.urls", namespace="calls_api")),
    path("api/v1/", include("apps.chat.api.urls", namespace="chat_api")),
    path(
        "api/v1/auth/",
        include(("identity.accounts.api.urls", "accounts_auth_api"), namespace="accounts_auth_api"),
    ),
    path("push/", include("apps.push.urls", namespace="push")),

    path("sitemap.xml", sitemap, {"sitemaps": sitemaps}, name="sitemap"),
    path("i18n/setlang/", set_language, name="set_language"),
]

if not getattr(settings, "MEDIA_USES_REMOTE_SERVER", False):
    urlpatterns += [
        re_path(r"^media/translations/(?P<path>.+)$", serve, {"document_root": settings.MEDIA_ROOT / "translations"}),
        re_path(r"^media/(?P<path>.+)$", protected_media, name="protected-media"),
    ]

if settings.DEBUG:
    urlpatterns += [
        path("admin/", admin.site.urls),
    ]
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
