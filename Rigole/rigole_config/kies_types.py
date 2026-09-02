# -*- coding: utf-8 -*-
"""
Konfiguration der Kiesrigole: Fuellmaterial und Draenrohr-Dimensionen.

HIER WIRD ERWEITERT
-------------------
Wie bei den Rigolenkoerben stehen alle veraenderlichen Angaben an genau
einer Stelle. Neues Material oder eine weitere Rohrdimension ergaenzt man,
indem man unten einen Eintrag hinzufuegt.

!!! WICHTIG - DIE HOHLRAUMANTEILE SIND PLATZHALTER !!!
Die Hohlraumanteile der Materialien unten sind BEISPIELWERTE zur
Veranschaulichung. Sie muessen vor dem produktiven Einsatz durch die Werte
aus dem Datenblatt der Lieferkoernung ersetzt werden. Der Hohlraumanteil
einer Schuettung haengt von Koernung, Kornform, Verdichtung und Einbauart
ab - eine allgemeingueltige Zahl gibt es dafuer nicht.

Die ROHRDIMENSIONEN dagegen sind keine Platzhalter: Vorgabe des Anwenders
vom 24.08.2026 ist die uebliche DN-Reihe, wobei die Zahl den Nenndurch-
messer (lichte Weite) in Millimetern angibt und genau so in die Zeichnung
und in die Rechnung eingeht.

Alle Laengen in METERN (float), wie im gesamten Werkzeug.

Kompatibilitaet: Python 3.9.2 (Vectorworks 2026)
"""

from collections import OrderedDict


# ---------------------------------------------------------------------------
# Fuellmaterial
# ---------------------------------------------------------------------------
# storage_coefficient = nutzbarer Hohlraumanteil als Faktor (0..1).
# Er wird beim Wechsel des Materials als Vorschlag in das Feld
# "Speicherkoeffizient" uebernommen und kann dort ueberschrieben werden.
KIES_MATERIALS = OrderedDict([
    ("Kies 16/32", {
        "storage_coefficient": 0.30,
        "note": "PLATZHALTER - Hohlraumanteil aus dem Datenblatt eintragen",
    }),
    ("Kies 8/16", {
        "storage_coefficient": 0.30,
        "note": "PLATZHALTER - Hohlraumanteil aus dem Datenblatt eintragen",
    }),
    ("Schotter 32/63", {
        "storage_coefficient": 0.35,
        "note": "PLATZHALTER - Hohlraumanteil aus dem Datenblatt eintragen",
    }),
    ("Schotter 16/32", {
        "storage_coefficient": 0.35,
        "note": "PLATZHALTER - Hohlraumanteil aus dem Datenblatt eintragen",
    }),
    ("Splitt 2/5", {
        "storage_coefficient": 0.30,
        "note": "PLATZHALTER - Hohlraumanteil aus dem Datenblatt eintragen",
    }),
])

DEFAULT_KIES_MATERIAL = list(KIES_MATERIALS.keys())[0]


# ---------------------------------------------------------------------------
# Draenrohr
# ---------------------------------------------------------------------------
# Vorgabe des Anwenders (24.08.2026): DN-Reihe, die Zahl ist der
# NENNDURCHMESSER (lichte Weite) in Millimetern und wird genau so als
# Durchmesser gezeichnet und gerechnet.
#
#   "dn"          Nennweite in mm - ganzzahlig, dient nur der Anzeige
#   "durchmesser" derselbe Wert in METERN - danach richtet sich die
#                 gezeichnete Geometrie und das ausgewiesene Rohrvolumen
#
# Eine weitere Nennweite ergaenzt man, indem man hier eine Zeile hinzufuegt;
# DN_REIHE weiter unten erzeugt die Eintraege automatisch.
KEIN_DRAENROHR = "ohne Draenrohr"

DN_REIHE = (100, 125, 160, 200, 250, 300, 350, 400, 500, 600)


def _dn_eintrag(dn):
    return ("DN %d" % (dn,), {
        "dn": int(dn),
        "durchmesser": float(dn) / 1000.0,
        "note": "Nenndurchmesser (lichte Weite) %d mm" % (dn,),
    })


DRAENROHR_DIMENSIONEN = OrderedDict(
    [(KEIN_DRAENROHR, {
        "dn": 0,
        "durchmesser": 0.0,
        "note": "Kiesrigole ohne Rohr",
    })]
    + [_dn_eintrag(dn) for dn in DN_REIHE]
)

DEFAULT_DRAENROHR = "DN 160"

# Vorgaben fuer die Abmessungen einer neuen Kiesrigole (m)
DEFAULT_KIES_LAENGE = 10.00
DEFAULT_KIES_BREITE = 1.00
DEFAULT_KIES_HOEHE = 1.00

# Abstand der ROHRUNTERKANTE zur Kiessohle (m).
# 0.0 = "aufliegend": das Rohr sitzt unmittelbar auf der Sohle. Die Achse
# rechnet das Werkzeug daraus selbst aus (UK + halber Nenndurchmesser).
DEFAULT_ROHR_UK = 0.0

# ---------------------------------------------------------------------------
# Kontrollschaechte
# ---------------------------------------------------------------------------
# Vorgabe des Anwenders (24.08.2026):
#   * je ein senkrechter Schacht vorne und hinten, ihre AUSSENKANTE liegt
#     20 cm innerhalb der Aussenkante der Kiesfuellung
#   * bei ueber 20 m Achsabstand zusaetzlich genau EINER in der Mitte
#   * das Draenrohr laeuft nur zwischen den Schaechten
#   * Unterkante Schacht 20 cm unter der Rohrunterkante
#   * Schachtachse = Draenrohrachse (mittig in der Breite)
#   * Oberkante Schacht wird als absolute Hoehenkote eingegeben
#
# Wie beim Draenrohr ist die Zahl hinter DN der NENNDURCHMESSER in
# Millimetern und wird genau so gezeichnet.
SCHACHT_DN_REIHE = (400, 600, 800, 1000)


def _schacht_eintrag(dn):
    return ("DN %d" % (dn,), {
        "dn": int(dn),
        "durchmesser": float(dn) / 1000.0,
        "note": "Kontrollschacht DN %d" % (dn,),
    })


SCHACHT_DIMENSIONEN = OrderedDict(
    [_schacht_eintrag(dn) for dn in SCHACHT_DN_REIHE])

DEFAULT_SCHACHT = "DN 400"

# Tiefe des Schachtsumpfes: so weit reicht der Schacht UNTER die
# Rohrunterkante (m).
SCHACHT_TIEFE_UNTER_ROHR = 0.20

# Abstand der Schacht-AUSSENKANTE zur Aussenkante der Kiesfuellung (m).
SCHACHT_RAND = 0.20

# Ab diesem Achsabstand der beiden Endschaechte kommt zusaetzlich einer in
# die Mitte (m).
SCHACHT_MITTE_AB_LAENGE = 20.0

# Vorgabe fuer die Oberkante des Schachtes (absolute Hoehenkote, m).
DEFAULT_SCHACHT_OK = 43.80


def schacht_namen():
    return list(SCHACHT_DIMENSIONEN.keys())


def schacht_durchmesser(key):
    """Nenndurchmesser des Schachtes in METERN; 0.0 = unbekannt."""
    daten = SCHACHT_DIMENSIONEN.get(key)
    if not daten:
        return 0.0
    try:
        return float(daten.get("durchmesser", 0.0))
    except (TypeError, ValueError):
        return 0.0


def schacht_dn_mm(key):
    """Nennweite des Schachtes in Millimetern; 0 = unbekannt."""
    daten = SCHACHT_DIMENSIONEN.get(key)
    if not daten:
        return 0
    try:
        return int(daten.get("dn", 0))
    except (TypeError, ValueError):
        return 0


# Symbolnamen der erzeugten Kiesrigolen-Bestandteile
SYMBOL_NAME_TEMPLATE_KIES = "Kiesrigole {laenge}x{breite}x{hoehe}"


def material_names():
    return list(KIES_MATERIALS.keys())


def get_material(key):
    daten = KIES_MATERIALS.get(key)
    return dict(daten) if daten else None


def coefficient_for(key):
    """Vorgeschlagener Hohlraumanteil als Faktor (0..1)."""
    daten = KIES_MATERIALS.get(key)
    if not daten:
        return 0.30
    try:
        return float(daten.get("storage_coefficient", 0.30))
    except (TypeError, ValueError):
        return 0.30


def draenrohr_names():
    return list(DRAENROHR_DIMENSIONEN.keys())


def rohr_durchmesser(key):
    """
    Nenndurchmesser in METERN; 0.0 bedeutet: kein Rohr.
    'DN 160' -> 0.160
    """
    daten = DRAENROHR_DIMENSIONEN.get(key)
    if not daten:
        return 0.0
    try:
        return float(daten.get("durchmesser", 0.0))
    except (TypeError, ValueError):
        return 0.0


def rohr_dn_mm(key):
    """Nennweite als ganze Zahl in Millimetern; 0 bedeutet: kein Rohr."""
    daten = DRAENROHR_DIMENSIONEN.get(key)
    if not daten:
        return 0
    try:
        return int(daten.get("dn", 0))
    except (TypeError, ValueError):
        return 0


def hat_draenrohr(key):
    return rohr_durchmesser(key) > 0.0


def note_for_material(key):
    daten = KIES_MATERIALS.get(key)
    return str(daten.get("note", "")) if daten else ""


def note_for_rohr(key):
    daten = DRAENROHR_DIMENSIONEN.get(key)
    return str(daten.get("note", "")) if daten else ""
