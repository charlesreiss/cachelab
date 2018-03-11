from django import template
import logging

register = template.Library()

logger = logging.getLogger('cachelabweb')

@register.simple_tag()
def format_hex(value, bits):
    if value == None:
        return '(none)'
    else:
        width = int((bits + 3) / 4)
        return '0x{:0{width}x}'.format(value, width=width)
