from django import template
from django.utils import timezone, translation

from requester.localdates import format_day

register = template.Library()


@register.filter
def localdate(value):
    """``YYYY-MM-DD`` in the visitor's calendar: Jalali for Persian, else Gregorian."""
    if not value:
        return ""
    if hasattr(value, "tzinfo") and timezone.is_aware(value):
        value = timezone.localtime(value)
    if hasattr(value, "date"):
        value = value.date()
    return format_day(value, translation.get_language())


@register.filter
def salary_label(posting):
    """``30,000 - 50,000 EUR`` for a posting; empty when no salary is given."""
    low, high = posting.salary_min, posting.salary_max
    if low is None and high is None:
        return ""
    if low is not None and high is not None and low != high:
        amount = f"{low:,} - {high:,}"
    else:
        amount = f"{(high if high is not None else low):,}"
    return f"{amount} {posting.salary_currency}"
