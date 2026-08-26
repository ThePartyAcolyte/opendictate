"""
Core Translator engine for OpenDictate.
Provides key-based string localization with format arguments support.
"""

from typing import Dict, Any, Optional

DEFAULT_LANG = "en"

# Global translations registry populated by i18n package initializer
TRANSLATIONS: Dict[str, Dict[str, str]] = {}


class Translator:
    """Translator class resolving localized strings by language code and key."""

    def __init__(self, lang_code: Optional[str]) -> None:
        self.lang = lang_code
        if not self.lang or self.lang not in TRANSLATIONS:
            self.lang = DEFAULT_LANG

    def t(self, key: str, *args: Any, **kwargs: Any) -> str:
        """Retrieve the translated string for a given key and apply optional formatting."""
        lang_dict = TRANSLATIONS.get(self.lang, {})
        default_dict = TRANSLATIONS.get(DEFAULT_LANG, {})
        text = lang_dict.get(key, default_dict.get(key, key))

        if kwargs:
            try:
                return text.format(**kwargs)
            except Exception:
                pass
        if args:
            try:
                if isinstance(args[0], dict):
                    return text.format(**args[0])
                return text.format(*args)
            except Exception:
                pass
        return text


def get_translator(lang_code: Optional[str]) -> Translator:
    """Factory helper to obtain a Translator instance for the specified language."""
    return Translator(lang_code)
