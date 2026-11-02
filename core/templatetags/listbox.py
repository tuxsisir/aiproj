"""Helpers for <c-listbox>: turn a Django form field into the options and value cotton-ui's listbox needs."""
from django import template

register = template.Library()


@register.filter
def listbox_choices(field):
    """[(value, label)] as strings, from a BoundField's choices (ModelChoiceField values become their pk)."""
    return [(str(value), str(label)) for value, label in field.field.choices]


@register.filter
def listbox_value(field):
    """The current value, only if it is one of the choices (a re-rendered POST can't put arbitrary text in JS)."""
    value = field.value()
    value = "" if value is None else str(value)
    return value if value in {str(v) for v, _ in field.field.choices} else ""


@register.filter
def listbox_placeholder(field, default):
    """A ModelChoiceField's empty label ("Nobody yet") reads better than a generic placeholder."""
    return getattr(field.field, "empty_label", None) or default


@register.filter
def safe_quotes(text):
    """cotton-ui writes labels into single-quoted JavaScript: a straight apostrophe (O'Brien), a backslash or a
    line break would break it, so swap or drop them."""
    text = str(text).replace("'", "’").replace("\\", "/")
    return " ".join(text.splitlines())


@register.filter
def is_select(field):
    return getattr(field.field.widget, "input_type", None) == "select"
