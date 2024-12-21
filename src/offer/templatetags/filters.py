import jdatetime

from django import template

register = template.Library()


@register.filter
def to_jalali(value):
    if value:
        return jdatetime.datetime. \
            fromgregorian(datetime=value). \
            strftime('%Y/%m/%d')
