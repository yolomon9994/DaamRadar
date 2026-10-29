from django import template
from django.utils.dateparse import parse_datetime
from django.utils.timezone import is_aware, localtime
from zoneinfo import ZoneInfo

register = template.Library()


@register.simple_tag(takes_context=True)
def query_url(context, **kwargs):
    params = context["request"].GET.copy()
    params.pop("page", None)
    for key, value in kwargs.items():
        if value == "":
            params.pop(key, None)
        else:
            params[key] = value
    return "?" + params.urlencode()


@register.filter
def money(value):
    return f"{value:,.0f}" if value is not None and value == value.to_integral_value() else f"{value:,.2f}" if value is not None else "—"


@register.filter
def observation_time(value):
    parsed = parse_datetime(value) if isinstance(value, str) else value
    if parsed is None or not is_aware(parsed):
        return "Unknown check time"
    return localtime(parsed, ZoneInfo("Asia/Karachi")).strftime("%d %b %Y, %H:%M:%S PKT")
