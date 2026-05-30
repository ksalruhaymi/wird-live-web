# نظام المستخدمين والأدوار والصلاحيات (accounts + rbac)

## 1. الفكرة العامة (بالعربي)

هذا النظام يوفر طبقة جاهزة لإدارة:

- المستخدمين (Users) عبر تطبيق `accounts`
- الأدوار (Roles) عبر تطبيق `rbac`
- الصلاحيات (Permissions) عبر تطبيق `rbac`
- دوال جاهزة للتحقق من الصلاحيات:
  - `user.has_permission("code")`
  - `user.has_role("slug")`
- Decorators و Mixins و Template Tags للاستخدام في:
  - الـ Views (دوال + كلاس)
  - القوالب (templates)
  - لوحة التحكم

يمكن نسخ `accounts` و `rbac` لأي مشروع Django جديد واستخدامهما كنظام RBAC جاهز.

---

## 2. المتطلبات

- Python 3.10+
- Django 4 أو 5 أو 6
- مشروع Django موجود مسبقًا به `settings` و `urls` و `manage.py`

---

## 3. تركيب النظام في مشروع جديد

### 3.1 نسخ التطبيقات

انسخ المجلدات التالية إلى داخل مشروعك (عادةً بجانب `core` أو داخل `src`):

- `accounts/`
- `rbac/`

تأكد من وجود الملفات التالية على الأقل:

- `accounts/models.py` فيه الموديل `User`
- `accounts/admin.py`
- `rbac/models.py` فيه `Role` و `Permission`
- `rbac/admin.py`
- `rbac/decorators.py`
- `rbac/mixins.py`
- `rbac/templatetags/rbac_tags.py`
- `rbac/management/commands/seed_rbac.py`

---

### 3.2 إعدادات Django

في ملف الإعدادات (مثل `web/settings/base.py` أو `settings.py`):

```python
INSTALLED_APPS = [
    # Django apps
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Project apps
    "accounts",
    "rbac",
]

AUTH_USER_MODEL = "accounts.User"
