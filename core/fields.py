"""
Bilingual text. Models store one column per language (`name_en`, `name_fr`); the API exposes one
object `{"en": "...", "fr": "..."}` (type `Localized` on the website).
"""

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .translation import LANGUAGES, other_language, translate

LOCALIZED_SCHEMA = {
    "type": "object",
    "properties": {"en": {"type": "string"}, "fr": {"type": "string"}},
    "required": ["en", "fr"],
}


def localized(obj, base):
    """{"en": obj.<base>_en, "fr": obj.<base>_fr}"""
    return {lang: getattr(obj, f"{base}_{lang}") or "" for lang in LANGUAGES}


def localized_columns(base, value):
    """{"en": "Burger"} -> {"name_en": "Burger"} (only the languages given)."""
    return {f"{base}_{lang}": text for lang, text in value.items()}


@extend_schema_field(LOCALIZED_SCHEMA)
class LocalizedField(serializers.Field):
    """
    `LocalizedField()` on a serializer reads/writes the `<field>_en` / `<field>_fr` columns.

    Writing: send both languages. A language sent empty (or missing on create) is translated from
    the other one with DeepL, or copied when DeepL is not configured. On a partial update, a
    language that is not sent keeps its current value.

    - `optional=True`: both languages may be empty; the field then reads as `null`.
    - `base="..."`: column prefix when it differs from the field name.
    """

    default_error_messages = {
        "invalid": 'Expected {"en": "...", "fr": "..."}.',
        "blank": "At least one language is required.",
        "max_length": "Ensure this text has no more than {max_length} characters.",
    }

    def __init__(self, *, base=None, optional=False, max_length=None, **kwargs):
        self.base = base
        self.optional = optional
        self.max_length = max_length
        kwargs["source"] = "*"
        if optional:
            kwargs.setdefault("required", False)
            kwargs.setdefault("allow_null", True)
        super().__init__(**kwargs)

    def bind(self, field_name, parent):
        super().bind(field_name, parent)
        self.base = self.base or field_name

    def to_representation(self, obj):
        value = localized(obj, self.base)
        if self.optional and not any(value.values()):
            return None
        return value

    def validate_empty_values(self, data):
        # source="*" fields skip None handling: an optional field set to null clears both languages
        if data is None and self.optional:
            return True, {f"{self.base}_{lang}": "" for lang in LANGUAGES}
        return super().validate_empty_values(data)

    def to_internal_value(self, data):
        if not isinstance(data, dict) or not set(data) <= set(LANGUAGES):
            self.fail("invalid")

        values = {}
        for lang in LANGUAGES:
            if lang not in data:
                continue
            text = data[lang] if data[lang] is not None else ""
            if not isinstance(text, str):
                self.fail("invalid")
            text = text.strip()
            if self.max_length and len(text) > self.max_length:
                self.fail("max_length", max_length=self.max_length)
            values[lang] = text

        creating = getattr(self.parent, "instance", None) is None
        filled = {lang: text for lang, text in values.items() if text}
        if not filled:
            if self.optional:
                return {f"{self.base}_{lang}": "" for lang in LANGUAGES}
            self.fail("blank")

        # Complete the language left empty (or missing on create) from the one that was given
        for lang in LANGUAGES:
            if lang in filled or (lang not in values and not creating):
                continue
            source = other_language(lang)
            values[lang] = translate(filled[source], source, lang) if source in filled else ""

        return {f"{self.base}_{lang}": text for lang, text in values.items()}
