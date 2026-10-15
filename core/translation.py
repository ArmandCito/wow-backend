"""Optional DeepL translation, used to fill a language an editor left empty."""

import logging

from django.conf import settings

logger = logging.getLogger(__name__)

LANGUAGES = ("en", "fr")
DEEPL_TARGETS = {"en": "EN-US", "fr": "FR"}


def other_language(lang):
    return "fr" if lang == "en" else "en"


def translate(text, source, target):
    """`text` translated from `source` to `target`; the text itself when DeepL is off or fails."""
    if not text or not settings.DEEPL_AUTH_KEY:
        return text
    try:
        import deepl

        result = deepl.Translator(settings.DEEPL_AUTH_KEY).translate_text(
            text, source_lang=source.upper(), target_lang=DEEPL_TARGETS[target]
        )
        return result.text
    except Exception:  # a translation problem must never block saving content
        logger.warning("DeepL translation failed, the text is copied as is", exc_info=True)
        return text
