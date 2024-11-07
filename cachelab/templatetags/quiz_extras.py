from django import template
import logging

register = template.Library()

logger = logging.getLogger('cachelab')

@register.simple_tag()
def format_hex(value, bits):
    if value == None:
        return '(none)'
    else:
        width = int((bits + 3) / 4)
        return '0x{:0{width}x}'.format(value, width=width)

@register.simple_tag()
def format_bin(value, bits=None):
    if value == None:
        return ''
    elif bits != None:
        return '{:0{bits}b}'.format(value, bits=bits)
    else:
        return '{:b}'.format(value)
