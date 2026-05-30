# Quran API (`v1`)

**المسار المعتمد:** `https://<النطاق>/api/v1/…`

نفس مسارات الـ API موجودة أيضًا تحت **`/api/…`** (بدون إصدار) في الإعداد الحالي؛ **يُفضَّل اعتماد `v1`** للعملاء الجدد ولتخطيط إصدارات لاحقة (`v2`…).

---

## المصادقة

جميع نقاط Quran API محمية بـ **`require_api_key`**:

| الطريقة | مثال |
|--------|------|
| ترويسة | `X-API-KEY: <المفتاح>` |
| استعلام | `?api_key=<المفتاح>` |

المفاتيح الصالحة تُعرَّف في Django في **`QURAN_API_KEYS`** (قائمة مفاتيح). أضِف مفتاحًا سريًا تولّده أنت ثم استخدمه بنفس القيمة في العميل (مثل ثابت **`apiKey`** في `Flutter …/api_config.dart`) حتى يعمل التطبيق ضد الخادم.

استجابة الرفض: **401** مع `{"detail": "Invalid or missing API key."}`.

مثال اختبار بعد وضع المفتاح في **`QURAN_API_KEYS`**:

```bash
curl -s "http://127.0.0.1:8000/api/v1/surahs/?api_key=ضع_المفتاح_الخاص_بك_هنا"
```

---

## أمثلة محلية (`runserver`)

الجذر: `http://127.0.0.1:8000` — أضِف **`?api_key=<مفتاحك>`** حيث يلزم (أو الترويسة **`X-API-KEY`**).

### سور وآيات وصفحات

| الوصف | المسار |
|--------|--------|
| قائمة السور | `GET /api/v1/surahs/` |
| سورة معيّنة | `GET /api/v1/surahs/<surah_number>/` |
| آيات سورة | `GET /api/v1/surahs/<surah_number>/ayahs/` |
| قائمة آيات (مع فلاتر اختيارية) | `GET /api/v1/ayahs/?surah=&page=&juz=` |
| آية بالمعرّف الداخلي | `GET /api/v1/ayahs/<pk>/` — **`pk`** = مفتاح السجل في الجدول وليس بالضرورة «رقم الآية في السورة» |
| صفحة مصحف (آيات + إحداثيات) | `GET /api/v1/pages/<page_number>/?mushaf=hafs` — **`mushaf`** اختياري (الافتراضي من الخادم مثل حفص) |
| إحداثيات صفحة | `GET /api/v1/pages/<page_number>/positions/?mushaf=hafs` |
| إحداثيات آية | `GET /api/v1/ayahs/<surah_number>/<ayah_number>/positions/?mushaf=hafs` |

### تفسير

| الوصف | المسار |
|--------|--------|
| كتب التفسير | `GET /api/v1/tafsir/books/` |
| كتاب | `GET /api/v1/tafsir/books/<id>/` |
| تفسير بكتاب + سورة + آية | `GET /api/v1/tafsir/books/<book_id>/surahs/<surah_number>/ayahs/<ayah_number>/` |
| تفسير حسب رقم آية (عمود في النموذج) | `GET /api/v1/ayahs/<ayah_number>/tafsir/` — قد يكون غامضًا إن تكرّر رقم الآية بين السور |

### القرّاء والميتا والصوت والميزات

| الوصف | المسار |
|--------|--------|
| قائمة القرّاء | `GET /api/v1/qurra/` |
| قارئ | `GET /api/v1/qurra/<id>/` |
| إعدادات ميتا (مصاحف افتراضية إلخ) | `GET /api/v1/meta/config/` |
| كتالوج مصاحف (JSON) | `GET /api/v1/mushafs/` |
| أعلام مزايا للعميل | `GET /api/v1/features/` |
| أكواد قرّاء لديهم صوت لمصحف | `GET /api/v1/audio/readers/?mushaf=hafs` — **`mushaf` مطلوب** (بدونها 400) |

### بحث

المعامل **`query`** (وليس `q`):

```
GET /api/v1/search/ayahs/?query=رحمن&api_key=...
GET /api/v1/search/tafsir/?query=صبر&api_key=...
```

للنصوص العربية في الروابط يُفضّل الترميز كما يفعل المتصفح (UTF-8).

---

## إنتاج (مثال)

| النوع | مثال |
|--------|------|
| API | `https://wird.me/api/v1/surahs/?api_key=...` |
| صور صفحات المصحف | `https://wird.me/media/mushaf/hafs/001.webp` (أو `.png` حسب الملفات على الخادم) |
| صور القرّاء | `https://wird.me/media/images/qurra/<اسم_الملف>` |
| صوت آية | `https://wird.me/media/audio/<mushaf>/<قارئ>/<سورة>/<سورة><آية>.mp3` مثل: `.../hafs/maher_almuaiqly/001/001001.mp3` |

---

## ملاحظات

- **ترتيب المسارات في `urls.py`:** `ayahs/<pk>/` يختلف عن `ayahs/<surah>/<ayah>/positions/`؛ الروابط أعلاه تطابق التعريف الحالي.
- بعد تعديل **Python أو المسارات** على الخادم: انشر التطبيق وأعد التشغيل (وما يلزم من **migrate**).
