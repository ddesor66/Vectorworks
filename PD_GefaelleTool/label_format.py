"""Pure, literal prefix/suffix formatting for drawing annotations."""
from .core import SlopeError, _number


DEFAULTS = {
    "height": {"prefix": "H=", "suffix": "m"},
    "length": {"prefix": "L=", "suffix": "m"},
    "slope": {"prefix": "", "suffix": " %"},
}


def options(value=None):
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise SlopeError("Ungültige Einstellungen für Beschriftungen.")
    result = {}
    for kind, defaults in DEFAULTS.items():
        supplied = value.get(kind, {})
        if not isinstance(supplied, dict):
            raise SlopeError("Präfix und Suffix müssen Textfelder sein.")
        result[kind] = {}
        for field, default in defaults.items():
            text = supplied.get(field, default)
            if not isinstance(text, str) or "\x00" in text:
                raise SlopeError("Präfix und Suffix müssen gültigen Text enthalten; leere Felder sind erlaubt.")
            # Spaces belong to the user's literal text, including at both ends.
            result[kind][field] = text
    return result


def annotation(kind, value, preferences):
    style = options(preferences.get("labels"))[kind]
    decimals = 2 if kind == "height" else preferences.get(kind + "_decimals", 2)
    if type(decimals) is not int or not 0 <= decimals <= 6:
        raise SlopeError("Nachkommastellen müssen zwischen 0 und 6 liegen.")
    numeric = ("%.*f" % (decimals, _number(value, "Beschriftungswert"))).replace(".", ",")
    return style["prefix"] + numeric + style["suffix"]
