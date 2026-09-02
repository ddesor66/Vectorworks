# -*- coding: utf-8 -*-
"""
Geometrie der KIESRIGOLE.

Erzeugt wird ein Schuettkoerper mit einem mittig liegenden Draenrohr:

    Draufsicht                        Vorderansicht (Schnitt)
    ┌──────────────────────┐          ┌──────────────────────┐
    │ - - - - - - - - - -  │          │                      │
    │ - - - - - - - - - -  │          │  ●                   │  ● = Rohr
    └──────────────────────┘          └──────────────────────┘

    x = Laengsrichtung, y = Breite, z = Hoehe
    Nullpunkt = vordere linke untere Ecke

Klassen (Vorgabe des Anwenders):
    PD-EW-Kiesrigole-Füllung     Schuettkoerper und Umgrenzung im Plan
    PD-EW-Kiesrigole-Drainrohr   Rohrkoerper und Rohrkontur im Plan
    PD-EW-Kiesrigole-Schacht     Kontrollschaechte (Koerper und Plankreis)

Kompatibilitaet: Python 3.9.2 (Vectorworks 2026)
"""

import vs

from rigole_config.constants import (
    CLASS_KIES_ROHR, CLASS_KIES_FUELLUNG, CLASS_KIES_SCHACHT,
)
from rigole_vw import vwutils, geometry_schacht


class KiesGeometrieFehler(Exception):
    pass


# ---------------------------------------------------------------------------
# Hilfen
# ---------------------------------------------------------------------------

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
    """
    Klasse ausdruecklich setzen - die aktive Klasse allein ist nicht
    verlaesslich (siehe Kommentar in geometry_2d.py).
    """
    try:
        vs.SetClass(h, klasse)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 3D - Schuettkoerper
# ---------------------------------------------------------------------------

def build_fuellkoerper(ergebnis, unit_ctx, origin_doc=(0.0, 0.0)):
    """
    Quader aus Kies bzw. Schotter, Unterkante auf z = 0.
    Rueckgabe: Handle oder None.
    """
    x0, y0 = float(origin_doc[0]), float(origin_doc[1])
    laenge = unit_ctx.to_doc(ergebnis.total_length)
    breite = unit_ctx.to_doc(ergebnis.total_width)
    hoehe = unit_ctx.to_doc(ergebnis.total_height)

    if laenge <= 0 or breite <= 0 or hoehe <= 0:
        raise KiesGeometrieFehler(
            u"Die Abmessungen der Kiesrigole sind ungueltig.")

    vorher = _klasse_setzen(CLASS_KIES_FUELLUNG)
    try:
        vs.BeginXtrd(0.0, hoehe)
        vs.Rect(x0, y0 + breite, x0 + laenge, y0)
        vs.EndXtrd()
        h = vs.LNewObj()
    except Exception as ex:
        raise KiesGeometrieFehler(
            u"Der Schuettkoerper konnte nicht erzeugt werden.\n\n"
            u"Technische Meldung: %r" % (ex,))
    finally:
        _klasse_setzen(vorher)

    if not vwutils.handle_ok(h):
        raise KiesGeometrieFehler(u"Der Schuettkoerper konnte nicht erzeugt "
                                  u"werden.")
    _klasse_zuweisen(h, CLASS_KIES_FUELLUNG)
    return h


# ---------------------------------------------------------------------------
# 3D - Draenrohr
# ---------------------------------------------------------------------------

def build_draenrohr(ergebnis, unit_ctx, origin_doc=(0.0, 0.0)):
    """
    Draenrohr als liegende Zylinder, mittig ueber die Laenge.

    An jedem Kontrollschacht ist das Rohr durchtrennt; gebaut wird deshalb
    je Rohrstueck ein eigener Zylinder. Ohne Schaechte bleibt es bei einem
    einzigen durchgehenden Rohr.

    Rueckgabe: Liste der erzeugten Handles (kann leer sein).
    """
    if not ergebnis.hat_rohr:
        return []

    segmente = ergebnis.rohr_segmente or [(0.0, ergebnis.rohr_laenge_brutto)]
    handles = []
    try:
        for anfang, ende in segmente:
            h = _build_rohrstueck(ergebnis, unit_ctx, origin_doc,
                                  float(anfang), float(ende))
            if h is not None:
                handles.append(h)
    except Exception:
        for h in handles:
            _aufraeumen(h)
        raise
    return handles


def _build_rohrstueck(ergebnis, unit_ctx, origin_doc, von_m, bis_m):
    """
    Ein einzelnes Rohrstueck zwischen zwei Schaechten.

    Vorgehen
    --------
    Vectorworks kennt keine Funktion, die einen liegenden Zylinder direkt
    erzeugt. Deshalb:
        1. senkrechter Zylinder ueber vs.BeginXtrd + vs.Oval
        2. mit vs.Set3DRot um 90 Grad um die Y-Achse kippen
        3. mit vs.Get3DCntr die tatsaechliche Lage messen und ihn per
           vs.Move3DObj an die Sollposition schieben

    Schritt 3 ist der Kniff: Ob die Drehung den Zylinder in die positive
    oder negative X-Richtung legt, haengt vom Drehsinn ab. Statt das zu
    raten, wird die Lage gemessen und der Koerper von dort aus an seinen
    Platz geschoben. Das Ergebnis stimmt damit unabhaengig vom Drehsinn.

    Rueckgabe: Handle oder None.
    """
    if not ergebnis.hat_rohr:
        return None

    x0, y0 = float(origin_doc[0]), float(origin_doc[1])
    von = unit_ctx.to_doc(von_m)
    bis = unit_ctx.to_doc(bis_m)
    laenge = bis - von
    radius = unit_ctx.to_doc(ergebnis.rohr_durchmesser) / 2.0
    if laenge <= 0 or radius <= 0:
        return None

    # Sollposition des Rohrmittelpunktes
    ziel_x = x0 + von + laenge / 2.0
    ziel_y = y0 + unit_ctx.to_doc(ergebnis.total_width) / 2.0
    ziel_z = unit_ctx.to_doc(ergebnis.rohr_achse)

    vorher = _klasse_setzen(CLASS_KIES_ROHR)
    h = None
    try:
        # 1 - senkrechter Zylinder, Achse auf (0, 0), Hoehe = Rohrlaenge
        vs.BeginXtrd(0.0, laenge)
        vs.Oval(-radius, radius, radius, -radius)
        vs.EndXtrd()
        h = vs.LNewObj()
        if not vwutils.handle_ok(h):
            raise KiesGeometrieFehler(u"Der Rohrkoerper konnte nicht erzeugt "
                                      u"werden.")

        # 2 - um 90 Grad um die Y-Achse kippen, Drehpunkt Ursprung
        vs.Set3DRot(h, 0.0, 90.0, 0.0, 0.0, 0.0, 0.0)

        # 3 - tatsaechliche Lage messen und an die Sollposition schieben
        mitte = vs.Get3DCntr(h)
        ist_x, ist_y, ist_z = _mittelpunkt(mitte)
        if ist_x is None:
            raise KiesGeometrieFehler(
                u"Die Lage des Draenrohres konnte nicht bestimmt werden "
                u"(Get3DCntr lieferte keinen brauchbaren Wert).")
        vs.Move3DObj(h, ziel_x - ist_x, ziel_y - ist_y, ziel_z - ist_z)
    except KiesGeometrieFehler:
        _aufraeumen(h)
        raise
    except Exception as ex:
        _aufraeumen(h)
        raise KiesGeometrieFehler(
            u"Das Draenrohr konnte nicht erzeugt werden.\n\n"
            u"Technische Meldung: %r" % (ex,))
    finally:
        _klasse_setzen(vorher)

    _klasse_zuweisen(h, CLASS_KIES_ROHR)
    return h


# ---------------------------------------------------------------------------
# 3D - Kontrollschaechte
# ---------------------------------------------------------------------------

def build_schaechte(ergebnis, unit_ctx, origin_doc=(0.0, 0.0)):
    """
    Senkrechte Rundschaechte auf der Draenrohrachse.

    Anders als beim Rohr braucht es hier keine Drehung: vs.BeginXtrd
    extrudiert ohnehin in Z-Richtung. Die Extrusionsgrenzen sind damit
    unmittelbar Unter- und Oberkante des Schachtes.

    Die Hoehen sind im Ergebnis als absolute Koten hinterlegt; innerhalb der
    Symboldefinition liegt die Kiessohle auf z = 0, deshalb wird die
    Unterkante der Rigole (ergebnis.uk) abgezogen.

    Rueckgabe: Liste der erzeugten Handles.
    """
    if not ergebnis.hat_schacht:
        return []

    if not ergebnis.hat_schacht:
        return []

    radius = unit_ctx.to_doc(ergebnis.schacht_durchmesser) / 2.0
    z_unten = unit_ctx.to_doc(float(ergebnis.schacht_uk) - float(ergebnis.uk))
    z_oben = unit_ctx.to_doc(float(ergebnis.schacht_ok) - float(ergebnis.uk))

    try:
        return geometry_schacht.build_koerper(
            _schacht_mittelpunkte(ergebnis, unit_ctx, origin_doc), radius,
            z_unten, z_oben, CLASS_KIES_SCHACHT)
    except geometry_schacht.SchachtFehler as ex:
        raise KiesGeometrieFehler(u"%s" % (ex,))


def _schacht_mittelpunkte(ergebnis, unit_ctx, origin_doc):
    """Mittelpunkte der Schaechte in Dokumenteinheiten."""
    x0, y0 = float(origin_doc[0]), float(origin_doc[1])
    mitte_y = y0 + unit_ctx.to_doc(ergebnis.total_width) / 2.0
    return [(x0 + unit_ctx.to_doc(float(p)), mitte_y)
            for p in (ergebnis.schacht_positionen or ())]


def _mittelpunkt(ergebnis_get3dcntr):
    """
    Wertet die Rueckgabe von vs.Get3DCntr aus: (p, zValue) mit p = (x, y).
    Faengt den Platzhalter 1e+97 ab und liefert dann (None, None, None).
    """
    try:
        p, z = ergebnis_get3dcntr
        x, y = float(p[0]), float(p[1])
        z = float(z)
    except Exception:
        return (None, None, None)
    for wert in (x, y, z):
        if abs(wert) >= vwutils.UNGUELTIG:
            return (None, None, None)
    return (x, y, z)


def _aufraeumen(h):
    if vwutils.handle_ok(h):
        try:
            vs.DelObject(h)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 2D - Draufsicht
# ---------------------------------------------------------------------------

def draw_plan(ergebnis, unit_ctx, origin_doc=(0.0, 0.0), mit_rohr=True):
    """
    Draufsicht: Aussenumgrenzung der Schuettung, dazu die Rohrkontur als
    zwei Laengslinien.

    Rueckgabe: Liste der erzeugten Handles.
    """
    x0, y0 = float(origin_doc[0]), float(origin_doc[1])
    laenge = unit_ctx.to_doc(ergebnis.total_length)
    breite = unit_ctx.to_doc(ergebnis.total_width)
    handles = []

    # --- Umgrenzung der Schuettung ----------------------------------------
    vorher = _klasse_setzen(CLASS_KIES_FUELLUNG)
    try:
        vs.Rect(x0, y0 + breite, x0 + laenge, y0)
        h = vs.LNewObj()
        if not vwutils.handle_ok(h):
            raise KiesGeometrieFehler(
                u"Die Aussenumgrenzung konnte nicht erzeugt werden.")
        _klasse_zuweisen(h, CLASS_KIES_FUELLUNG)
        handles.append(h)
    finally:
        _klasse_setzen(vorher)

    # --- Rohrkontur --------------------------------------------------------
    # Je Rohrstueck ein eigenes Linienpaar - an den Schaechten ist das Rohr
    # unterbrochen, und genau so soll es auch im Plan erscheinen.
    if mit_rohr and ergebnis.hat_rohr:
        radius = unit_ctx.to_doc(ergebnis.rohr_durchmesser) / 2.0
        mitte_y = y0 + breite / 2.0
        segmente = ergebnis.rohr_segmente or [(0.0, ergebnis.rohr_laenge_brutto)]
        vorher = _klasse_setzen(CLASS_KIES_ROHR)
        try:
            for anfang, ende in segmente:
                von = x0 + unit_ctx.to_doc(float(anfang))
                bis = x0 + unit_ctx.to_doc(float(ende))
                if bis - von <= 0:
                    continue
                for versatz in (-radius, radius):
                    vs.MoveTo(von, mitte_y + versatz)
                    vs.LineTo(bis, mitte_y + versatz)
                    h = vs.LNewObj()
                    if vwutils.handle_ok(h):
                        _klasse_zuweisen(h, CLASS_KIES_ROHR)
                        handles.append(h)
        finally:
            _klasse_setzen(vorher)

    # --- Schaechte ---------------------------------------------------------
    if ergebnis.hat_schacht:
        handles.extend(geometry_schacht.draw_kreise(
            _schacht_mittelpunkte(ergebnis, unit_ctx, origin_doc),
            unit_ctx.to_doc(ergebnis.schacht_durchmesser) / 2.0,
            CLASS_KIES_SCHACHT))

    return handles


def measure_symbol(symbol_name, unit_ctx):
    """
    Misst die Abmessungen einer vorhandenen Kiesrigolen-Symboldefinition,
    damit bei Namensgleichheit erkannt wird, ob sie zur neuen Rigole passt.
    Nutzt dieselbe Technik wie bei den Korbsymbolen.
    """
    from rigole_vw import geometry_3d
    return geometry_3d.measure_symbol(symbol_name, unit_ctx)
