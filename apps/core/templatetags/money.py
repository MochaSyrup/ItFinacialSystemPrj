from django import template

register = template.Library()

UNITS = (
    (10 ** 12, '조'),
    (10 ** 8, '억'),
    (10 ** 4, '만'),
)


def _fmt(scaled):
    if scaled == int(scaled):
        return f'{int(scaled):,}'
    return f'{scaled:,.1f}'


@register.filter
def korean_amount(value):
    try:
        n = float(value)
    except (TypeError, ValueError):
        return ''
    if not n:
        return '0'
    sign = '-' if n < 0 else ''
    n = abs(n)
    for divisor, unit in UNITS:
        if n >= divisor:
            return f'{sign}{_fmt(n / divisor)}{unit}'
    return f'{sign}{int(round(n)):,}'
