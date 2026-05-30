"""Literal translation markers for dynamic template keys extracted by makemessages."""

from django.utils.translation import gettext_lazy as _

# Mushaf display titles (referenced via mushaf_config title_key and {% translate %}).
MUSHAF_TITLE_HAFS = _("mushaf_hafs")
MUSHAF_TITLE_WARSH = _("mushaf_warsh")
MUSHAF_TITLE_QALOUN = _("mushaf_qaloun")
MUSHAF_TITLE_DOURI = _("mushaf_douri")
MUSHAF_TITLE_SHUBA = _("mushaf_shuba")
MUSHAF_TITLE_SOUSI = _("mushaf_sousi")

# Tafsir book display titles (referenced via TafsirBook.lang and {% translate %}).
TAFSIR_ALMUYASSER = _("tafsir_almuyasser")
TAFSIR_ALKATHEER = _("tafsir_alkatheer")
TAFSIR_ALBAGHAWY = _("tafsir_albaghawy")
TAFSIR_ALTABARY = _("tafsir_altabary")
TAFSIR_ALQORTOBY = _("tafsir_alqortoby")
TAFSIR_ALSA3DY = _("tafsir_alsa3dy")
