# -*- coding: utf-8 -*-
"""
PHASE 17 - Geometrie des Werkzeugs "Rigole komplex".

Zeichnet innerhalb der Symboldefinition:

    * die Umgrenzung als Polygon                Klasse ...-2D
    * je belegtem Korbplatz ein Rechteck        Klasse ...-2D
    * je belegtem Korbplatz und Lage ein Korbsymbol   Klasse ...-3D
    * Kontrollschaechte                         Klasse ...-Schacht

KOORDINATEN
-----------
Alles hier rechnet im LOKALEN System der Symboldefinition. Sein Nullpunkt
ist die linke untere Ecke der belegten Huellbox, seine x-Achse ist die
Rasterrichtung. Die fertige Instanz wird spaeter mit dem Rasterwinkel
eingefuegt (vs.Symbol nimmt den Winkel entgegen) - hier muss also nichts
zurueckgedreht werden.

Das Umgrenzungspolygon wird dabei mitgezeichnet, damit im Plan sichtbar
bleibt, wonach gefuellt wurde. Das vom Anwender GEZEICHNETE Polygon bleibt
davon unberuehrt; es liegt weiterhin in der Zeichnung.

Kompatibilitaet: Python 3.9.2 (Vectorworks 2026)
"""

import vs

from rigole_config.constants import (
    CLASS_2D, CLASS_3D, GRID_MAX_LINES, WARN_BASKETS_TOTAL,
)
from rigole_core.calculations import symbol_anchor_offset
from rigole_vw import vwutils
from rigole_vw.geometry_3d import GeometrieFehler


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


def _klasse_zuweisen(h, klasse):
    try:
        vs.SetClass(h, klasse)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 2D
# ---------------------------------------------------------------------------

def draw_plan(ergebnis, unit_ctx, rollback, mit_zellen=True):
    """
    Draufsicht im lokalen System.

    mit_zellen   True = jeder belegte Korbplatz bekommt ein Rechteck.
                 Bei sehr vielen Koerben wird das automatisch weggelassen,
                 sonst wird der Plan unlesbar und die Datei gross.

    Rueckgabe: Liste der erzeugten Handles.
    """
    handles = []
    vorher = _klasse_setzen(CLASS_2D)
    try:
        # --- Umgrenzung ---------------------------------------------------
        punkte = ergebnis.polygon_lokal_verschoben()
        if len(punkte) >= 3:
            koordinaten = []
            for x_m, y_m in punkte:
                koordinaten.append(unit_ctx.to_doc(x_m))
                koordinaten.append(unit_ctx.to_doc(y_m))
            try:
                vs.ClosePoly()
                vs.Poly(*koordinaten)
            except Exception as ex:
                raise GeometrieFehler(
                    u"Die Umgrenzung konnte nicht gezeichnet werden.\n\n"
                    u"Technische Meldung: %r" % (ex,))
            h = rollback.merke_letztes()
            if not vwutils.handle_ok(h):
                raise GeometrieFehler(
                    u"Die Umgrenzung konnte nicht gezeichnet werden.")
            _klasse_zuweisen(h, CLASS_2D)
            handles.append(h)

        # --- Korbplaetze ---------------------------------------------------
        zellen = ergebnis.zellen or []
        if mit_zellen and 0 < len(zellen) <= GRID_MAX_LINES:
            for zelle in zellen:
                x0, y0, x1, y1 = ergebnis.zellrechteck_lokal(zelle)
                vs.Rect(unit_ctx.to_doc(x0), unit_ctx.to_doc(y1),
                        unit_ctx.to_doc(x1), unit_ctx.to_doc(y0))
                h = rollback.merke_letztes()
                if vwutils.handle_ok(h):
                    _klasse_zuweisen(h, CLASS_2D)
                    handles.append(h)
    finally:
        _klasse_setzen(vorher)

    return handles


# ---------------------------------------------------------------------------
# 3D
# ---------------------------------------------------------------------------

def place_baskets(ergebnis, unit_ctx, rollback, symbol_name,
                  anchor="corner", fortschritt=True):
    """
    Setzt die Korbsymbole auf allen belegten Korbplaetzen, Lage fuer Lage.

    Die unterste Lage liegt auf z = 0 des lokalen Systems; die fertige
    Instanz wird spaeter als Ganzes auf die Planungshoehe gehoben - genau
    wie bei der rechteckigen Rigole.
    """
    if not vwutils.symbol_exists(symbol_name):
        raise GeometrieFehler(
            u"Das Symbol „%s“ ist im aktuellen Dokument nicht vorhanden.\n\n"
            u"Bitte importieren Sie es zuerst in die Zeichnung oder waehlen "
            u"Sie ein anderes Symbol." % (symbol_name,))

    anker_x_m, anker_y_m = symbol_anchor_offset(
        ergebnis.basket_length, ergebnis.basket_width, anchor)

    zellen = ergebnis.zellen or []
    lagen = int(ergebnis.count_height)
    gesamt = len(zellen) * lagen

    zeige = bool(fortschritt) and gesamt > WARN_BASKETS_TOTAL
    if zeige:
        try:
            vs.ProgressDlgOpen(u"Rigole wird aufgebaut", False)
            vs.ProgressDlgSetMeter(u"%d Rigolenkoerper werden gesetzt ..."
                                   % (gesamt,))
        except Exception:
            zeige = False

    handles = []
    vorher = _klasse_setzen(CLASS_3D)
    try:
        zaehler = 0
        for lage in range(lagen):
            z_m = lage * float(ergebnis.basket_height)
            z_doc = unit_ctx.to_doc(z_m)
            for zelle in zellen:
                x0, y0, _x1, _y1 = ergebnis.zellrechteck_lokal(zelle)
                x = unit_ctx.to_doc(x0 + anker_x_m)
                y = unit_ctx.to_doc(y0 + anker_y_m)

                vs.Symbol(symbol_name, (x, y), 0.0)
                h = rollback.merke_letztes()
                if not vwutils.handle_ok(h):
                    raise GeometrieFehler(
                        u"Der Rigolenkoerper %d von %d konnte nicht erzeugt "
                        u"werden." % (zaehler + 1, gesamt))
                _klasse_zuweisen(h, CLASS_3D)
                handles.append(h)

                if z_doc != 0.0:
                    try:
                        vs.Move3DObj(h, 0.0, 0.0, z_doc)
                    except Exception as ex:
                        raise GeometrieFehler(
                            u"Die Hoehenlage des Rigolenkoerpers %d konnte "
                            u"nicht gesetzt werden.\n\n"
                            u"Technische Meldung: %r" % (zaehler + 1, ex))

                zaehler += 1
                if zeige and (zaehler % 25 == 0):
                    try:
                        vs.ProgressDlgYield(zaehler)
                    except Exception:
                        pass
    finally:
        _klasse_setzen(vorher)
        if zeige:
            try:
                vs.ProgressDlgClose()
            except Exception:
                pass

    return handles
