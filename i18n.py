"""
Backward-compatibility bridge for OpenDictate i18n package.
Directs imports to the modular i18n package modules.
"""

from i18n.translator import Translator, get_translator, DEFAULT_LANG, TRANSLATIONS
from i18n.en import STRINGS as EN_STRINGS
from i18n.es import STRINGS as ES_STRINGS
from i18n.de import STRINGS as DE_STRINGS
from i18n.fr import STRINGS as FR_STRINGS

TRANSLATIONS["en"] = EN_STRINGS
TRANSLATIONS["es"] = ES_STRINGS
TRANSLATIONS["de"] = DE_STRINGS
TRANSLATIONS["fr"] = FR_STRINGS

__all__ = ["Translator", "get_translator", "DEFAULT_LANG", "TRANSLATIONS"]
