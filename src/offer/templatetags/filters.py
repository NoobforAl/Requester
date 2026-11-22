import jdatetime
from django import template
from django.utils import timezone

register = template.Library()


@register.filter
def to_jalali(value):
    if value:
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        return jdatetime.datetime.fromgregorian(datetime=value).strftime("%Y/%m/%d")
