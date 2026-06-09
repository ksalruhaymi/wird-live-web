# نشر مشروع وِرد لايف (Hostinger)

توثيق نشر **wird-live-web** على السيرفر ورفع **APK** الجوال عند تغيير الإصدار.

---

## معلومات السيرفر

| العنصر | القيمة |
|---|---|
| مسار المشروع (Git) | `/var/www/wird-live-web/src` |
| مجلد media | `/var/www/wird-live-web/media` |
| مجلد APK | `/var/www/wird-live-web/media/mobile` |
| رابط APK | `https://live.wird.me/media/mobile/<filename>.apk` |
| البيئة الافتراضية | `/var/www/wird-live-web/venv` |
| خدمة systemd | `wird-live.service` |
| المستخدم | `ksalruhaymi` |
| عنوان السيرفر (SCP) | `187.124.177.246` |

> **تنبيه:** لا يُنفَّذ `git pull` من `/home/ksalruhaymi`. المسار الصحيح دائماً:
> `/var/www/wird-live-web/src`

> **تنبيه:** مجلد `media` **ليس** داخل `src`، بل في:
> `/var/www/wird-live-web/media`

---

## 1) نشر تعديلات wird-live-web

عند وجود تعديلات مرفوعة إلى GitHub (`main`):

```bash
cd /var/www/wird-live-web/src

git status
git pull origin main

source /var/www/wird-live-web/venv/bin/activate
export APP_ENV=prod
export DJANGO_SETTINGS_MODULE=config.settings

python manage.py check
python manage.py collectstatic --noinput

sudo systemctl restart wird-live.service
sudo systemctl reload nginx

git status
```

### إن وُجدت migrations جديدة

نفّذ قبل `collectstatic` (أو بعد `check`):

```bash
python manage.py migrate
```

### التحقق من النجاح

- `git status` يظهر: `Your branch is up to date with 'origin/main'`
- `python manage.py check` بدون أخطاء
- الموقع يعمل: https://live.wird.me

---

## 2) نشر إصدار جديد للجوال (wird-live-mobile)

ملفات **APK لا تُرفع إلى GitHub**. تُرفع مباشرة إلى السيرفر.

### الخطوة 1 — تحديث الإصدار

في `pubspec.yaml` (مثال):

```yaml
version: 1.0.0+4
```

- `1.0.0` = رقم الإصدار (version)
- `4` = رقم البناء (build number)

### الخطوة 2 — بناء APK (على جهاز التطوير)

```bash
cd /path/to/wird-live-mobile

flutter pub get
flutter analyze
flutter build apk --release
```

### الخطوة 3 — تسمية الملف ونسخه

```bash
cp build/app/outputs/flutter-apk/app-release.apk ~/Desktop/wird-live-1.0.0-build4.apk
```

الصيغة المقترحة للاسم:

```
wird-live-<version>-build<build_number>.apk
```

مثال: `wird-live-1.0.0-build4.apk`

### الخطوة 4 — رفع APK إلى السيرفر

```bash
scp ~/Desktop/wird-live-1.0.0-build4.apk ksalruhaymi@187.124.177.246:/var/www/wird-live-web/media/mobile/
```

### الخطوة 5 — اختبار الرابط

```bash
curl -I https://live.wird.me/media/mobile/wird-live-1.0.0-build4.apk
```

إذا ظهر `HTTP/2 200` (أو `HTTP/1.1 200`) يكون الرابط صحيحاً.

---

## 3) إعداد لوحة التحكم بعد رفع APK

من **إعدادات تطبيق الجوال** داخل لوحة وِرد لايف:

| الحقل | مثال |
|---|---|
| minimum version | `1.0.0` |
| minimum build number | `4` (رقم البناء الجديد) |
| force update | `true` (إذا أردت إجبار التحديث) |
| update URL | `https://live.wird.me/media/mobile/wird-live-1.0.0-build4.apk` |
| message | هذه النسخة انتهت، فضلاً حمّل النسخة الجديدة. |

---

## 4) قواعد ثابتة — لا تُغيَّر

| المنصة | المعرف |
|---|---|
| Android applicationId | `com.kslabs.wirdlive` |
| iOS Bundle ID | `com.kslabs.wirdlive` |
| Flutter package name | `wird_live` |

---

## 5) ملخص سريع

| المهمة | الأمر/المسار |
|---|---|
| سحب الويب | `git pull` من `/var/www/wird-live-web/src` |
| إعادة تشغيل التطبيق | `sudo systemctl restart wird-live.service` |
| رفع APK | `scp` → `/var/www/wird-live-web/media/mobile/` |
| رابط التحميل | `https://live.wird.me/media/mobile/<filename>.apk` |

---

## 6) استكشاف الأخطاء

| المشكلة | الحل المحتمل |
|---|---|
| `git pull` لا يجد تغييرات | تأكد أنك في `/var/www/wird-live-web/src` وليس `/home/ksalruhaymi` |
| APK يعطي 404 | تحقق من وجود الملف في `/var/www/wird-live-web/media/mobile/` وصلاحيات القراءة |
| الموقع لا يعمل بعد النشر | `sudo systemctl status wird-live.service` و `sudo journalctl -u wird-live.service -n 50` |
| static لا يتحدث | أعد `collectstatic` ثم `reload nginx` |
