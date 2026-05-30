#!/usr/bin/env python3
"""
1. Add read_quran / support / footer_links to all existing complete .po files
2. Fix tilawa / translations / contact_us in those files
3. Translate the 3 new keys for incomplete languages (fa included)
4. Recompile every .mo
Run AFTER the background translate_missing.py has finished.
"""

import os
import time
import polib
from deep_translator import GoogleTranslator

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCALE_DIR = os.path.join(BASE_DIR, "locale")

# New keys: msgid → {lang: translation}
NEW_KEYS = {
    "read_quran": {
        "en": "Read Quran",
        "ar": "قراءة القرآن",
        "de": "Koran lesen",
        "fr": "Lire le Coran",
        "hi": "क़ुरान पढ़ें",
        "id": "Baca Al-Quran",
        "ur": "قرآن پڑھیں",
    },
    "support": {
        "en": "Support",
        "ar": "الدعم",
        "de": "Support",
        "fr": "Support",
        "hi": "सहायता",
        "id": "Dukungan",
        "ur": "مدد",
    },
    "footer_links": {
        "en": "Footer links",
        "ar": "روابط التذييل",
        "de": "Fußzeilen-Links",
        "fr": "Liens de pied de page",
        "hi": "फ़ुटर लिंक",
        "id": "Tautan footer",
        "ur": "فوٹر لنکس",
    },
}

# Arabic fixes: msgid → correct Arabic msgstr
AR_FIXES = {
    "tilawa":       "التلاوات",
    "translations": "الترجمات",
    "contact_us":   "تواصل معنا",
}

# All languages on the site
ALL_LANGS = ["ar", "de", "en", "es", "fa", "fil", "fr", "hi", "id",
             "ja", "nl", "si", "so", "ur", "vi", "zh", "as"]

GT_CODE = {
    "es":  "es", "fa":  "fa", "fil": "tl", "ja":  "ja",
    "zh":  "zh-CN", "nl":  "nl", "vi":  "vi", "as":  "as",
    "si":  "si", "so":  "so", "de":  "de", "fr":  "fr",
    "hi":  "hi", "id":  "id", "ur":  "ur",
}


def translate_one(text: str, lang: str) -> str:
    gt = GT_CODE.get(lang, lang)
    for attempt in range(3):
        try:
            result = GoogleTranslator(source="en", target=gt).translate(text)
            return result or text
        except Exception as e:
            if attempt == 2:
                print(f"    [WARN] translate {lang}: {e}")
                return text
            time.sleep(2 ** attempt)
    return text


def process(lang: str):
    po_path = os.path.join(LOCALE_DIR, lang, "LC_MESSAGES", "django.po")
    mo_path = os.path.join(LOCALE_DIR, lang, "LC_MESSAGES", "django.mo")

    if not os.path.exists(po_path):
        print(f"  [{lang}] SKIP – no .po file")
        return

    po = polib.pofile(po_path)
    entry_map = {e.msgid: e for e in po}
    changed = False

    # 1. Fix existing entries (tilawa, translations, contact_us) for Arabic only
    if lang == "ar":
        for msgid, correct_str in AR_FIXES.items():
            entry = entry_map.get(msgid)
            if entry and entry.msgstr != correct_str:
                print(f"  [{lang}] fix  '{msgid}': '{entry.msgstr}' → '{correct_str}'")
                entry.msgstr = correct_str
                changed = True

    # 2. Add / update new keys
    for msgid, translations in NEW_KEYS.items():
        entry = entry_map.get(msgid)
        desired = translations.get(lang)

        if desired is None:
            # Need to translate from English
            print(f"  [{lang}] translate new key '{msgid}'…")
            desired = translate_one(translations["en"], lang)
            time.sleep(0.3)

        if entry is None:
            new_entry = polib.POEntry(msgid=msgid, msgstr=desired)
            po.append(new_entry)
            print(f"  [{lang}] add  '{msgid}' = '{desired}'")
            changed = True
        elif not entry.msgstr.strip():
            entry.msgstr = desired
            print(f"  [{lang}] fill '{msgid}' = '{desired}'")
            changed = True

    if changed:
        po.save(po_path)

    # Always recompile .mo
    try:
        po.save_as_mofile(mo_path)
        print(f"  [{lang}] compiled .mo ✓")
    except Exception as e:
        print(f"  [{lang}] [WARN] .mo failed: {e}")


if __name__ == "__main__":
    print("Fixing nav/footer keys in all languages…\n")
    for lang in ALL_LANGS:
        print(f"── {lang} ──")
        process(lang)
    print("\nDone.")
