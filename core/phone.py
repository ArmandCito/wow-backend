"""Rwandan mobile numbers, same rule as the website (lib/phone.ts)."""

import re

from rest_framework import serializers

RWANDAN_MOBILE = re.compile(r"^(?:\+?250|0)(7\d{8})$")


def normalize_phone(value):
    """"0781234567", "+250 781 234 567"… -> "078 123 4567", or None when it is not a Rwandan mobile."""
    digits = re.sub(r"[\s().-]", "", value or "")
    match = RWANDAN_MOBILE.match(digits)
    if not match:
        return None
    local = f"0{match.group(1)}"
    return f"{local[:3]} {local[3:6]} {local[6:]}"


class PhoneField(serializers.CharField):
    """Accepts any common spelling of a Rwandan mobile number and stores "078 123 4567"."""

    default_error_messages = {"invalid_phone": "Enter a Rwandan mobile number (07X XXX XXXX)."}

    def __init__(self, **kwargs):
        kwargs.setdefault("max_length", 20)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        value = super().to_internal_value(data)
        if value == "" and self.allow_blank:
            return value
        phone = normalize_phone(value)
        if phone is None:
            self.fail("invalid_phone")
        return phone
