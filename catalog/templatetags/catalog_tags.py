from django import template

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
