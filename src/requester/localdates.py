"""Calendar helpers: Jalali dates for Persian, Gregorian for other languages."""

from datetime import date, timedelta

import jdatetime

JALALI_LANGUAGES = frozenset({"fa"})


def uses_jalali(language: str | None) -> bool:
    return (language or "").split("-")[0] in JALALI_LANGUAGES


def month_starts(today: date, language: str | None) -> tuple[date, date]:
    """First day of this month and of last month, as Gregorian dates."""
    if uses_jalali(language):
        this_month = jdatetime.date.fromgregorian(date=today).replace(day=1)
        last_month = (this_month - timedelta(days=1)).replace(day=1)
        return this_month.togregorian(), last_month.togregorian()
    this_month_g = today.replace(day=1)
    last_month_g = (this_month_g - timedelta(days=1)).replace(day=1)
    return this_month_g, last_month_g


def format_day(day: date, language: str | None) -> str:
    """``YYYY-MM-DD`` in the calendar of ``language``."""
    if uses_jalali(language):
        return jdatetime.date.fromgregorian(date=day).strftime("%Y-%m-%d")
    return day.strftime("%Y-%m-%d")
