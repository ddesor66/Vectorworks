# -*- coding: utf-8 -*-
"""
Kontrollschaechte - gemeinsame Geometrie fuer beide Bauarten.

Ein Schacht ist in beiden Faellen dasselbe: ein senkrechtes Rundrohr
zwischen zwei Hoehenkoten. Unterschiedlich sind nur die Lage, die Hoehen
und die Klasse. Deshalb liegt der eigentliche Bauvorgang hier und wird von
geometry_kies.py (Kiesrigole) und builder.py (Koerbe-Rigole) benutzt.

Warum keine Drehung noetig ist
------------------------------
vs.BeginXtrd extrudiert ohnehin in Z-Richtung. Die Extrusionsgrenzen sind
damit unmittelbar Unter- und Oberkante des Schachtes - anders als beim
liegenden Draenrohr, das erst gekippt und dann nachgemessen werden muss.

Alle Werte kommen bereits in DOKUMENTEINHEITEN herein; die Umrechnung aus
Metern erledigt die aufrufende Schicht.

Kompatibilitaet: Python 3.9.2 (Vectorworks 2026)
"""

import vs

from rigole_vw import vwutils


class SchachtFehler(Exception):
    pass


def _klasse_setzen(name):
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


def _aufraeumen(handles):
    for h in handles:
        if vwutils.handle_ok(h):
            try:
                vs.DelObject(h)
            except Exception:
                pass


def build_koerper(mittelpunkte_doc, radius_doc, z_unten_doc, z_oben_doc,
                  klasse):
    """
    Senkrechte Rundschaechte als Extrusionen.

    mittelpunkte_doc  Liste von (x, y) in Dokumenteinheiten
    radius_doc        halber Nenndurchmesser
    z_unten_doc       Unterkante, z_oben_doc Oberkante (beide relativ zum
                      Nullpunkt der Symboldefinition)

    Rueckgabe: Liste der Handles.
    """
    if not mittelpunkte_doc or radius_doc <= 0:
        return []
    if z_oben_doc - z_unten_doc <= 0:
        raise SchachtFehler(
            u"Die Oberkante des Schachtes liegt nicht ueber seiner "
            u"Unterkante. Es wurde nichts erzeugt.")

    handles = []
    vorher = _klasse_setzen(klasse)
    try:
        for mx, my in mittelpunkte_doc:
            vs.BeginXtrd(z_unten_doc, z_oben_doc)
            vs.Oval(mx - radius_doc, my + radius_doc,
                    mx + radius_doc, my - radius_doc)
            vs.EndXtrd()
            h = vs.LNewObj()
            if not vwutils.handle_ok(h):
                raise SchachtFehler(
                    u"Ein Kontrollschacht konnte nicht erzeugt werden.")
            try:
                vs.SetClass(h, klasse)
            except Exception:
                pass
            handles.append(h)
    except SchachtFehler:
        _aufraeumen(handles)
        raise
    except Exception as ex:
        _aufraeumen(handles)
        raise SchachtFehler(
            u"Die Kontrollschaechte konnten nicht erzeugt werden.\n\n"
            u"Technische Meldung: %r" % (ex,))
    finally:
        _klasse_setzen(vorher)

    return handles


def draw_kreise(mittelpunkte_doc, radius_doc, klasse):
    """
    Schachtkreise in der Draufsicht.
    Rueckgabe: Liste der Handles.
    """
    if not mittelpunkte_doc or radius_doc <= 0:
        return []

    handles = []
    vorher = _klasse_setzen(klasse)
    try:
        for mx, my in mittelpunkte_doc:
            vs.Oval(mx - radius_doc, my + radius_doc,
                    mx + radius_doc, my - radius_doc)
            h = vs.LNewObj()
            if vwutils.handle_ok(h):
                try:
                    vs.SetClass(h, klasse)
                except Exception:
                    pass
                handles.append(h)
    finally:
        _klasse_setzen(vorher)

    return handles
