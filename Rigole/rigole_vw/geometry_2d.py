# -*- coding: utf-8 -*-
"""
PHASE 6 - 2D-Darstellung der Rigole (Draufsicht).

Erzeugt:
    * ein Rechteck als Aussenumgrenzung
    * Rasterlinien entsprechend der Korbteilung

    ┌────┬────┬────┬────┐
    │    │    │    │    │
    ├────┼────┼────┼────┤
    │    │    │    │    │
    └────┴────┴────┴────┘

Der Nullpunkt ist der Einfuegepunkt; aufgebaut wird in positive X- und
Y-Richtung, ohne Drehung.

Alle uebergebenen Masse sind in METERN; die Umrechnung in Dokumenteinheiten
passiert hier ueber den UnitContext.

Pruefbericht A, U3: Ein per vs.Rect erzeugtes Objekt liegt bereits auf der
Ebenenebene (GetEntityMatrix liefert True mit Offset 0/0/0). Ein
nachtraegliches SetEntityMatrix ist nicht noetig.

Kompatibilitaet: Python 3.9.2 (Vectorworks 2026)
"""

import vs

from rigole_config.constants import CLASS_2D, GRID_MAX_LINES
from rigole_vw import vwutils


def draw_plan(origin_doc, ergebnis, unit_ctx, rollback, mit_raster=True):
    """
    Zeichnet die Draufsicht.

    origin_doc   (x, y) Einfuegepunkt in DOKUMENTEINHEITEN
    ergebnis     RigoleResult aus calculations.compute_rigole (Meter)
    unit_ctx     UnitContext
    rollback     vwutils.Rollback - jedes Objekt wird dort vermerkt
    mit_raster   False = nur die Aussenumgrenzung

    Rueckgabe: Liste der erzeugten Handles.
    """
    x0, y0 = float(origin_doc[0]), float(origin_doc[1])
    laenge = unit_ctx.to_doc(ergebnis.total_length)
    breite = unit_ctx.to_doc(ergebnis.total_width)
    korb_l = unit_ctx.to_doc(ergebnis.basket_length)
    korb_b = unit_ctx.to_doc(ergebnis.basket_width)

    handles = []
    vorherige_klasse = _klasse_setzen(CLASS_2D)
    try:
        # --- Aussenumgrenzung --------------------------------------------
        vs.Rect(x0, y0 + breite, x0 + laenge, y0)
        h = rollback.merke_letztes()
        if not vwutils.handle_ok(h):
            raise RuntimeError("Die Aussenumgrenzung konnte nicht erzeugt werden.")
        _klasse_zuweisen(h)
        handles.append(h)

        # --- Raster -------------------------------------------------------
        anzahl_linien = max(0, ergebnis.count_length - 1) + \
            max(0, ergebnis.count_width - 1)
        if mit_raster and 0 < anzahl_linien <= GRID_MAX_LINES:
            # Trennlinien quer zur Laengsrichtung
            for i in range(1, ergebnis.count_length):
                x = x0 + i * korb_l
                vs.MoveTo(x, y0)
                vs.LineTo(x, y0 + breite)
                h = rollback.merke_letztes()
                if vwutils.handle_ok(h):
                    _klasse_zuweisen(h)
                    handles.append(h)
            # Trennlinien laengs
            for j in range(1, ergebnis.count_width):
                y = y0 + j * korb_b
                vs.MoveTo(x0, y)
                vs.LineTo(x0 + laenge, y)
                h = rollback.merke_letztes()
                if vwutils.handle_ok(h):
                    _klasse_zuweisen(h)
                    handles.append(h)
    finally:
        _klasse_setzen(vorherige_klasse)

    return handles


def _klasse_zuweisen(h):
    """
    Weist die Klasse AUSDRUECKLICH zu.

    Die aktive Klasse allein reicht nicht: In Vectorworks haengt es von einer
    Dokumentvoreinstellung ab, ob neu erzeugte Objekte die aktive Klasse
    uebernehmen. Genau deshalb lagen am 24.08.2026 einzelne 2D-Objekte in der
    falschen Klasse. vs.SetClass je Objekt ist eindeutig und kostet nur einen
    Aufruf.
    """
    try:
        vs.SetClass(h, CLASS_2D)
    except Exception:
        pass


def _klasse_setzen(name):
    """
    Macht die Klasse aktiv (und legt sie an, falls sie fehlt).
    Liefert den Namen der vorher aktiven Klasse zurueck, damit der Aufrufer
    den Dokumentzustand wiederherstellen kann.
    """
    vorher = ""
    try:
        vorher = vs.ActiveClass()
    except Exception:
        pass
    if name:
        try:
            vs.NameClass(name)
        except Exception:
            pass
    return vorher
