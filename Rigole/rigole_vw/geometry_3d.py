# -*- coding: utf-8 -*-
"""
PHASE 7 - 3D-Darstellung: Vervielfaeltigung der Korbsymbole.

Anordnung als dreidimensionales Raster:

    x = Einfuegepunkt X + i * Korblaenge      (i = hintereinander)
    y = Einfuegepunkt Y + j * Korbbreite      (j = nebeneinander)
    z = Rigolen-UK      + k * Korbhoehe       (k = uebereinander)

Gemessen in Pruefbericht A2 (U6): Nach vs.Symbol() setzt
vs.Move3DObj(h, 0, 0, z) die Einfuegehoehe der Instanz zuverlaessig -
GetSymLoc3D meldete anschliessend genau den gewuenschten Z-Wert, und die
Sichtpruefung in der Vorderansicht hat es bestaetigt. Move3DObj verschiebt
RELATIV; eine frisch gesetzte Instanz startet bei z = 0, ein Aufruf je Korb
genuegt also.

Version 1 geht davon aus, dass das gewaehlte Symbol bereits die richtigen
Abmessungen hat. Eine automatische Skalierung ist bewusst nicht enthalten.

Kompatibilitaet: Python 3.9.2 (Vectorworks 2026)
"""

import vs
import math

from rigole_config.constants import CLASS_3D, WARN_BASKETS_TOTAL
from rigole_core.calculations import iter_basket_positions, symbol_anchor_offset
from rigole_vw import vwutils


class GeometrieFehler(Exception):
    pass


def place_baskets(origin_doc, ergebnis, unit_ctx, rollback,
                  symbol_name, anchor="corner", z_offset_doc=0.0,
                  fortschritt=True, base_z_m=None):
    """
    Setzt alle Symbolinstanzen.

    origin_doc    (x, y) Einfuegepunkt in DOKUMENTEINHEITEN
    ergebnis      RigoleResult (Meter)
    unit_ctx      UnitContext
    rollback      vwutils.Rollback
    symbol_name   Name der Symboldefinition
    anchor        "corner" oder "center"
    z_offset_doc  zusaetzlicher Z-Versatz in Dokumenteinheiten
                  (z. B. minus Ebenenhoehe)
    base_z_m      Hoehe der untersten Lage in Metern. None = Rigolen-UK.
                  Beim Aufbau INNERHALB einer Symboldefinition wird 0
                  uebergeben - dort liegt die Unterkante auf dem
                  Symbolnullpunkt, und die fertige Instanz wird spaeter als
                  Ganzes auf die Planungshoehe gehoben.

    Rueckgabe: Liste der erzeugten Handles.
    """
    # --- Symbol EINMAL pruefen, vor der Schleife (Performance, Punkt 30) --
    if not vwutils.symbol_exists(symbol_name):
        raise GeometrieFehler(
            u"Das Symbol „%s“ ist im aktuellen Dokument nicht vorhanden.\n\n"
            u"Bitte importieren Sie es zuerst in die Zeichnung oder waehlen "
            u"Sie ein anderes Symbol." % (symbol_name,))

    x0, y0 = float(origin_doc[0]), float(origin_doc[1])

    # Versatz, falls der Einfuegepunkt des Symbols mittig liegt
    anker_x_m, anker_y_m = symbol_anchor_offset(
        ergebnis.basket_length, ergebnis.basket_width, anchor)
    anker_x = unit_ctx.to_doc(anker_x_m)
    anker_y = unit_ctx.to_doc(anker_y_m)

    gesamt = ergebnis.basket_count
    zeige_fortschritt = bool(fortschritt) and gesamt > WARN_BASKETS_TOTAL
    if zeige_fortschritt:
        try:
            vs.ProgressDlgOpen(u"Rigole wird aufgebaut", False)
            vs.ProgressDlgSetMeter(u"%d Rigolenkoerper werden gesetzt ..."
                                   % (gesamt,))
        except Exception:
            zeige_fortschritt = False

    handles = []
    vorherige_klasse = _klasse_setzen(CLASS_3D)
    try:
        zaehler = 0
        for i, j, k, x_m, y_m, z_m in iter_basket_positions(
                ergebnis.count_length, ergebnis.count_width,
                ergebnis.count_height,
                ergebnis.basket_length, ergebnis.basket_width,
                ergebnis.basket_height,
                origin_x=0.0, origin_y=0.0,
                base_z=(ergebnis.uk if base_z_m is None else float(base_z_m))):

            x = x0 + unit_ctx.to_doc(x_m) + anker_x
            y = y0 + unit_ctx.to_doc(y_m) + anker_y
            z = unit_ctx.to_doc(z_m) + float(z_offset_doc)

            vs.Symbol(symbol_name, (x, y), 0.0)
            h = rollback.merke_letztes()
            if not vwutils.handle_ok(h):
                raise GeometrieFehler(
                    u"Der Rigolenkoerper %d von %d konnte nicht erzeugt "
                    u"werden." % (zaehler + 1, gesamt))
            # Klasse ausdruecklich zuweisen - die aktive Klasse allein ist
            # nicht verlaesslich (siehe Kommentar in geometry_2d.py).
            try:
                vs.SetClass(h, CLASS_3D)
            except Exception:
                pass
            handles.append(h)

            if z != 0.0:
                try:
                    vs.Move3DObj(h, 0.0, 0.0, z)
                except Exception as ex:
                    raise GeometrieFehler(
                        u"Die Hoehenlage des Rigolenkoerpers %d konnte nicht "
                        u"gesetzt werden.\n\nTechnische Meldung: %r"
                        % (zaehler + 1, ex))

            zaehler += 1
            if zeige_fortschritt and (zaehler % 25 == 0):
                try:
                    vs.ProgressDlgYield(zaehler)
                except Exception:
                    pass
    finally:
        _klasse_setzen(vorherige_klasse)
        if zeige_fortschritt:
            try:
                vs.ProgressDlgClose()
            except Exception:
                pass

    return handles


def ensure_basket_symbol(symbol_name, laenge_m, breite_m, hoehe_m, unit_ctx):
    """
    Stellt sicher, dass die Symboldefinition fuer einen Rigolenkorb existiert.
    Fehlt sie, wird sie erzeugt: ein Quader mit genau den uebergebenen Massen.

    Aufbau der Definition:
        Einfuegepunkt      = vordere linke untere Ecke
        Ausdehnung         = 0..Laenge (X), 0..Breite (Y), 0..Hoehe (Z)
        Klasse des Inhalts = CLASS_3D (= PD-EW-RW-Rigole)

    Rueckgabe: (existierte_schon, wurde_erzeugt)
    Loest GeometrieFehler aus, wenn die Definition danach nicht vorliegt.

    Hinweise zur Umsetzung
    ----------------------
    * vs.BeginSym verwendet laut Referenz den BENUTZERNULLPUNKT als
      Einfuegepunkt. Da alle Skriptkoordinaten ohnehin auf diesen Nullpunkt
      bezogen sind, liegt ein bei (0,0) gezeichnetes Rechteck automatisch
      genau auf dem Einfuegepunkt. Der Nullpunkt des Dokuments wird deshalb
      NICHT veraendert - vs.SetOriginAbsolute waere ein Eingriff in die
      Zeichnung des Anwenders.
    * Die Symboldefinition ist eine Ressource, keine Zeichnungsgeometrie. Sie
      bleibt erhalten, wenn ein spaeterer Bauschritt zurueckgenommen wird -
      das ist gewollt, sie wird beim naechsten Mal wiederverwendet.
    """
    if not symbol_name:
        raise GeometrieFehler(
            u"Fuer den gewaehlten Korbtyp konnte kein Symbolname gebildet "
            u"werden. Bitte die Abmessungen pruefen.")

    if vwutils.symbol_exists(symbol_name):
        return (True, False)

    # Ein Name, der schon vergeben ist - aber nicht an eine Symboldefinition
    h_fremd = vs.GetObject(symbol_name)
    if vwutils.handle_ok(h_fremd):
        raise GeometrieFehler(
            u"Der Name „%s“ ist im Dokument bereits vergeben, gehoert aber "
            u"nicht zu einer Symboldefinition (Objekttyp %s).\n\n"
            u"Bitte in rigole_config/basket_types.py bei diesem Korbtyp unter "
            u"\"symbol\" einen anderen Namen eintragen."
            % (symbol_name, vs.GetTypeN(h_fremd)))

    laenge = unit_ctx.to_doc(laenge_m)
    breite = unit_ctx.to_doc(breite_m)
    hoehe = unit_ctx.to_doc(hoehe_m)
    if laenge <= 0 or breite <= 0 or hoehe <= 0:
        raise GeometrieFehler(
            u"Die Korbabmessungen sind ungueltig - das Symbol kann nicht "
            u"erzeugt werden.")

    vorherige_klasse = _klasse_setzen(CLASS_3D)
    try:
        vs.BeginSym(symbol_name)
        try:
            vs.BeginXtrd(0.0, hoehe)
            vs.Rect(0.0, breite, laenge, 0.0)
            vs.EndXtrd()
        finally:
            vs.EndSym()
    except Exception as ex:
        raise GeometrieFehler(
            u"Die Symboldefinition „%s“ konnte nicht erzeugt werden.\n\n"
            u"Technische Meldung: %r" % (symbol_name, ex))
    finally:
        _klasse_setzen(vorherige_klasse)

    if not vwutils.symbol_exists(symbol_name):
        raise GeometrieFehler(
            u"Die Symboldefinition „%s“ wurde angelegt, ist aber nicht "
            u"auffindbar. Bitte den Ressourcenmanager pruefen."
            % (symbol_name,))

    return (False, True)


def measure_symbol(symbol_name, unit_ctx):
    """
    Misst die tatsaechlichen Abmessungen einer Symboldefinition in METERN.

    Dazu wird kurz eine Probeinstanz gesetzt, vermessen und wieder geloescht.

    vs.Get3DInfo liefert laut Referenz die Werte in der Reihenfolge
    delta-Y, delta-X, delta-Z - die Parameternamen (height, width, depth) sind
    dort ausdruecklich als irrefuehrend gekennzeichnet. Weil ich mich darauf
    nicht blind verlassen will, gibt diese Funktion alle drei Werte
    unsortiert zurueck; der Vergleich erfolgt in dimensions_match() ueber die
    sortierte Reihenfolge und ist damit unabhaengig von der Achszuordnung.

    Rueckgabe: (a, b, c) in Metern oder None, wenn nicht messbar.
    """
    if not vwutils.symbol_exists(symbol_name):
        return None
    h = None
    try:
        vs.Symbol(symbol_name, (0.0, 0.0), 0.0)
        h = vs.LNewObj()
        if not vwutils.handle_ok(h):
            return None
        werte = vs.Get3DInfo(h)
        if not werte or len(werte) < 3:
            return None
        return tuple(unit_ctx.from_doc(float(w)) for w in werte[:3])
    except Exception:
        return None
    finally:
        if vwutils.handle_ok(h):
            try:
                vs.DelObject(h)
            except Exception:
                pass


def dimensions_match(gemessen, laenge, breite, hoehe, toleranz):
    """
    Vergleicht die gemessenen Symbolabmessungen mit den eingegebenen
    Korbmassen - unabhaengig davon, welcher Wert welcher Achse entspricht.

    Rueckgabe: True, wenn alle drei Masse innerhalb der Toleranz passen.
    """
    if not gemessen:
        return False
    try:
        a = sorted(float(w) for w in gemessen)
        b = sorted((float(laenge), float(breite), float(hoehe)))
    except Exception:
        return False
    if len(a) != 3 or any(not math.isfinite(w) or w <= 0.0 for w in a + b):
        return False
    if not math.isfinite(float(toleranz)) or float(toleranz) < 0:
        return False
    for x, y in zip(a, b):
        if abs(x - y) > float(toleranz):
            return False
    return True


def layer_elevation_doc():
    """
    Hoehe der aktiven Konstruktionsebene in DOKUMENTEINHEITEN.

    Pruefbericht A hat bestaetigt (U4): GetLayerElevation arbeitet in
    Dokumenteinheiten, nicht in Millimetern - geschrieben wurde 1,0 in einem
    Meter-Dokument, gelesen wurde 1,0, und Vectorworks zeigte 1,00 m.
    """
    try:
        basis, dicke = vs.GetLayerElevation(vs.ActLayer())
        return float(basis)
    except Exception:
        return 0.0


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
