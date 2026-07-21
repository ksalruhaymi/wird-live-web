from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from identity.accounts.user_types import (
    USER_TYPE_ADMIN,
    USER_TYPE_STUDENT,
    USER_TYPE_SUPERVISOR,
    USER_TYPE_TEACHER,
)
from identity.rbac.models import Role, Permission

User = get_user_model()


# ---------------------------------------------------------------------------
# Legacy permission codes (kept for backward compatibility during migration).
# ---------------------------------------------------------------------------
LEGACY_PERMISSIONS = [
    ("dashboard.access", "لوحة التحكم"),
    ("rbac.access", "إدارة الصلاحيات"),
    ("overview.access", "الوصول إلى لوحة المعلومات"),
    ("settings.access", "إدارة إعدادات تسجيل الدخول"),
    # Users / roles / permissions (legacy codes used in RBAC views)
    ("users.list", "عرض المستخدمين"),
    ("users.detail", "عرض تفاصيل مستخدم"),
    ("users.create", "إضافة مستخدم"),
    ("users.update", "تعديل مستخدم"),
    ("users.delete", "حذف مستخدم"),
    ("roles.list", "عرض الأدوار"),
    ("roles.create", "إضافة دور"),
    ("roles.update", "تعديل دور"),
    ("roles.delete", "حذف دور"),
    ("permissions.list", "عرض الصلاحيات"),
    ("permissions.create", "إضافة صلاحية"),
    ("permissions.update", "تعديل صلاحية"),
    ("permissions.delete", "حذف صلاحية"),
    ("permissions.assign_roles", "ربط الصلاحيات بالأدوار"),
    # Aliases (view.*) for clarity — map to same module as list.*
    ("users.view", "عرض المستخدمين"),
    ("users.teachers.view", "عرض المعلمين في لوحة المستخدمين"),
    ("users.students.view", "عرض الطلاب في لوحة المستخدمين"),
    ("management.view", "عرض الإدارة"),
    ("management.teachers.view", "عرض طلبات المعلمين الجدد"),
    ("management.teachers.approve", "الموافقة على المعلمين"),
    ("management.teachers.reject", "رفض المعلمين"),
    ("roles.view", "عرض الأدوار"),
    ("permissions.view", "عرض الصلاحيات"),
    ("permissions.assign", "ربط الصلاحيات بالأدوار"),
    # Teachers / calls
    ("teachers.view", "عرض المعلمين"),
    ("teachers.update", "تعديل المعلمين"),
    ("teachers.availability.view", "عرض حالة المعلمين"),
    ("calls.view", "عرض سجل المكالمات"),
    ("appointments.view", "عرض المواعيد"),
    ("appointments.manage_schedule", "إدارة جدول المواعيد"),
    ("appointments.manage_bookings", "إدارة حجوزات المواعيد"),
    ("appointments.view_all", "عرض جميع المواعيد"),
    ("appointments.override_status", "تجاوز حالات المواعيد"),
    # Subscriptions / announcements
    ("subscriptions.view", "عرض الاشتراكات"),
    ("subscriptions.create", "إنشاء اشتراك"),
    ("subscriptions.update", "تعديل اشتراك"),
    ("subscriptions.delete", "حذف اشتراك"),
    ("announcements.view", "عرض الإعلانات"),
    ("announcements.create", "إنشاء إعلان"),
    ("announcements.update", "تعديل إعلان"),
    ("announcements.delete", "حذف إعلان"),
    ("app_notifications.view", "عرض تنبيهات التطبيق"),
    ("app_notifications.create", "إنشاء تنبيه تطبيق"),
    ("app_notifications.update", "تعديل تنبيه تطبيق"),
    ("app_notifications.delete", "حذف تنبيه تطبيق"),
    # Evaluations / recordings
    ("evaluations.view", "عرض التقييمات"),
    ("evaluations.create", "إضافة سؤال تقييم"),
    ("evaluations.update", "تعديل سؤال تقييم"),
    ("evaluations.delete", "حذف سؤال تقييم"),
    ("recordings.view", "عرض التسجيلات"),
    ("recordings.delete", "حذف التسجيلات"),
    ("mobile_app_config.view", "عرض إعدادات تطبيق الجوال"),
    ("mobile_app_config.update", "تعديل إعدادات تطبيق الجوال"),
    ("mobile_versions.view", "عرض إصدارات التطبيق"),
    ("mobile_versions.manage", "إدارة إصدارات التطبيق"),
    # Notifications / messaging / communication
    ("notification.access", "الوصول إلى التنبيهات"),
    ("notification.create", "إرسال تنبيه"),
    ("notification.inapp", "عرض التنبيهات الداخلية"),
    ("messaging.access", "الوصول إلى قنوات الإرسال"),
    ("messaging.create", "إنشاء رسالة"),
    ("messaging.email", "عرض البريد الإلكتروني"),
    ("messaging.whatsapp", "عرض رسائل واتساب"),
    ("messaging.sms", "عرض رسائل SMS"),
    ("messaging.manage_newsletter", "إدارة النشرة البريدية"),
    ("communication.access", "الوصول للتواصل"),
    ("communication.create", "إنشاء رسالة"),
    ("communication.campaigns", "عرض الحملات"),
    ("communication.logs", "عرض سجل الإرسال"),
    ("contact.access", "الوصول للتواصل"),
    ("contact.list", "عرض رسائل التواصل"),
    ("contact.create", "إنشاء رسالة تواصل"),
    ("subscription.access", "الوصول إلى الاشتراكات (قديم)"),
    ("subscription.create", "إرسال رسالة اشتراك"),
    ("subscription.subscriber", "عرض المشتركين"),
    ("push.access", "الوصول إلى الإشعارات الفورية"),
]

# ---------------------------------------------------------------------------
# New structured permissions: web.* / mobile.* / shared.*
# ---------------------------------------------------------------------------
WEB_PERMISSIONS = [
    ("web.dashboard.access", "الوصول إلى لوحة التحكم"),
    ("web.dashboard.overview.view", "عرض لوحة المعلومات"),
    ("web.settings.login.view", "عرض إعدادات تسجيل الدخول"),
    ("web.settings.login.update", "تعديل إعدادات تسجيل الدخول"),
    ("web.subscriptions.plans.view", "عرض باقات الاشتراك"),
    ("web.subscriptions.plans.create", "إنشاء باقة اشتراك"),
    ("web.subscriptions.plans.update", "تعديل باقة اشتراك"),
    ("web.subscriptions.plans.delete", "حذف باقة اشتراك"),
    ("web.subscriptions.plans.toggle", "تفعيل/تعطيل باقة اشتراك"),
    ("web.subscriptions.students.view", "عرض سجل اشتراكات الطلاب"),
    ("web.subscriptions.students.update", "تعديل اشتراك طالب"),
    ("web.subscriptions.students.delete", "حذف سجل اشتراك طالب"),
    ("web.announcements.view", "عرض الإعلانات"),
    ("web.announcements.create", "إنشاء إعلان"),
    ("web.announcements.update", "تعديل إعلان"),
    ("web.announcements.delete", "حذف إعلان"),
    ("web.announcements.toggle", "تفعيل/تعطيل إعلان"),
    ("web.app_notifications.view", "عرض تنبيهات التطبيق"),
    ("web.app_notifications.create", "إنشاء تنبيه تطبيق"),
    ("web.app_notifications.update", "تعديل تنبيه تطبيق"),
    ("web.app_notifications.delete", "حذف تنبيه تطبيق"),
    ("web.app_notifications.toggle", "تفعيل/تعطيل تنبيه تطبيق"),
    ("web.mobile_app_config.view", "عرض إعدادات تطبيق الجوال"),
    ("web.mobile_app_config.update", "تعديل إعدادات تطبيق الجوال"),
    ("web.mobile_versions.view", "عرض إصدارات التطبيق"),
    ("web.mobile_versions.manage", "إدارة إصدارات التطبيق"),
    ("web.users.teachers.view", "عرض المعلمين في لوحة المستخدمين"),
    ("web.users.students.view", "عرض الطلاب في لوحة المستخدمين"),
    ("web.users.teachers.update", "تعديل بيانات معلم"),
    ("web.users.students.update", "تعديل بيانات طالب"),
    ("web.calls.view", "عرض سجل المكالمات"),
    ("web.appointments.view", "عرض المواعيد"),
    ("web.appointments.manage_schedule", "إدارة جدول المواعيد"),
    ("web.appointments.manage_bookings", "إدارة حجوزات المواعيد"),
    ("web.appointments.view_all", "عرض جميع المواعيد"),
    ("web.appointments.override_status", "تجاوز حالات المواعيد"),
    ("web.teachers.availability.view", "عرض حالة المعلمين"),
    ("web.evaluations.view", "عرض تقييمات الجلسات"),
    ("web.evaluations.questions.create", "إضافة سؤال تقييم"),
    ("web.evaluations.questions.update", "تعديل سؤال تقييم"),
    ("web.evaluations.questions.delete", "حذف سؤال تقييم"),
    ("web.evaluations.questions.toggle", "تفعيل/تعطيل فئة تقييم"),
    ("web.recordings.view", "عرض التسجيلات"),
    ("web.recordings.delete", "حذف التسجيلات"),
    ("web.rbac.access", "الوصول إلى إدارة الصلاحيات"),
    ("web.rbac.users.view", "عرض مستخدمي RBAC"),
    ("web.rbac.users.create", "إنشاء مستخدم RBAC"),
    ("web.rbac.users.update", "تعديل مستخدم RBAC"),
    ("web.rbac.users.delete", "حذف مستخدم RBAC"),
    ("web.rbac.roles.view", "عرض الأدوار"),
    ("web.rbac.roles.create", "إنشاء دور"),
    ("web.rbac.roles.update", "تعديل دور"),
    ("web.rbac.roles.delete", "حذف دور"),
    ("web.rbac.permissions.view", "عرض الصلاحيات"),
    ("web.rbac.permissions.create", "إنشاء صلاحية"),
    ("web.rbac.permissions.update", "تعديل صلاحية"),
    ("web.rbac.permissions.delete", "حذف صلاحية"),
    ("web.rbac.permissions.assign", "ربط الصلاحيات بالأدوار"),
]

MOBILE_PERMISSIONS = [
    ("mobile.nav.home.view", "تبويب الرئيسية"),
    ("mobile.nav.teachers.view", "تبويب المعلمون"),
    ("mobile.nav.recordings.view", "تبويب التسجيلات"),
    ("mobile.nav.management.view", "تبويب الإدارة"),
    ("mobile.nav.settings.view", "تبويب الإعدادات"),
    ("mobile.nav.subscriptions.view", "تبويب الاشتراكات"),
    ("mobile.nav.appointments.view", "تبويب المواعيد"),
    ("mobile.management.teachers.view", "عرض طلبات المعلمين الجدد"),
    ("mobile.management.teachers.approve", "الموافقة على المعلمين"),
    ("mobile.management.teachers.reject", "رفض المعلمين"),
    ("mobile.management.teachers.interview_call", "مكالمة مقابلة معلم"),
    ("mobile.teachers.list.view", "عرض قائمة المعلمين"),
    ("mobile.teachers.profile.view", "عرض ملف المعلم"),
    ("mobile.teachers.favorite.toggle", "إضافة/إزالة المعلم من المفضلة"),
    ("mobile.subscriptions.packages.view", "عرض باقات الاشتراك"),
    ("mobile.subscriptions.status.view", "عرض حالة الاشتراك"),
    ("mobile.subscriptions.checkout.create", "إنشاء طلب اشتراك"),
    ("mobile.calls.request", "طلب مكالمة (طالب)"),
    ("mobile.evaluations.submit", "إرسال تقييم جلسة"),
    ("mobile.teacher.home.view", "الشاشة الرئيسية للمعلم"),
    ("mobile.teacher.availability.update", "تحديث حالة توفر المعلم"),
    ("mobile.teacher.heartbeat.send", "إرسال نبضة حضور المعلم"),
    ("mobile.calls.incoming.view", "عرض المكالمات الواردة"),
    ("mobile.calls.accept", "قبول مكالمة"),
    ("mobile.calls.reject", "رفض مكالمة"),
    ("mobile.recordings.list_own.view", "عرض تسجيلاتي"),
]

SHARED_PERMISSIONS = [
    ("shared.profile.view", "عرض الملف الشخصي"),
    ("shared.profile.update", "تحديث الملف الشخصي"),
    ("shared.profile.avatar.update", "تحديث صورة الملف الشخصي"),
    ("shared.recordings.play_own", "تشغيل تسجيلاتي"),
    ("shared.recordings.play_all", "تشغيل كل التسجيلات (مراقبة)"),
    ("shared.recordings.download_own", "تحميل تسجيلاتي"),
    ("shared.recordings.download_all", "تحميل كل التسجيلات (مراقبة)"),
]

# Supervisor legacy codes (unchanged during migration).
SUPERVISOR_LEGACY_PERMISSIONS = [
    "dashboard.access",
    "overview.access",
    "subscriptions.view",
    "subscriptions.create",
    "subscriptions.update",
    "announcements.view",
    "announcements.create",
    "announcements.update",
    "app_notifications.view",
    "app_notifications.create",
    "app_notifications.update",
    "calls.view",
    "appointments.view",
    "appointments.view_all",
    "teachers.availability.view",
    "evaluations.view",
    "evaluations.create",
    "evaluations.update",
    "recordings.view",
    "users.view",
    "users.teachers.view",
    "users.students.view",
    "management.teachers.view",
    "management.teachers.approve",
    "management.teachers.reject",
]

SUPERVISOR_WEB_PERMISSIONS = [
    "web.dashboard.access",
    "web.dashboard.overview.view",
    "web.users.teachers.view",
    "web.users.students.view",
    "web.calls.view",
    "web.appointments.view",
    "web.appointments.view_all",
    "web.recordings.view",
    "web.teachers.availability.view",
    "web.evaluations.view",
    "web.announcements.view",
    "web.announcements.create",
    "web.announcements.update",
    "web.app_notifications.view",
    "web.app_notifications.create",
    "web.app_notifications.update",
    "web.subscriptions.students.view",
]

SUPERVISOR_MOBILE_PERMISSIONS = [
    "mobile.nav.home.view",
    "mobile.nav.teachers.view",
    "mobile.nav.recordings.view",
    "mobile.nav.management.view",
    "mobile.nav.settings.view",
    "mobile.nav.subscriptions.view",
    "mobile.management.teachers.view",
    "mobile.management.teachers.approve",
    "mobile.management.teachers.reject",
    "mobile.management.teachers.interview_call",
    # Teachers screen: list all approved teachers and place outbound calls.
    "mobile.teachers.list.view",
    "mobile.teachers.profile.view",
    "mobile.teachers.favorite.toggle",
    "mobile.calls.request",
    # Packages + paid store checkout (not complimentary).
    "mobile.subscriptions.packages.view",
    "mobile.subscriptions.status.view",
    "mobile.subscriptions.checkout.create",
]

SUPERVISOR_SHARED_PERMISSIONS = [
    "shared.profile.view",
    "shared.recordings.play_all",
]

TEACHER_MOBILE_PERMISSIONS = [
    "mobile.nav.home.view",
    "mobile.nav.recordings.view",
    "mobile.nav.settings.view",
    "mobile.nav.appointments.view",
    "mobile.teacher.home.view",
    "mobile.teacher.availability.update",
    "mobile.teacher.heartbeat.send",
    "mobile.calls.incoming.view",
    "mobile.calls.accept",
    "mobile.calls.reject",
    # Teachers receive calls only — never teachers list / outbound request.
    "mobile.recordings.list_own.view",
]

TEACHER_SHARED_PERMISSIONS = [
    "shared.profile.view",
    "shared.profile.update",
    "shared.profile.avatar.update",
    "shared.recordings.play_own",
    "shared.recordings.download_own",
]

STUDENT_MOBILE_PERMISSIONS = [
    "mobile.nav.home.view",
    "mobile.nav.teachers.view",
    "mobile.nav.recordings.view",
    "mobile.nav.settings.view",
    "mobile.nav.subscriptions.view",
    "mobile.teachers.list.view",
    "mobile.teachers.profile.view",
    "mobile.teachers.favorite.toggle",
    "mobile.subscriptions.packages.view",
    "mobile.subscriptions.status.view",
    "mobile.subscriptions.checkout.create",
    "mobile.calls.request",
    "mobile.evaluations.submit",
]

STUDENT_SHARED_PERMISSIONS = [
    "shared.profile.view",
    "shared.profile.update",
    "shared.profile.avatar.update",
    "shared.recordings.play_own",
    "shared.recordings.download_own",
]


def _permission_module(code: str) -> str:
    """Derive Permission.module from code prefix."""
    parts = code.split(".")
    if not parts:
        return ""
    prefix = parts[0]
    if prefix in {"web", "mobile", "shared"}:
        return prefix
    rbac_submodules = {"users", "roles", "permissions"}
    if prefix == "rbac" or (len(parts) > 1 and parts[0] == "rbac"):
        if len(parts) > 1 and parts[1] in rbac_submodules:
            return parts[1]
        return "rbac"
    return prefix


def _dedupe_preserve_order(codes: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for code in codes:
        if code not in seen:
            seen.add(code)
            result.append(code)
    return result


class Command(BaseCommand):
    help = "Seed default roles and permissions for RBAC"

    @transaction.atomic
    def handle(self, *args, **options):
        permissions_data = (
            LEGACY_PERMISSIONS + WEB_PERMISSIONS + MOBILE_PERMISSIONS + SHARED_PERMISSIONS
        )

        all_legacy_codes = [code for code, _ in LEGACY_PERMISSIONS]
        all_web_codes = [code for code, _ in WEB_PERMISSIONS]
        all_mobile_codes = [code for code, _ in MOBILE_PERMISSIONS]
        all_shared_codes = [code for code, _ in SHARED_PERMISSIONS]
        all_codes = [code for code, _ in permissions_data]

        admin_permissions = _dedupe_preserve_order(all_codes)

        supervisor_permissions = _dedupe_preserve_order(
            SUPERVISOR_LEGACY_PERMISSIONS
            + SUPERVISOR_WEB_PERMISSIONS
            + SUPERVISOR_MOBILE_PERMISSIONS
            + SUPERVISOR_SHARED_PERMISSIONS
        )

        teacher_permissions = _dedupe_preserve_order(
            TEACHER_MOBILE_PERMISSIONS + TEACHER_SHARED_PERMISSIONS
        )

        student_permissions = _dedupe_preserve_order(
            STUDENT_MOBILE_PERMISSIONS + STUDENT_SHARED_PERMISSIONS
        )

        roles_data = {
            "admin": {
                "name": "مدير النظام",
                "permissions": admin_permissions,
            },
            "supervisor": {
                "name": "مشرف",
                "permissions": supervisor_permissions,
            },
            "student": {
                "name": "طالب",
                "permissions": student_permissions,
            },
            "teacher": {
                "name": "معلم",
                "permissions": teacher_permissions,
            },
        }

        perms_map = {}

        for code, name in permissions_data:
            module = _permission_module(code)

            perm, _ = Permission.objects.get_or_create(
                code=code,
                defaults={"name": name, "module": module},
            )
            changed = False
            if perm.name != name:
                perm.name = name
                changed = True
            if perm.module != module:
                perm.module = module
                changed = True
            if changed:
                perm.save()
            perms_map[code] = perm

        for slug, data in roles_data.items():
            role, _ = Role.objects.get_or_create(
                slug=slug,
                defaults={"name": data["name"]},
            )
            if role.name != data["name"]:
                role.name = data["name"]
                role.save()
            role.permissions.set(
                [perms_map[p] for p in data["permissions"] if p in perms_map]
            )

        self._sync_user_roles()

        self.stdout.write(self.style.SUCCESS("RBAC seeded successfully."))
        self.stdout.write(
            f"  Legacy permissions: {len(all_legacy_codes)}"
        )
        self.stdout.write(
            f"  New web permissions: {len(all_web_codes)}"
        )
        self.stdout.write(
            f"  New mobile permissions: {len(all_mobile_codes)}"
        )
        self.stdout.write(
            f"  New shared permissions: {len(all_shared_codes)}"
        )
        self.stdout.write(f"  Total permissions: {len(all_codes)}")
        for slug, data in roles_data.items():
            self.stdout.write(
                f"  Role '{slug}': {len(data['permissions'])} permissions"
            )

    def _sync_user_roles(self):
        """Align roles with user_type; remove legacy participant role."""
        participant = Role.objects.filter(slug="participant").first()
        if participant:
            participant.delete()

        role_by_slug = {r.slug: r for r in Role.objects.all()}

        for user in User.objects.filter(user_type=USER_TYPE_STUDENT):
            role = role_by_slug.get("student")
            if role:
                user.roles.set([role])

        for user in User.objects.filter(user_type=USER_TYPE_TEACHER):
            role = role_by_slug.get("teacher")
            if role:
                user.roles.set([role])

        for user in User.objects.filter(user_type=USER_TYPE_SUPERVISOR):
            role = role_by_slug.get("supervisor")
            if role and not user.roles.filter(slug="supervisor").exists():
                user.roles.add(role)

        for user in User.objects.filter(user_type=USER_TYPE_ADMIN):
            role = role_by_slug.get("admin")
            if role:
                user.roles.add(role)

        for user in User.objects.filter(is_superuser=True):
            role = role_by_slug.get("admin")
            if role:
                user.roles.add(role)
