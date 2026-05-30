#!/usr/bin/env python3
"""
Translate missing .po file entries from English using Google Translate.
Run from the src/ directory:
    python translate_missing.py [lang_code ...]

If no args given, processes all incomplete languages.
"""

import os
import sys
import time
import re
import polib
from deep_translator import GoogleTranslator

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCALE_DIR = os.path.join(BASE_DIR, "locale")
EN_PO = os.path.join(LOCALE_DIR, "en", "LC_MESSAGES", "django.po")

# Django locale code → Google Translate code
GT_CODE = {
    "es":  "es",
    "fa":  "fa",
    "fil": "tl",
    "ja":  "ja",
    "zh":  "zh-CN",
    "nl":  "nl",
    "vi":  "vi",
    "as":  "as",
    "si":  "si",
    "so":  "so",
    # Full languages – already have .mo but let's keep them for completeness
    "ar":  "ar",
    "de":  "de",
    "fr":  "fr",
    "hi":  "hi",
    "id":  "id",
    "ur":  "ur",
}

# Languages that need full translation (no .mo yet or < 100 strings)
INCOMPLETE = ["es", "fa", "fil", "ja", "zh", "nl", "vi", "as", "si", "so"]

# ── helpers ──────────────────────────────────────────────────────────────────

SEPARATOR = "\n|||SPLIT|||\n"

def is_translatable(s: str) -> bool:
    """Return True if string should be sent to Google Translate."""
    if not s or not s.strip():
        return False
    # Pure numbers / punctuation
    if re.fullmatch(r"[\d\s\W]+", s):
        return False
    return True


def translate_batch(texts: list[str], lang: str) -> list[str]:
    """Translate a list of strings, keeping order. Retries on error."""
    gt_lang = GT_CODE.get(lang, lang)
    joined = SEPARATOR.join(texts)
    max_chunk = 4800  # Google Translate safe limit

    # If joined text is too long, split recursively
    if len(joined) > max_chunk:
        mid = len(texts) // 2
        if mid == 0:
            # Single very long string – truncate-translate
            mid = 1
        left  = translate_batch(texts[:mid], lang)
        right = translate_batch(texts[mid:], lang)
        return left + right

    for attempt in range(4):
        try:
            translator = GoogleTranslator(source="en", target=gt_lang)
            result = translator.translate(joined)
            parts = result.split("|||SPLIT|||")
            parts = [p.strip("\n ") for p in parts]
            if len(parts) == len(texts):
                return parts
            # Mismatch – fall back to 1-by-1
            break
        except Exception as e:
            wait = 2 ** attempt
            print(f"    [retry {attempt+1}] {e} – waiting {wait}s")
            time.sleep(wait)

    # One-by-one fallback
    out = []
    for t in texts:
        for attempt in range(3):
            try:
                tr = GoogleTranslator(source="en", target=gt_lang).translate(t)
                out.append(tr or t)
                time.sleep(0.25)
                break
            except Exception as e:
                if attempt == 2:
                    print(f"    [SKIP] {e} – keeping original")
                    out.append(t)
                else:
                    time.sleep(2 ** attempt)
    return out


# ── main logic ───────────────────────────────────────────────────────────────

def process_language(lang: str):
    print(f"\n{'='*60}")
    print(f"  Language: {lang}")
    print(f"{'='*60}")

    po_path = os.path.join(LOCALE_DIR, lang, "LC_MESSAGES", "django.po")
    mo_path = os.path.join(LOCALE_DIR, lang, "LC_MESSAGES", "django.mo")

    # Load English source
    en_po = polib.pofile(EN_PO)
    en_map = {e.msgid: e.msgstr for e in en_po if e.msgid}

    # Load or create target .po
    os.makedirs(os.path.dirname(po_path), exist_ok=True)
    if os.path.exists(po_path):
        target_po = polib.pofile(po_path)
        target_map = {e.msgid: e for e in target_po}
    else:
        target_po = polib.POFile()
        target_po.metadata = {
            "Project-Id-Version":        "wird",
            "Language":                  lang,
            "MIME-Version":              "1.0",
            "Content-Type":              "text/plain; charset=UTF-8",
            "Content-Transfer-Encoding": "8bit",
        }
        target_map = {}

    # Collect entries that need translation
    need_translation: list[tuple[str, str]] = []  # (msgid, english_msgstr)
    for entry in en_po:
        if not entry.msgid:
            continue
        en_str = entry.msgstr
        existing = target_map.get(entry.msgid)
        if existing and existing.msgstr.strip():
            continue  # already translated
        if not is_translatable(en_str):
            continue
        need_translation.append((entry.msgid, en_str))

    print(f"  Strings to translate: {len(need_translation)}")

    if not need_translation:
        print("  Nothing to do – already complete.")
        return

    # Translate in batches of 30
    BATCH = 30
    translated_map: dict[str, str] = {}

    for i in range(0, len(need_translation), BATCH):
        batch = need_translation[i : i + BATCH]
        msgids  = [x[0] for x in batch]
        en_strs = [x[1] for x in batch]

        pct = int((i / len(need_translation)) * 100)
        print(f"  [{pct:3d}%] Translating batch {i//BATCH + 1} ({len(batch)} items)…")

        results = translate_batch(en_strs, lang)
        for mid, res in zip(msgids, results):
            translated_map[mid] = res

        time.sleep(0.5)  # gentle rate-limit

    # Write results back into the .po file
    for entry in en_po:
        if not entry.msgid:
            continue
        new_str = translated_map.get(entry.msgid)
        existing = target_map.get(entry.msgid)

        if existing:
            if new_str and not existing.msgstr.strip():
                existing.msgstr = new_str
        else:
            new_entry = polib.POEntry(msgid=entry.msgid)
            if new_str:
                new_entry.msgstr = new_str
            elif not is_translatable(entry.msgstr):
                new_entry.msgstr = entry.msgstr  # keep as-is
            else:
                new_entry.msgstr = ""
            target_po.append(new_entry)
            target_map[entry.msgid] = new_entry

    target_po.save(po_path)
    print(f"  Saved: {po_path}")

    # Compile .mo
    try:
        target_po.save_as_mofile(mo_path)
        print(f"  Compiled: {mo_path}")
    except Exception as e:
        print(f"  [WARN] Could not compile .mo: {e}")

    # Stats
    total      = sum(1 for e in target_po if e.msgid)
    translated = sum(1 for e in target_po if e.msgid and e.msgstr.strip())
    print(f"  Done: {translated}/{total} strings translated")


# ── entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    targets = sys.argv[1:] if len(sys.argv) > 1 else INCOMPLETE

    # Validate
    for lang in targets:
        if lang not in GT_CODE:
            print(f"[ERROR] Unknown language code: {lang}")
            print(f"  Known: {list(GT_CODE.keys())}")
            sys.exit(1)

    print(f"Processing {len(targets)} language(s): {targets}")

    for lang in targets:
        process_language(lang)

    print("\n\nAll done.")
