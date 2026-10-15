"""Kigali time helpers (UTC+2, no daylight saving). Dates are stored in UTC."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone

KIGALI = ZoneInfo("Africa/Kigali")


def now():
    return timezone.now()


def start_of_kigali_day(days_ago=0):
    """Midnight in Kigali, `days_ago` calendar days before today."""
    today = timezone.localtime(now(), KIGALI).date() - timedelta(days=days_ago)
    return datetime.combine(today, time.min, tzinfo=KIGALI)


def iso(value):
    """ISO 8601 in Kigali time: "2026-10-06T12:18:00+02:00"."""
    return timezone.localtime(value, KIGALI).isoformat(timespec="seconds") if value else None


def short_date(value):
    """"09 Oct, 18:00" (used in audit sentences)."""
    return timezone.localtime(value, KIGALI).strftime("%d %b, %H:%M")


def rwf(amount):
    """6000 -> "RWF 6,000" (as on the website)."""
    return f"RWF {amount:,}"
