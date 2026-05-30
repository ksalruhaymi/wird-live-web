from django.core.management.base import BaseCommand
from django.db import transaction

from identity.rbac.models import Role, Permission


class Command(BaseCommand):
    help = "Seed default roles and permissions for RBAC"

    @transaction.atomic
    def handle(self, *args, **options):
        # ===== Permissions =====
        # NOTE: Keep these codes in sync with your view decorators.

        permissions_data = [
                ("dashboard.access", "لوحة التحكم"),
                ("rbac.access", "إدارة الصلاحيات"),

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

                ("settings.access", "إدارة إعدادات تسجيل الدخول"),
                ("overview.access", "الوصول إلى لوحة المعلومات"),

                ("analytics.access", "الوصول إلى التحليلات"),
                ("overview.access", "الوصول إلى لوحة المعلومات"),



                ("notification.access", "الوصول إلى التنبيهات"),
                ("notification.create", " إرسال تنبيه "),
                ("notification.inapp", "عرض التنبيهات الداخلية"),

                ("messaging.access", "الوصول إلى قنوات الإرسال"),
                ("messaging.create", "إنشاء رسالة"),
                ("messaging.email", "عرض البريد الإلكتروني"),
                ("messaging.whatsapp", "عرض رسائل واتساب"),
                ("messaging.sms", "عرض رسائل SMS"),

                ("communication.access", "الوصول للتواصل"),
                ("communication.create", "إنشاء رسالة"),
                ("communication.campaigns", "عرض الحملات"),
                ("communication.logs", "عرض سجل الإرسال"),


                ("contact.access", "الوصول للتواصل"),
                ("contact.list", "عرض رسائل التواصل"),
                ("contact.create", "إنشاء رسالة تواصل"),

                ("subscription.access", "الوصول إلى الاشتراكات"),
                ("subscription.create", "إرسال رسالة"),
                ("subscription.subscriber", "عرض المشتركين"),

                ("quran_studio.access", "الوصول إلى استوديو القرآن"),
                ("quran_studio.coordinate", "احداثيات القرآن"),
                ("quran_studio.qurra", "القراء"),
                ("quran_studio.qurra_create", "إضافة قارئ"),
                ("quran_studio.qurra_update", "تعديل بيانات قارئ"),
                ("quran_studio.qurra_delete", "حذف بيانات قارئ"),
            ]
        # ===== Roles =====
        roles_data = {
            "admin": {
                "name": "Admin",
                # Admin gets all permissions defined above
                "permissions": [code for code, _ in permissions_data],
            },
            "supervisor": {
                "name": "مشرف",
                # Participant: basic access, no RBAC, no users management
                "permissions": ["dashboard.access",],
            },
            "participant": {
                "name": "مشارك",
                # Participant: basic access, no RBAC, no users management
                "permissions": ["dashboard.access",],
            },
        }

        # RBAC submodules mapping for module field
        RBAC_SUBMODULES = {"users", "roles", "permissions"}

        # Create / get permissions
        perms_map = {}
        for code, name in permissions_data:
            parts = code.split(".")

            # Determine module based on RBAC or non-RBAC codes
            if parts[0] == "rbac":
                if len(parts) > 1 and parts[1] in RBAC_SUBMODULES:
                    module = parts[1]  # users / roles / permissions
                else:
                    module = "rbac"    # core rbac.*
            else:
                # Non-RBAC permissions keep their own module from the first segment
                module = parts[0]

            perm, created = Permission.objects.get_or_create(
                code=code,
                defaults={
                    "name": name,
                    "module": module,
                },
            )

            # Idempotent update for name and module
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

        # Create / get roles and attach permissions
        for slug, data in roles_data.items():
            role, _ = Role.objects.get_or_create(
                slug=slug,
                defaults={"name": data["name"]},
            )
            role.permissions.set(
                [perms_map[p] for p in data["permissions"] if p in perms_map]
            )
            role.save()

        self.stdout.write(self.style.SUCCESS("RBAC seeded successfully."))
