# -*- coding: utf-8 -*-
"""
Einheitenstrategie des Rigolen-Tools.

GRUNDREGEL
----------
1. INTERN rechnet das Tool ausschliesslich in METERN (float).
   Jede Funktion in rigole_core erwartet und liefert Meter.
2. Die Vectorworks-API (vs.Rect, vs.Symbol, vs.MoveTo, vs.SetEntityMatrix ...)
   erwartet Koordinaten in DOKUMENTEINHEITEN des aktiven Dokuments.
   Steht das Dokument auf Millimeter, bedeutet vs.Rect(0,0,1000,500) ein
   Rechteck von 1000 mm x 500 mm. Steht es auf Meter, waeren das 1000 m.
3. Die Umrechnung erfolgt genau an EINER Stelle: to_doc() / from_doc().

UMRECHNUNG
----------
vs.GetUnits() liefert unter anderem "upi" = units per inch, also die Anzahl
Dokumenteinheiten pro Zoll (mm-Dokument: 25.4, cm: 2.54, m: 0.0254,
Zoll: 1.0, Fuss: 1/12).

    1 m = 1 / 0.0254 Zoll = 39.3700787... Zoll
    doc_units = meter * (1 / 0.0254) * upi

Gegenprobe:
    mm-Dokument  upi = 25.4    -> 1 m * 39.37008 * 25.4    = 1000.0   OK
    cm-Dokument  upi = 2.54    -> 1 m * 39.37008 * 2.54    =  100.0   OK
    m-Dokument   upi = 0.0254  -> 1 m * 39.37008 * 0.0254  =    1.0   OK
    Zoll         upi = 1.0     -> 1 m * 39.37008 * 1.0     =   39.37  OK

ANZEIGE
-------
Die Anzeige im Dialog und in der Beschriftung erfolgt bewusst IMMER in Metern
(m, m2, m3) - unabhaengig von den Dokumenteinheiten. Das entspricht der
Planungspraxis im Tiefbau und macht die Beschriftung dokumentunabhaengig
vergleichbar. Formatierung siehe rigole_core/formatting.py.

Ausnahme: Eingabefelder, die als vs.CreateEditReal vom Typ 3 (Dimension)
angelegt werden, arbeiten zwingend in Dokumenteinheiten. Fuer Version 1
werden Laengen deshalb als REAL-Felder (Typ 1) mit dem festen Suffix "m"
im Label gefuehrt -> keine versteckte Einheitenumrechnung im Dialog.

Kompatibilitaet: Python 3.9.2 (Vectorworks 2026)
"""

import math

INCH_IN_METERS = 0.0254
INCHES_PER_METER = 1.0 / INCH_IN_METERS      # 39.37007874015748


def meters_to_doc(value_m, units_per_inch):
    """Meter -> Dokumenteinheiten."""
    return float(value_m) * INCHES_PER_METER * float(units_per_inch)


def doc_to_meters(value_doc, units_per_inch):
    """Dokumenteinheiten -> Meter."""
    upi = float(units_per_inch)
    if upi == 0.0:
        raise ValueError("units_per_inch darf nicht 0 sein.")
    return float(value_doc) / (INCHES_PER_METER * upi)


def cubic_meters_to_doc(value_m3, units_per_inch):
    """Kubikmeter -> Kubik-Dokumenteinheiten (nur falls jemals benoetigt)."""
    f = INCHES_PER_METER * float(units_per_inch)
    return float(value_m3) * f * f * f


class UnitContext(object):
    """
    Buendelt die Einheiteninformationen des aktiven Dokuments.

    Wird in der VW-Schicht EINMAL pro Toolaufruf erzeugt aus:
        fraction, display, format, upi, name, squareName = vs.GetUnits()
    und danach an alle Geometriefunktionen weitergereicht. So wird
    vs.GetUnits() nicht hunderte Male je Korb aufgerufen (Performance).
    """

    def __init__(self, units_per_inch, unit_mark="", square_mark=""):
        self.upi = float(units_per_inch)
        if not math.isfinite(self.upi) or self.upi <= 0:
            raise ValueError("Ungültige Dokumenteinheit: units per inch muss positiv sein.")
        self.unit_mark = unit_mark
        self.square_mark = square_mark

    def to_doc(self, value_m):
        return meters_to_doc(value_m, self.upi)

    def from_doc(self, value_doc):
        return doc_to_meters(value_doc, self.upi)

    def __repr__(self):
        return "UnitContext(upi=%r, mark=%r)" % (self.upi, self.unit_mark)


# Bequeme Vorgaben fuer Tests ausserhalb von Vectorworks
UPI_MM = 25.4
UPI_CM = 2.54
UPI_M = 0.0254
UPI_INCH = 1.0
UPI_FOOT = 1.0 / 12.0
