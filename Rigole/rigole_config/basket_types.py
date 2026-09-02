# -*- coding: utf-8 -*-
"""
Konfiguration der vordefinierten Rigolenkoerbe und der Auswahllisten.

HIER WIRD DAS TOOL ERWEITERT
----------------------------
Jeder Korbtyp bringt seine Abmessungen UND sein Vectorworks-Symbol mit.
Der Anwender waehlt im Dialog nur noch die Groesse - das passende Symbol
sucht sich das Werkzeug selbst. Damit kann Symbol und Groesse nicht mehr
auseinanderlaufen (das war die Ursache der Lagenluecke am 21.08.2026).

Einen neuen Korbtyp ergaenzt man, indem man unten einen weiteren Eintrag in
BASKET_TYPES hinzufuegt. Der Schluessel ist gleichzeitig der Anzeigetext im
Aufklappmenue.

WICHTIG
-------
* Alle Laengenangaben in METERN (float). Das ist die interne Einheit des
  gesamten Tools.
* "symbol" muss EXAKT dem Namen der Symboldefinition im Vectorworks-
  Dokument entsprechen (Gross-/Kleinschreibung zaehlt).
* Die Symboldefinition muss dieselben Abmessungen haben wie length/width/
  height. Das Werkzeug misst vor dem Bauen nach und fragt bei Abweichung.
* "anchor" beschreibt, wo der Einfuegepunkt der Symboldefinition sitzt:
      "corner" = vordere linke Ecke  (Standard)
      "center" = Mitte des Korbes
* Diese Datei ist bewusst frei von "import vs" -> ausserhalb von
  Vectorworks testbar.

Kompatibilitaet: Python 3.9.2 (Vectorworks 2026)
"""

from collections import OrderedDict

# ---------------------------------------------------------------------------
# Rigolenarten - HISTORISCH (bis Version 0.16.0)
# ---------------------------------------------------------------------------
# Bis einschliesslich 0.16.0 gab es im Dialog eine Auswahl "Rigolenart"
# ("Rigolenkoerper", "Rohr-Rigole", ...). Sie ist am 26.08.2026 auf Wunsch
# entfallen; an ihre Stelle ist die Auswahl HERSTELLER / SYSTEM getreten,
# die zugleich die Elementmasse mitbringt.
#
# Die Liste bleibt stehen, weil diese Texte im Datensatzfeld "Rigolenart"
# aelterer Objekte auftauchen und beim Bearbeiten gelesen werden.
RIGOLE_TYPES = [
    "Rigolenkoerper",
    "Rohr-Rigole",
    "Kiesrigole",
    "Sonderbauart",
]

ART_KIESRIGOLE_NAME = "Kiesrigole"


def rigole_types():
    """Historische Auswahlliste - im Dialog nicht mehr verwendet."""
    return [t for t in RIGOLE_TYPES if t != ART_KIESRIGOLE_NAME]

# ---------------------------------------------------------------------------
# Belastungsklassen (DIN EN 1433 / DIN EN 124)
# REINE PLANUNGSINFORMATION - es findet KEINE statische Bemessung statt.
# ---------------------------------------------------------------------------
LOAD_CLASSES = ["A15", "B125", "C250", "D400", "E600", "F900"]
DEFAULT_LOAD_CLASS = "D400"

# ---------------------------------------------------------------------------
# Einfuegepunkt der Symbole
# ---------------------------------------------------------------------------
ANCHOR_CORNER = "corner"
ANCHOR_CENTER = "center"
DEFAULT_ANCHOR = ANCHOR_CORNER

# ---------------------------------------------------------------------------
# HERSTELLER / SYSTEM  (Auswahl im Dialog, seit 26.08.2026)
# ---------------------------------------------------------------------------
# Die Auswahl bringt die Elementmasse mit: Wer ein System waehlt, bekommt
# Laenge, Breite und Hoehe automatisch eingetragen; die Massfelder sind dann
# gesperrt. Nur bei "Benutzerdefinierte Abmessungen" sind sie frei.
#
# Felder je Eintrag:
#   hersteller : Firmenname, nur zur Anzeige
#   system     : Produktname, nur zur Anzeige
#   length     : Elementlaenge in m (X-Richtung / Laengsrichtung der Rigole)
#   width      : Elementbreite in m (Y-Richtung)
#   height     : Elementhoehe  in m (Z-Richtung)
#   storage_coefficient : Vorschlag fuer den Speicherkoeffizienten (Faktor)
#   symbol     : Name der Vectorworks-Symboldefinition
#                ("" = Name wird aus den Massen gebildet und das Symbol bei
#                 Bedarf selbst angelegt)
#   anchor     : "corner" oder "center"
#   note       : Freitext, erscheint als Hilfetext im Dialog
#
# ACHTUNG, zwei Dinge sind hier NICHT belastbar und vor dem produktiven
# Einsatz zu pruefen:
#
# 1. Die MASSE stammen aus der Vorgabe des Anwenders vom 26.08.2026
#    ("typisches Elementmass"). Sie sind nicht aus Herstellerunterlagen
#    nachgeschlagen. Bei den beiden ACO-Eintraegen handelt es sich
#    ausserdem ausdruecklich um ein RASTERMASS je voller Lage, nicht um ein
#    Einzelbauteil - das Werkzeug setzt sie trotzdem wie ein Element.
#
# 2. Der SPEICHERKOEFFIZIENT ist ueberall ein PLATZHALTER (0,95). Die
#    tatsaechlichen Hohlraumanteile der Systeme kenne ich nicht und habe
#    sie bewusst nicht geraten. Der Wert laesst sich im Dialog jederzeit
#    ueberschreiben; hier gehoert je System die Herstellerangabe hinein.
CUSTOM_BASKET_KEY = "Benutzerdefinierte Abmessungen"

# Platzhalter-Speicherkoeffizient, siehe Hinweis oben.
KOEFF_PLATZHALTER = 0.95

_HINWEIS_MASS = ("Typisches Elementmass laut Vorgabe vom 26.08.2026. "
                 "Speicherkoeffizient ist ein PLATZHALTER - bitte durch die "
                 "Herstellerangabe ersetzen.")

_HINWEIS_ACO = ("Rastermass je VOLLER LAGE, kein Einzelbauteil. "
                "Speicherkoeffizient ist ein PLATZHALTER - bitte durch die "
                "Herstellerangabe ersetzen.")


def _system(hersteller, system, laenge, breite, hoehe, hinweis=_HINWEIS_MASS):
    """Ein Eintrag der Auswahlliste. Masse in METERN."""
    return (u"%s – %s" % (hersteller, system), {
        "hersteller": hersteller,
        "system": system,
        "length": float(laenge),
        "width": float(breite),
        "height": float(hoehe),
        "storage_coefficient": KOEFF_PLATZHALTER,
        "symbol": "",
        "anchor": ANCHOR_CORNER,
        "note": hinweis,
    })


BASKET_TYPES = OrderedDict([
    _system(u"FRÄNKISCHE", "Rigofill inspect", 0.800, 0.800, 0.660),
    _system(u"FRÄNKISCHE", "Rigofill inspect Halbblock", 0.800, 0.800, 0.350),
    _system("GRAF", "EcoBloc Inspect 420", 0.800, 0.800, 0.660),
    _system("REHAU", "RAUSIKKO Box 8.6 SC", 0.800, 0.800, 0.660),
    _system("REHAU", "RAUSIKKO Box 8.3 SC", 0.800, 0.800, 0.360),
    _system("Funke", "D-Raintank 3000", 0.600, 0.600, 0.600),
    _system("Funke", "Smallbox", 0.600, 0.600, 0.330),
    _system("Wavin", "Q-Bic Plus", 1.200, 0.600, 0.600),
    _system("Wavin", "AquaCell NG", 1.200, 0.600, 0.400),
    _system("ACO", "StormBrixx HD", 1.205, 0.602, 0.610, _HINWEIS_ACO),
    _system("ACO", "StormBrixx SD", 1.200, 0.600, 0.914, _HINWEIS_ACO),
    (CUSTOM_BASKET_KEY, {
        "hersteller": "",
        "system": "",
        "length": 0.80,
        "width": 0.80,
        "height": 0.33,
        "storage_coefficient": KOEFF_PLATZHALTER,
        "symbol": "",                       # leer -> Name aus den Eingabewerten
        "anchor": ANCHOR_CORNER,
        "note": "Masse werden von Hand eingegeben; der Symbolname ergibt "
                "sich aus den eingegebenen Massen.",
    }),
])

DEFAULT_BASKET_KEY = list(BASKET_TYPES.keys())[0]

# Fuer den Datensatz und die Beschriftung: Das frueher getrennt gefuehrte
# Feld "Rigolenart" traegt jetzt die Auswahl "Hersteller - System".
DEFAULT_RIGOLE_TYPE = DEFAULT_BASKET_KEY


def hersteller_von(key):
    data = BASKET_TYPES.get(key) or {}
    return str(data.get("hersteller") or "")


def system_von(key):
    data = BASKET_TYPES.get(key) or {}
    return str(data.get("system") or "")


def ist_bekanntes_system(key):
    """Steht dieser Text in der Auswahlliste?"""
    return key in BASKET_TYPES


def basket_type_names():
    """Reihenfolge der Eintraege fuer das Aufklappmenue."""
    return list(BASKET_TYPES.keys())


def get_basket_type(key):
    """
    Liefert eine KOPIE des Korbtyp-Datensatzes.
    Kopie, damit ein versehentliches Ueberschreiben im Dialog die
    Konfiguration nicht dauerhaft veraendert.
    """
    data = BASKET_TYPES.get(key)
    if data is None:
        return None
    return dict(data)


def is_custom(key):
    return key == CUSTOM_BASKET_KEY


# ---------------------------------------------------------------------------
# Symbolnamen
# ---------------------------------------------------------------------------
# Ist bei einem Korbtyp kein Symbolname eingetragen, bildet das Werkzeug ihn
# aus den Abmessungen und legt die Symboldefinition bei Bedarf selbst an.
# Damit muss vorab kein Symbol von Hand in die Zeichnung geholt werden.
SYMBOL_NAME_TEMPLATE = "Rigolenkorb {laenge}x{breite}x{hoehe}"


def symbol_name_for_dimensions(laenge_m, breite_m, hoehe_m):
    """
    Bildet den Symbolnamen aus den Abmessungen, in Millimetern.

        0.80, 0.80, 0.33  ->  "Rigolenkorb 800x800x330"

    Millimeter statt Meter, damit im Namen keine Dezimaltrennzeichen stehen -
    die machen in Vectorworks-Ressourcennamen nur Aerger.
    """
    def mm(wert):
        try:
            return int(round(float(wert) * 1000.0))
        except (TypeError, ValueError):
            return 0

    return SYMBOL_NAME_TEMPLATE.format(laenge=mm(laenge_m), breite=mm(breite_m),
                                       hoehe=mm(hoehe_m))


def symbol_for(key, laenge_m=None, breite_m=None, hoehe_m=None):
    """
    Name der Symboldefinition fuer diesen Korbtyp.

    Vorrang hat ein in BASKET_TYPES eingetragener Name. Fehlt er, wird der
    Name aus den Abmessungen gebildet - bei "Benutzerdefinierte Abmessungen"
    aus den uebergebenen Werten, sonst aus denen der Konfiguration.
    """
    data = BASKET_TYPES.get(key)
    if data:
        eingetragen = str(data.get("symbol") or "").strip()
        if eingetragen:
            return eingetragen

    if laenge_m is None or breite_m is None or hoehe_m is None:
        if not data:
            return ""
        laenge_m = data.get("length")
        breite_m = data.get("width")
        hoehe_m = data.get("height")

    if not laenge_m or not breite_m or not hoehe_m:
        return ""
    return symbol_name_for_dimensions(laenge_m, breite_m, hoehe_m)


def anchor_for(key):
    """Einfuegepunkt des Symbols dieses Korbtyps."""
    data = BASKET_TYPES.get(key)
    if not data:
        return DEFAULT_ANCHOR
    anchor = data.get("anchor") or DEFAULT_ANCHOR
    return anchor if anchor in (ANCHOR_CORNER, ANCHOR_CENTER) else DEFAULT_ANCHOR


def note_for(key):
    data = BASKET_TYPES.get(key)
    if not data:
        return ""
    return str(data.get("note") or "")


def types_with_symbol():
    """Alle Korbtypen, denen ein Symbol zugeordnet ist."""
    return [k for k in BASKET_TYPES if symbol_for(k)]


def has_custom_symbol(key):
    """True, wenn in der Konfiguration ausdruecklich ein Symbol steht."""
    data = BASKET_TYPES.get(key)
    if not data:
        return False
    return bool(str(data.get("symbol") or "").strip())
