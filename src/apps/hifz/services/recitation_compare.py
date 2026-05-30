import re
from difflib import SequenceMatcher


ARABIC_DIACRITICS_RE = re.compile(r"[ً-ٰٟۖ-ۭ]")
PUNCT_RE = re.compile(r"[^\w\s؀-ۿ]")
WORD_RE = re.compile(r"[؀-ۿ]+")

PHONETIC_GROUPS = {
    "heavy_letters": set("خصضغطقظ"),
    "light_s_family": {"س", "ص", "ث", "ز", "ذ", "ظ"},
    "hamza_family": {"ا", "أ", "إ", "آ", "ء", "ؤ", "ئ"},
    "taa_family": {"ت", "ط"},
    "dal_family": {"د", "ض", "ظ", "ذ"},
    "haa_family": {"ه", "ح", "خ"},
    "ain_family": {"ع", "ء", "ا"},
}

MAD_LETTERS = set(["ا", "و", "ي", "ى"])


def strip_diacritics(text: str) -> str:
    return ARABIC_DIACRITICS_RE.sub("", text or "")


def normalize_quran_text(text: str) -> str:
    if not text:
        return ""

    text = text.strip()
    text = strip_diacritics(text)
    text = PUNCT_RE.sub(" ", text)

    replacements = {
        "ٱ": "ا",
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ى": "ي",
        "ة": "ه",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = " ".join(text.split())
    return text


def tokenize_arabic_words(text: str) -> list[str]:
    return WORD_RE.findall(text or "")


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a or "", b or "").ratio()


def _shared_word_ratio(expected_words: list[str], actual_words: list[str]) -> float:
    if not expected_words or not actual_words:
        return 0.0

    expected_set = set(expected_words)
    actual_set = set(actual_words)
    shared = expected_set.intersection(actual_set)

    return len(shared) / max(len(expected_set), 1)


def _is_unrelated_recitation(
    expected_text: str,
    actual_text: str,
    expected_words: list[str],
    actual_words: list[str],
) -> bool:
    if not actual_text.strip():
        return True

    char_ratio = similarity(expected_text, actual_text)
    word_ratio = _shared_word_ratio(expected_words, actual_words)

    if len(actual_words) == 1:
        return char_ratio < 0.20 and word_ratio == 0

    if len(actual_words) >= 2 and word_ratio == 0 and char_ratio < 0.30:
        return True

    if len(actual_words) >= 3 and char_ratio < 0.25:
        return True

    return False


def classify_word_error(expected_word: str, actual_word: str) -> tuple[str, str]:
    if not actual_word:
        return (
            "missing",
            "يوجد حذف لكلمة كاملة، أعد قراءة الكلمة بهدوء مع وصلها بما قبلها وما بعدها.",
        )

    if expected_word == actual_word:
        return ("correct", "")

    if len(actual_word) > len(expected_word) and expected_word in actual_word:
        return (
            "addition",
            "يبدو أن هناك زيادة صوتية أو تكرارًا زائدًا في الكلمة، حاول التلاوة دون تمديد زائد.",
        )

    if len(expected_word) > len(actual_word) and actual_word and actual_word in expected_word:
        return (
            "missing_part",
            "يبدو أن جزءًا من الكلمة سقط أثناء التلاوة، ركز على إكمال جميع الحروف بوضوح.",
        )

    expected_letters = set(expected_word)
    actual_letters = set(actual_word)

    if (expected_letters & PHONETIC_GROUPS["heavy_letters"]) != (actual_letters & PHONETIC_GROUPS["heavy_letters"]):
        return (
            "tafkheem_tarqeeq",
            "يوجد تبدل محتمل بين حرف مفخم وحرف مرقق، راقب صفة الحرف ولا تُخفف المفخم.",
        )

    if any(letter in expected_letters for letter in MAD_LETTERS) and not any(letter in actual_letters for letter in MAD_LETTERS):
        return (
            "madd",
            "الخطأ يبدو قريبًا من المد، حاول إعطاء حروف المد مقدارها الصحيح دون قصر.",
        )

    if any(letter in expected_letters for letter in PHONETIC_GROUPS["light_s_family"]) and any(
        letter in actual_letters for letter in PHONETIC_GROUPS["light_s_family"]
    ):
        return (
            "sifaat",
            "يوجد تقارب صوتي بين الحروف، ركز على الصفة الدقيقة ومخرج الحرف داخل الكلمة.",
        )

    if any(letter in expected_letters for letter in PHONETIC_GROUPS["haa_family"]) and any(
        letter in actual_letters for letter in PHONETIC_GROUPS["haa_family"]
    ):
        return (
            "makhraj",
            "الخطأ يبدو من مخرج الحرف، خصوصًا في الحروف الحلقية، فأخرج الحرف من موضعه بوضوح.",
        )

    return (
        "substitution",
        "يوجد استبدال أو اضطراب في نطق الكلمة، أعدها ببطء وركز على ترتيب الحروف داخلها.",
    )


def build_word_alignment(expected_words: list[str], actual_words: list[str]) -> list[dict]:
    matcher = SequenceMatcher(None, expected_words, actual_words)
    items: list[dict] = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for idx in range(i2 - i1):
                word = expected_words[i1 + idx]
                items.append({
                    "expected": word,
                    "actual": actual_words[j1 + idx],
                    "status": "correct",
                    "score": 100,
                    "error_type": "correct",
                    "tajweed_tip": "",
                })
            continue

        if tag == "replace":
            left = expected_words[i1:i2]
            right = actual_words[j1:j2]
            max_len = max(len(left), len(right))
            for idx in range(max_len):
                expected_word = left[idx] if idx < len(left) else ""
                actual_word = right[idx] if idx < len(right) else ""
                error_type, tip = classify_word_error(expected_word, actual_word)
                score = round(similarity(expected_word, actual_word) * 100) if expected_word or actual_word else 0
                items.append({
                    "expected": expected_word,
                    "actual": actual_word,
                    "status": "wrong",
                    "score": score,
                    "error_type": error_type,
                    "tajweed_tip": tip,
                })
            continue

        if tag == "delete":
            for word in expected_words[i1:i2]:
                error_type, tip = classify_word_error(word, "")
                items.append({
                    "expected": word,
                    "actual": "",
                    "status": "missing",
                    "score": 0,
                    "error_type": error_type,
                    "tajweed_tip": tip,
                })
            continue

        if tag == "insert":
            for word in actual_words[j1:j2]:
                items.append({
                    "expected": "",
                    "actual": word,
                    "status": "extra",
                    "score": 0,
                    "error_type": "addition",
                    "tajweed_tip": "هناك كلمة زائدة في القراءة الحالية، حاول الالتزام بنص الآية دون إضافة.",
                })

    return items


def build_highlight_parts(alignment: list[dict]) -> tuple[list[dict], list[dict]]:
    expected_parts = []
    actual_parts = []

    for item in alignment:
        status = item["status"]
        expected_parts.append({
            "text": item.get("expected") or "—",
            "status": "correct" if status == "correct" else "wrong",
        })
        actual_parts.append({
            "text": item.get("actual") or "—",
            "status": "correct" if status == "correct" else "wrong",
        })

    return expected_parts, actual_parts


def summarize_errors(alignment: list[dict]) -> tuple[list[dict], str]:
    errors = []

    for item in alignment:
        if item["status"] == "correct":
            continue
        errors.append({
            "expected_word": item.get("expected") or "",
            "recognized_word": item.get("actual") or "",
            "error_type": item.get("error_type") or "substitution",
            "score": item.get("score") or 0,
            "tajweed_tip": item.get("tajweed_tip") or "",
        })

    if not errors:
        return [], "أحسنت، التلاوة مطابقة بشكل كامل تقريبًا."

    first = errors[0]
    focus_word = first["expected_word"] or first["recognized_word"] or "الكلمة"
    return errors, f"يوجد خطأ ظاهر عند كلمة \"{focus_word}\"، ويفضل إعادة المقطع مع التركيز على النطق والصفة."


def analyze_recitation_score(expected_text: str, actual_text: str) -> dict:
    expected_norm = normalize_quran_text(expected_text)
    actual_norm = normalize_quran_text(actual_text)

    expected_words = tokenize_arabic_words(expected_norm)
    actual_words = tokenize_arabic_words(actual_norm)

    if not actual_norm:
        return {
            "score": 0,
            "is_correct": False,
            "message": "لم يتم التقاط صوت واضح.",
            "recognized_text": actual_text.strip(),
            "expected_parts": [{"text": word, "status": "wrong"} for word in expected_words] or [{"text": "—", "status": "wrong"}],
            "recognized_parts": [{"text": "—", "status": "wrong"}],
            "word_analysis": [],
            "errors": [{
                "expected_word": "",
                "recognized_word": "",
                "error_type": "empty",
                "score": 0,
                "tajweed_tip": "تأكد من عمل الميكروفون ثم أعد التسجيل بصوت أوضح.",
            }],
        }

    if _is_unrelated_recitation(expected_norm, actual_norm, expected_words, actual_words):
        expected_parts = [{"text": word, "status": "wrong"} for word in expected_words] or [{"text": "—", "status": "wrong"}]
        recognized_parts = [{"text": word, "status": "wrong"} for word in actual_words] or [{"text": "—", "status": "wrong"}]

        return {
            "score": 0,
            "is_correct": False,
            "message": "القراءة لا تطابق الآية المطلوبة، ويبدو أن المقطع المقروء غير متعلق بالنص المرجعي.",
            "recognized_text": actual_text.strip(),
            "expected_parts": expected_parts,
            "recognized_parts": recognized_parts,
            "word_analysis": [],
            "errors": [{
                "expected_word": expected_words[0] if expected_words else "",
                "recognized_word": actual_words[0] if actual_words else "",
                "error_type": "not_related",
                "score": 0,
                "tajweed_tip": "ابدأ بقراءة الآية نفسها أولًا، ثم أعد التسجيل بوضوح وتركيز.",
            }],
        }

    ratio = similarity(expected_norm, actual_norm)
    score = round(ratio * 100)

    alignment = build_word_alignment(expected_words, actual_words)
    expected_parts, actual_parts = build_highlight_parts(alignment)
    errors, summary = summarize_errors(alignment)

    is_correct = len(errors) == 0 and score >= 98

    return {
        "score": score,
        "is_correct": is_correct,
        "message": "ممتاز" if is_correct else summary,
        "recognized_text": actual_text.strip(),
        "expected_parts": expected_parts,
        "recognized_parts": actual_parts,
        "word_analysis": alignment,
        "errors": errors,
    }