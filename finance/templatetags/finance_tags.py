from decimal import Decimal
from django import template
register = template.Library()
@register.filter
def money(value):
    text = f'{Decimal(value or 0):,.2f}'
    return 'R$ ' + text.replace(',', '_').replace('.', ',').replace('_', '.')
