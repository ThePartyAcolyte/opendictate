"""
Internationalization (i18n) package for OpenDictate.
Exposes Translator, get_translator, DEFAULT_LANG, and aggregated TRANSLATIONS dictionary.
"""

from .translator import Translator, get_translator, DEFAULT_LANG, TRANSLATIONS
from .en import STRINGS as EN_STRINGS
from .es import STRINGS as ES_STRINGS
from .de import STRINGS as DE_STRINGS
from .fr import STRINGS as FR_STRINGS

# Populate global translations registry
TRANSLATIONS["en"] = EN_STRINGS
TRANSLATIONS["es"] = ES_STRINGS
TRANSLATIONS["de"] = DE_STRINGS
TRANSLATIONS["fr"] = FR_STRINGS

__all__ = [
    "Translator",
    "get_translator",
    "DEFAULT_LANG",
    "TRANSLATIONS",
]
