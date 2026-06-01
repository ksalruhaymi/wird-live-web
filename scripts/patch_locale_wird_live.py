#!/usr/bin/env python3
"""Patch ar/en django.po for Wird Life branding (run from src/)."""

from __future__ import annotations

import re
from pathlib import Path

LOCALE_DIR = Path(__file__).resolve().parent.parent / "locale"

AR = {
    "contact_page_description": "تواصل مع فريق وِرْد لايف للاستفسارات والدعم الفني وطلبات الانضمام كمعلم.",
    "contact_intro_text": (
        "نسعد بتواصلكم مع فريق وِرْد لايف للاستفسارات، الدعم الفني، أو طلبات الانضمام كمعلم."
    ),
    "contact_success_message": (
        "تم استلام رسالتك بنجاح. سيتواصل معك فريق وِرْد لايف في أقرب وقت ممكن."
    ),
    "contact_support_app": "الدعم الفني لتطبيق وِرْد لايف",
    "wird quran": "وِرْد لايف",
    "wird": "وِرْد لايف",
    "dashboard": "لوحة التحكم",
    "login_register_page": "وِرْد لايف — تسجيل الدخول",
    "login_or_create_account": "سجّل الدخول أو أنشئ حسابًا في وِرْد لايف",
    "register_success": "تم إنشاء حسابك بنجاح. نرحب بك في وِرْد لايف.",
    "web_wrd_quran_platform_mtkamlh_lqrah_quran_alkrym_listening_lltlawat_bashhr_alqra_wtsfh_ktb_tafsir_bshwlh_wbdwn_ialanat": (
        "منصة تعليمية لربط الطلاب بالمعلمين لتصحيح التلاوة، متابعة الحفظ، والمراجعة عن بُعد."
    ),
    "web_wrd_alqraan_alkrym": "عن وِرْد لايف",
    "about_page_meta_description": (
        "تعرف على منصة وِرْد لايف لربط الطلاب بالمعلمين وتصحيح التلاوة ومتابعة الحفظ عن بُعد."
    ),
    "long_about_text": (
        "وِرْد لايف منصة تعليمية تهدف إلى ربط الطلاب بالمعلمين المتخصصين لتصحيح التلاوة، "
        "متابعة الحفظ، والمراجعة عن بُعد من خلال جلسات منظمة وسهلة الاستخدام."
    ),
    "about_wird": (
        "وِرْد لايف منصة تعليمية تهدف إلى ربط الطلاب بالمعلمين المتخصصين لتصحيح التلاوة، "
        "متابعة الحفظ، والمراجعة عن بُعد من خلال جلسات منظمة وسهلة الاستخدام."
    ),
    "home_hero_summary": (
        "منصة تعليمية لربط الطلاب بالمعلمين لتصحيح التلاوة، متابعة الحفظ، والمراجعة عن بُعد."
    ),
    "read_quran": "الرئيسية",
    "daily_wird": "الجلسات",
    "tilawa": "الجلسات",
    "hifz_quran": "الحفظ",
    "translations": "الترجمات",
    "newsletter_subscription_notice": "أنت مشترك في رسائل وِرْد لايف",
    "newsletter_welcome_subject": "شكرًا لاشتراكك في وِرْد لايف",
    "newsletter_thank_you_for_subscribing": "شكرًا لاشتراكك في رسائل وِرْد لايف",
    "newsletter_subscription_success": "شكرًا لك، تم الاشتراك بنجاح في رسائل وِرْد لايف",
    "newsletter_subscription_reactivated": "شكرًا لك، تم إعادة تفعيل اشتراكك في رسائل وِرْد لايف",
    "wird-live_platform_name": "وِرْد لايف",
    "wird-live_platform_tagline": (
        "منصة تعليمية لربط الطلاب بالمعلمين لتصحيح التلاوة، متابعة الحفظ، والمراجعة عن بُعد."
    ),
    "wird-live_about_title": "عن وِرْد لايف",
    "wird-live_about_body": (
        "وِرْد لايف منصة تعليمية تهدف إلى ربط الطلاب بالمعلمين المتخصصين لتصحيح التلاوة، "
        "متابعة الحفظ، والمراجعة عن بُعد من خلال جلسات منظمة وسهلة الاستخدام."
    ),
    "wird-live_contact_title": "تواصل معنا",
    "wird-live_contact_intro": (
        "نسعد بتواصلكم مع فريق وِرْد لايف للاستفسارات، الدعم الفني، أو طلبات الانضمام كمعلم."
    ),
    "wird-live_dashboard_title": "لوحة التحكم",
    "dashboard_sidebar_home": "الرئيسية",
    "dashboard_sidebar_overview": "لوحة المعلومات",
    "dashboard_sidebar_analytics": "إحصائيات الموقع",
    "dashboard_sidebar_settings": "الإعدادات",
    "dashboard_sidebar_notifications": "التنبيهات",
    "dashboard_sidebar_messaging": "قنوات الإرسال",
    "dashboard_sidebar_subscriptions": "الاشتراكات",
    "dashboard_sidebar_contact": "رسائل التواصل",
    "dashboard_sidebar_communication": "التواصل الاجتماعي",
    "dashboard_sidebar_push": "الإشعارات الفورية",
    "dashboard_sidebar_rbac": "إدارة الصلاحيات",
    "dashboard_home_title": "الصفحة الرئيسية",
    "dashboard_overview_title": "لوحة المعلومات",
    "dashboard_overview_subtitle": "ملخص الأرقام والمؤشرات العامة في النظام.",
    "dashboard_rbac_note": "نظام إدارة المستخدمين والصلاحيات (RBAC)",
    "dashboard_users_count": "عدد المستخدمين",
    "dashboard_users_badge": "مستخدمون مسجلون",
    "dashboard_roles_count": "عدد الأدوار",
    "dashboard_roles_badge": "أدوار مهيكلة",
    "dashboard_permissions_count": "عدد الصلاحيات",
    "dashboard_permissions_badge": "صلاحيات مفعّلة",
    "push_placeholder_example": "مثال: تحديث جديد في وِرْد لايف",
    "subscription_unsubscribe_description": "إلغاء الاشتراك من رسائل وِرْد لايف",
    "subscription_unsubscribe_body": "من رسائل وِرْد لايف.",
    "privacy_app_name": "وِرْد لايف",
    "privacy_policy": "سياسة الخصوصية",
    "last_updated_may_2026": "آخر تحديث: مايو 2026",
    "privacy_intro_wird-live": "توضّح هذه السياسة كيفية تعامل منصة وِرْد لايف مع بياناتك. نحرص على الشفافية والإيجاز.",
    "privacy_local_sessions_progress": "جلساتك وتقدم الحفظ والمراجعة",
    "privacy_local_notification_prefs": "تفضيلات الإشعارات والحساب",
    "privacy_local_display_settings": "إعدادات العرض وإمكانية الوصول",
    "analytics_live_badge": "لوحة حية",
    "analytics_stats_subtitle": "متابعة الزوار، الصفحات، والتفاعلات على المنصة.",
    "analytics_total_visitors": "إجمالي الزوار",
    "analytics_total_page_views": "إجمالي زيارات الصفحات",
    "analytics_audio_plays": "تشغيلات الصوت",
    "analytics_page_flips": "تقليب الصفحات",
    "analytics_audio_completions": "إكمالات الصوت",
    "analytics_unique_ips": "عدد IP الفريدة",
    "analytics_visitors_7d": "زوار آخر 7 أيام",
    "analytics_page_views_7d": "زيارات آخر 7 أيام",
    "analytics_page_views_30d": "زيارات آخر 30 يوم",
    "analytics_listen_seconds": "إجمالي ثواني الاستماع",
    "analytics_visitors_today": "زوار اليوم",
    "analytics_recitation_corrections_today": "من صحّح التلاوة اليوم",
    "analytics_sessions_today": "جلسات اليوم",
    "analytics_language_changes_today": "تغييرات اللغة اليوم",
    "analytics_recent_page_views": "زيارات الأيام الأخيرة",
    "analytics_tab_overview": "نظرة عامة",
    "analytics_tab_pages": "الصفحات",
    "analytics_tab_audio": "الصوت",
    "analytics_tab_content": "المحتوى",
    "analytics_tab_interactions": "آخر التفاعلات",
    "analytics_tab_visitors": "الزوار",
    "analytics_badge_label": "إحصائيات • لوحة التحكم",
    "push_tab_summary": "ملخص التنبيهات",
    "push_tab_send": "إرسال تنبيه",
    "push_tab_devices": "الأجهزة",
    "push_tab_history": "التنبيهات المرسلة",
}

EN = {
    "contact_page_description": "Contact the Wird Live team for support, inquiries, and teacher onboarding.",
    "contact_intro_text": (
        "We are happy to hear from the Wird Live team for inquiries, technical support, "
        "or teacher onboarding requests."
    ),
    "contact_success_message": (
        "Your message was received successfully. The Wird Live team will contact you soon."
    ),
    "contact_support_app": "Technical support for the Wird Live app",
    "wird quran": "Wird Live",
    "wird": "Wird Live",
    "dashboard": "Dashboard",
    "login_register_page": "Wird Live — Sign in",
    "login_or_create_account": "Sign in or create an account on Wird Live",
    "register_success": "Your account was created successfully. Welcome to Wird Live.",
    "web_wrd_quran_platform_mtkamlh_lqrah_quran_alkrym_listening_lltlawat_bashhr_alqra_wtsfh_ktb_tafsir_bshwlh_wbdwn_ialanat": (
        "An educational platform connecting students with teachers for recitation correction, "
        "memorization follow-up, and remote review."
    ),
    "web_wrd_alqraan_alkrym": "About Wird Live",
    "about_page_meta_description": (
        "Learn about Wird Live, an educational platform connecting students with teachers "
        "for recitation correction, memorization follow-up, and remote review."
    ),
    "long_about_text": (
        "Wird Live is an educational platform that connects students with specialized teachers "
        "for recitation correction, memorization follow-up, and remote review through organized sessions."
    ),
    "about_wird": (
        "Wird Live is an educational platform that connects students with specialized teachers "
        "for recitation correction, memorization follow-up, and remote review through organized sessions."
    ),
    "home_hero_summary": (
        "An educational platform connecting students with teachers for recitation correction, "
        "memorization follow-up, and remote review."
    ),
    "read_quran": "Home",
    "daily_wird": "Sessions",
    "tilawa": "Sessions",
    "hifz_quran": "Memorization",
    "translations": "Translations",
    "newsletter_subscription_notice": "You are subscribed to Wird Live messages",
    "newsletter_welcome_subject": "Thank you for subscribing to Wird Live",
    "newsletter_thank_you_for_subscribing": "Thank you for subscribing to Wird Live messages",
    "newsletter_subscription_success": "Thank you. You are subscribed to Wird Live messages.",
    "newsletter_subscription_reactivated": "Thank you. Your Wird Live subscription was reactivated.",
    "wird-live_platform_name": "Wird Live",
    "wird-live_platform_tagline": (
        "An educational platform connecting students with teachers for recitation correction, "
        "memorization follow-up, and remote review."
    ),
    "wird-live_about_title": "About Wird Live",
    "wird-live_about_body": (
        "Wird Live is an educational platform that connects students with specialized teachers "
        "for recitation correction, memorization follow-up, and remote review through organized sessions."
    ),
    "wird-live_contact_title": "Contact us",
    "wird-live_contact_intro": (
        "We are happy to hear from the Wird Live team for inquiries, technical support, "
        "or teacher onboarding requests."
    ),
    "wird-live_dashboard_title": "Dashboard",
    "dashboard_sidebar_home": "Home",
    "dashboard_sidebar_overview": "Overview",
    "dashboard_sidebar_analytics": "Site analytics",
    "dashboard_sidebar_settings": "Settings",
    "dashboard_sidebar_notifications": "Notifications",
    "dashboard_sidebar_messaging": "Messaging channels",
    "dashboard_sidebar_subscriptions": "Subscriptions",
    "dashboard_sidebar_contact": "Contact messages",
    "dashboard_sidebar_communication": "Social communication",
    "dashboard_sidebar_push": "Push notifications",
    "dashboard_sidebar_rbac": "Permissions",
    "dashboard_home_title": "Home page",
    "dashboard_overview_title": "Overview dashboard",
    "dashboard_overview_subtitle": "Summary of key numbers and system indicators.",
    "dashboard_rbac_note": "User and permission management (RBAC)",
    "dashboard_users_count": "Users",
    "dashboard_users_badge": "Registered users",
    "dashboard_roles_count": "Roles",
    "dashboard_roles_badge": "Structured roles",
    "dashboard_permissions_count": "Permissions",
    "dashboard_permissions_badge": "Active permissions",
    "push_placeholder_example": "Example: New update in Wird Live",
    "subscription_unsubscribe_description": "Unsubscribe from Wird Live messages",
    "subscription_unsubscribe_body": "from Wird Live messages.",
    "privacy_app_name": "Wird Live",
    "privacy_policy": "Privacy Policy",
    "last_updated_may_2026": "Last updated: May 2026",
    "privacy_intro_wird-live": "This policy explains how Wird Live handles your data. We value transparency and clarity.",
    "privacy_local_sessions_progress": "Your sessions and memorization/review progress",
    "privacy_local_notification_prefs": "Notification and account preferences",
    "privacy_local_display_settings": "Display and accessibility settings",
    "analytics_live_badge": "Live dashboard",
    "analytics_stats_subtitle": "Track visitors, pages, and interactions on the platform.",
    "analytics_total_visitors": "Total visitors",
    "analytics_total_page_views": "Total page views",
    "analytics_audio_plays": "Audio plays",
    "analytics_page_flips": "Page flips",
    "analytics_audio_completions": "Audio completions",
    "analytics_unique_ips": "Unique IPs",
    "analytics_visitors_7d": "Visitors (7 days)",
    "analytics_page_views_7d": "Page views (7 days)",
    "analytics_page_views_30d": "Page views (30 days)",
    "analytics_listen_seconds": "Total listen seconds",
    "analytics_visitors_today": "Visitors today",
    "analytics_recitation_corrections_today": "Recitation corrections today",
    "analytics_sessions_today": "Sessions today",
    "analytics_language_changes_today": "Language changes today",
    "analytics_recent_page_views": "Recent page views",
    "analytics_tab_overview": "Overview",
    "analytics_tab_pages": "Pages",
    "analytics_tab_audio": "Audio",
    "analytics_tab_content": "Content",
    "analytics_tab_interactions": "Recent interactions",
    "analytics_tab_visitors": "Visitors",
    "analytics_badge_label": "Analytics • Dashboard",
    "push_tab_summary": "Push summary",
    "push_tab_send": "Send notification",
    "push_tab_devices": "Devices",
    "push_tab_history": "Sent notifications",
}


def escape_po(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def format_msgstr(text: str) -> str:
    if "\n" not in text:
        return f'msgstr "{escape_po(text)}"\n'
    parts = ['msgstr ""\n']
    for line in text.split("\n"):
        parts.append(f'"{escape_po(line)}\\n"\n')
    return "".join(parts)


def patch_po(path: Path, updates: dict[str, str]) -> None:
    content = path.read_text(encoding="utf-8")
    content = content.replace("Project-Id-Version: wird\n", "Project-Id-Version: wird-live\n")

    msgstr_block = (
        r"(?:"
        r'msgstr "(?:[^"\\]|\\.)*"\n'
        r'|msgstr ""\n(?:"(?:[^"\\]|\\.)*\\n"\n)+'
        r")"
    )
    for msgid, msgstr in updates.items():
        escaped_id = re.escape(msgid)
        pattern = re.compile(rf'msgid "{escaped_id}"\n{msgstr_block}')
        replacement = f'msgid "{msgid}"\n' + format_msgstr(msgstr)
        if pattern.search(content):
            content = pattern.sub(replacement, content, count=1)
        else:
            content += f'\nmsgid "{msgid}"\n' + format_msgstr(msgstr)

    path.write_text(content, encoding="utf-8")


def main() -> None:
    patch_po(LOCALE_DIR / "ar/LC_MESSAGES/django.po", AR)
    patch_po(LOCALE_DIR / "en/LC_MESSAGES/django.po", EN)
    print("Patched ar and en locale files.")


if __name__ == "__main__":
    main()
