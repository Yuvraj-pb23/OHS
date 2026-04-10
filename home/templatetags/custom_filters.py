from django import template

register = template.Library()

@register.filter
def get_item_subject(templates_dict, key):
    template = templates_dict.get(key)
    return template.subject if template else ""

@register.filter
def get_item_body(templates_dict, key):
    template = templates_dict.get(key)
    return template.body if template else ""
