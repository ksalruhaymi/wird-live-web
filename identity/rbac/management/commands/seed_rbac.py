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


class Command(BaseCommand):
    help = "Seed default roles and permissions for RBAC"

    @transaction.atomic
    def handle(self, *args, **options):
        permissions_data = [
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
            ("roles.view", "عرض الأدوار"),
            ("permissions.view", "عرض الصلاحيات"),
            ("permissions.assign", "ربط الصلاحيات بالأدوار"),
            # Teachers / calls
            ("teachers.view", "عرض المعلمين"),
            ("teachers.update", "تعديل المعلمين"),
            ("teachers.availability.view", "عرض حالة المعلمين"),
            ("calls.view", "عرض سجل المكالمات"),
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
            # Quran studio
            ("quran_studio.access", "الوصول إلى استوديو القرآن"),
            ("quran_studio.coordinate", "احداثيات القرآن"),
            ("quran_studio.qurra", "القراء"),
            ("quran_studio.qurra_create", "إضافة قارئ"),
            ("quran_studio.qurra_update", "تعديل بيانات قارئ"),
            ("quran_studio.qurra_delete", "حذف بيانات قارئ"),
        ]

        all_codes = [code for code, _ in permissions_data]

        # Supervisor (مشرف): view/create/update/toggle on dashboard modules; no delete.
        supervisor_permissions = [
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
            "teachers.availability.view",
            "evaluations.view",
            "evaluations.create",
            "evaluations.update",
            "recordings.view",
        ]

        roles_data = {
            "admin": {
                "name": "مدير النظام",
                "permissions": all_codes,
            },
            "supervisor": {
                "name": "مشرف",
                "permissions": supervisor_permissions,
            },
            "student": {
                "name": "طالب",
                "permissions": [],
            },
            "teacher": {
                "name": "معلم",
                "permissions": [],
            },
        }

        rbac_submodules = {"users", "roles", "permissions"}
        perms_map = {}

        for code, name in permissions_data:
            parts = code.split(".")
            if parts[0] == "rbac":
                if len(parts) > 1 and parts[1] in rbac_submodules:
                    module = parts[1]
                else:
                    module = "rbac"
            else:
                module = parts[0]

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
