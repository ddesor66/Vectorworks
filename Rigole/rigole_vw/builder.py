# -*- coding: utf-8 -*-
"""
PHASE 9 (Kern) - Zusammenbau der Rigole.

Setzt Symbolerzeugung, 2D, 3D, Datensatz und Beschriftung zu einem einzigen,
transaktionsaehnlichen Vorgang zusammen (Anforderung Punkt 23): Geht etwas
schief, wird alles bereits Erzeugte wieder entfernt.

Ergebnis in der Zeichnung
-------------------------
    Symbolinstanz „Rigole RIG-001"      Klasse PD-EW-RW-Rigole
        Symboldefinition = Bezeichnung, z. B. „RRB 01"        <- traegt DB_Rigole
        │
        ├── Rechteck + Rasterlinien     Klasse PD-EW-RW-Rigole-2D
        ├── n x Korbsymbol              Klasse PD-EW-RW-Rigole-3D
        └── Kontrollschaechte           Klasse PD-EW-RW-Rigole-Schacht
            (Koerper und Plankreise)

    Textobjekt Beschriftung             Klasse PD-EW-RW-Rigole-Beschriftung
                                        (ausserhalb, frei verschiebbar,
                                         ohne Datensatz)

Warum die Geometrie DIREKT in der Symboldefinition entsteht
-----------------------------------------------------------
Ein nachtraegliches Umwandeln einer Gruppe in ein Symbol gibt es in der
Skript-API nicht - der Menuebefehl dafuer waere ueber vs.DoMenuTextByName
nur sprachabhaengig erreichbar und damit unzuverlaessig. Der saubere Weg ist,
die Objekte gleich zwischen vs.BeginSym und vs.EndSym zu erzeugen.

Innerhalb der Definition wird BEWUSST NICHT gruppiert: Gruppieren setzt eine
Auswahl voraus, und vs.BeginSym hebt laut Referenz die Auswahl auf. Die
Trennung von 2D und 3D uebernehmen die Klassen.

Hoehenlage
----------
Innerhalb der Definition liegt die Unterkante der Rigole auf z = 0. Die
fertige Instanz wird anschliessend als Ganzes auf die Planungshoehe gehoben
(vs.Move3DObj). Damit ist dieselbe Symboldefinition auf jeder Hoehe
verwendbar.

Kompatibilitaet: Python 3.9.2 (Vectorworks 2026)
"""

import vs

from rigole_config.constants import (
    CLASS_MAIN, CLASS_SCHACHT, CLASSES_ALL, GROUP_NAME_TEMPLATE,
    LABEL_NAME_TEMPLATE, SYMBOL_TOLERANZ,
)
from rigole_vw import (vwutils, records, geometry_2d, geometry_3d,
                       geometry_schacht, labeling)


class BauFehler(Exception):
    pass


# ---------------------------------------------------------------------------
# Symbolname der Rigole
# ---------------------------------------------------------------------------

def rigole_symbolname(bezeichnung, rigole_id):
    """
    Der Symbolname ist die im Dialog eingegebene Bezeichnung.
    Ist sie leer, greift ersatzweise die Rigolen-ID.
    """
    name = str(bezeichnung or "").strip()
    if not name:
        name = u"Rigole %s" % (rigole_id,)
    return name


def _freier_symbolname(basisname, rigole_id):
    """Haengt die Rigolen-ID an, falls der Name schon vergeben ist."""
    kandidat = u"%s %s" % (basisname, rigole_id)
    if not vwutils.handle_ok(vs.GetObject(kandidat)):
        return kandidat
    for nummer in range(2, 100):
        weiterer = u"%s %s (%d)" % (basisname, rigole_id, nummer)
        if not vwutils.handle_ok(vs.GetObject(weiterer)):
            return weiterer
    return None


def _passt_vorhandenes_symbol(name, ergebnis, unit_ctx):
    """
    Prueft, ob eine bereits vorhandene Symboldefinition dieselbe Rigole
    beschreibt - verglichen werden die Gesamtabmessungen.
    Rueckgabe: (passt, gemessene_masse_in_metern_oder_None)
    """
    gemessen = geometry_3d.measure_symbol(name, unit_ctx)
    if gemessen is None:
        return (False, None)
    passt = geometry_3d.dimensions_match(
        gemessen, ergebnis.total_length, ergebnis.total_width,
        ergebnis.total_height, SYMBOL_TOLERANZ)
    return (passt, gemessen)


def _zahl(text, standard=None):
    try:
        return float(str(text).replace(",", "."))
    except (TypeError, ValueError):
        return standard


def _schaechte_passen_zum_symbol(symbolname, ergebnis):
    """
    Prueft, ob die vorhandene Symboldefinition dieselben Kontrollschaechte
    enthaelt wie die neu einzufuegende Rigole.

    Dieselbe Falle wie bei der Kiesrigole (24.08.2026): Die Aussenmasse
    aendern sich durch die Schaechte NICHT - sie sitzen oben auf und liegen
    in der Draufsicht innerhalb der Rigole. Ohne diesen Vergleich wuerde ein
    vorhandenes Symbol stillschweigend mit den alten Schaechten
    wiederverwendet.

    Verglichen wird die Schachtoberkante RELATIV zur Oberkante der Rigole -
    innerhalb der Symboldefinition zaehlt nur diese Differenz.

    Rueckgabe: (passt, klartext_begruendung)
    """
    eintraege = records.rigole_daten_zu_symbol(symbolname)
    if not eintraege:
        # Nichts zu vergleichen. Solange die neue Rigole ohne Schaechte
        # auskommt, ist das unkritisch - sonst muss nachgefragt werden.
        if not ergebnis.hat_schacht:
            return (True, u"")
        return (False, u"Zu diesem Symbol liegt keine Rigole mit Datensatz "
                       u"im Dokument. Das Werkzeug kann deshalb nicht "
                       u"feststellen, welche Schaechte darin stecken.")

    neu_dn = str(ergebnis.schacht_dn or "")
    for eintrag in eintraege:
        alt_dn = str(eintrag.get("schacht_dn") or "")
        if alt_dn != neu_dn:
            return (False, u"Schacht - vorhanden: %s, neu: %s"
                           % (alt_dn or u"ohne", neu_dn or u"ohne"))

        alt_anzahl = _zahl(eintrag.get("schacht_anz"), 0.0)
        if int(alt_anzahl or 0) != int(ergebnis.schacht_anzahl):
            return (False, u"Anzahl Schaechte - vorhanden: %d, neu: %d"
                           % (int(alt_anzahl or 0), ergebnis.schacht_anzahl))

        if ergebnis.hat_schacht:
            alt_ok = _zahl(eintrag.get("schacht_ok"))
            alt_rigole_ok = _zahl(eintrag.get("ok_rigole"))
            if alt_ok is None or alt_rigole_ok is None:
                return (False, u"Die Schachthoehe ist im vorhandenen Symbol "
                               u"nicht vermerkt (aelterer Datensatz).")
            alt_rel = alt_ok - alt_rigole_ok
            neu_rel = float(ergebnis.schacht_ok) - float(ergebnis.ok)
            if abs(alt_rel - neu_rel) > SYMBOL_TOLERANZ:
                return (False, u"Schachthoehe ueber OK Rigole - vorhanden: "
                               u"%.3f m, neu: %.3f m" % (alt_rel, neu_rel))

    return (True, u"")


def klaere_symbolname(bezeichnung, rigole_id, ergebnis, unit_ctx):
    """
    Bestimmt den zu verwendenden Symbolnamen und ob neu gebaut werden muss.

    Rueckgabe: (name, muss_erzeugt_werden)
    Rueckgabe (None, False) bedeutet: der Anwender hat abgebrochen.
    """
    name = rigole_symbolname(bezeichnung, rigole_id)
    h = vs.GetObject(name)

    if not vwutils.handle_ok(h):
        return (name, True)                     # Name frei

    if vs.GetTypeN(h) != vwutils.TYP_SYMBOLDEFINITION:
        # Name durch etwas anderes belegt (Klasse, Ebene, Gruppe ...)
        ersatz = _freier_symbolname(name, rigole_id)
        if ersatz is None:
            raise BauFehler(
                u"Der Name „%s“ ist bereits vergeben und es liess sich kein "
                u"freier Ersatzname bilden. Bitte eine andere Bezeichnung "
                u"eingeben." % (name,))
        return (ersatz, True)

    # Es gibt bereits ein Symbol dieses Namens
    passt, gemessen = _passt_vorhandenes_symbol(name, ergebnis, unit_ctx)
    if passt:
        schacht_passt, grund = _schaechte_passen_zum_symbol(name, ergebnis)
        if schacht_passt:
            return (name, False)                # wiederverwenden
        ersatz = _freier_symbolname(name, rigole_id)
        if ersatz is None:
            raise BauFehler(
                u"Der Name „%s“ ist vergeben und es liess sich kein freier "
                u"Ersatzname bilden." % (name,))
        weiter = vwutils.frage(
            u"Im Dokument gibt es bereits ein Symbol „%s“ mit denselben "
            u"Abmessungen, aber anderen Kontrollschaechten.\n\n"
            u"%s\n\n"
            u"Soll die neue Rigole als eigenes Symbol „%s“ angelegt werden?\n\n"
            u"Ja   = neues Symbol anlegen\n"
            u"Nein = abbrechen, es wird nichts erzeugt"
            % (name, grund, ersatz))
        if not weiter:
            return (None, False)
        return (ersatz, True)

    gem = u"unbekannt"
    if gemessen:
        gem = u" x ".join(("%.3f" % w).replace(".", ",")
                          for w in sorted(float(w) for w in gemessen))
    neu = u" x ".join(("%.3f" % w).replace(".", ",")
                      for w in sorted((ergebnis.total_length,
                                       ergebnis.total_width,
                                       ergebnis.total_height)))
    ersatz = _freier_symbolname(name, rigole_id)
    if ersatz is None:
        raise BauFehler(
            u"Der Name „%s“ ist vergeben und es liess sich kein freier "
            u"Ersatzname bilden." % (name,))

    weiter = vwutils.frage(
        u"Im Dokument gibt es bereits ein Symbol „%s“ - allerdings mit "
        u"anderen Abmessungen.\n\n"
        u"vorhandenes Symbol : %s m\n"
        u"neue Rigole        : %s m\n\n"
        u"Soll die neue Rigole als eigenes Symbol „%s“ angelegt werden?\n\n"
        u"Ja   = neues Symbol anlegen\n"
        u"Nein = abbrechen, es wird nichts erzeugt"
        % (name, gem, neu, ersatz))
    if not weiter:
        return (None, False)
    return (ersatz, True)


# ---------------------------------------------------------------------------
# Symboldefinition der Rigole aufbauen
# ---------------------------------------------------------------------------

def erzeuge_rigolensymbol(symbolname, werte, ergebnis, unit_ctx):
    """
    Baut die Symboldefinition der kompletten Rigole.
    Die Unterkante liegt dabei auf z = 0, der Einfuegepunkt vorne links.

    Rueckgabe: Anzahl der erzeugten Einzelobjekte.
    """
    rb_intern = vwutils.Rollback()      # nur zum Zaehlen; Symbolinhalt bleibt
    anzahl = 0
    ursprung = (0.0, 0.0)

    try:
        vs.BeginSym(symbolname)
        try:
            if werte.get("draw_3d"):
                handles = geometry_3d.place_baskets(
                    ursprung, ergebnis, unit_ctx, rb_intern,
                    werte.get("symbol_name"),
                    anchor=werte.get("symbol_anchor", "corner"),
                    z_offset_doc=0.0,
                    base_z_m=0.0)          # innerhalb der Definition ab 0
                anzahl += len(handles)

            if werte.get("draw_2d"):
                handles = geometry_2d.draw_plan(
                    ursprung, ergebnis, unit_ctx, rb_intern)
                anzahl += len(handles)

            # --- Kontrollschaechte ------------------------------------
            # Sie sitzen mittig auf der OBERKANTE eines Rigolenkorbes;
            # innerhalb der Definition ist das z = Gesamthoehe.
            if ergebnis.hat_schacht:
                mittelpunkte = _schacht_mittelpunkte(
                    ursprung, ergebnis, unit_ctx)
                radius = unit_ctx.to_doc(ergebnis.schacht_durchmesser) / 2.0
                if werte.get("draw_3d"):
                    anzahl += len(geometry_schacht.build_koerper(
                        mittelpunkte, radius,
                        unit_ctx.to_doc(ergebnis.total_height),
                        unit_ctx.to_doc(float(ergebnis.schacht_ok)
                                        - float(ergebnis.uk)),
                        CLASS_SCHACHT))
                if werte.get("draw_2d"):
                    anzahl += len(geometry_schacht.draw_kreise(
                        mittelpunkte, radius, CLASS_SCHACHT))
        finally:
            vs.EndSym()
    except Exception as ex:
        loesche_symboldefinition(symbolname)
        raise BauFehler(
            u"Die Symboldefinition „%s“ konnte nicht aufgebaut werden.\n\n"
            u"Technische Meldung: %r" % (symbolname, ex))

    if not vwutils.symbol_exists(symbolname):
        raise BauFehler(
            u"Die Symboldefinition „%s“ wurde nicht angelegt." % (symbolname,))

    return anzahl


def _schacht_mittelpunkte(origin_doc, ergebnis, unit_ctx):
    """
    Mittelpunkte der Kontrollschaechte in Dokumenteinheiten.
    Die Positionen kommen in Metern aus calculations.korb_schacht_positionen.
    """
    x0, y0 = float(origin_doc[0]), float(origin_doc[1])
    return [(x0 + unit_ctx.to_doc(float(x)), y0 + unit_ctx.to_doc(float(y)))
            for (x, y) in (ergebnis.schacht_positionen or ())]


def loesche_symboldefinition(symbolname):
    """Entfernt eine Symboldefinition - fuer den Fehlerfall."""
    try:
        h = vs.GetObject(symbolname)
        if vwutils.handle_ok(h) and \
                vs.GetTypeN(h) == vwutils.TYP_SYMBOLDEFINITION:
            vs.DelObject(h)
            return True
    except Exception:
        pass
    return False


def benenne(h, name):
    """
    Benennt ein Objekt. Schlaegt fehl, wenn der Name schon vergeben ist -
    das ist nicht kritisch, deshalb nur ein stiller Rueckgabewert.
    """
    try:
        vs.SetName(h, name)
        return vs.GetName(h) == name
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Hauptfunktion
# ---------------------------------------------------------------------------

def build_rigole(origin_doc, werte, ergebnis, unit_ctx,
                 rigole_id=None, label_position_doc=None, angle_deg=None):
    """
    Baut die komplette Rigole.

    origin_doc          (x, y) Einfuegepunkt in DOKUMENTEINHEITEN
    werte               Wertedictionary aus dem Dialog
    ergebnis            RigoleResult aus calculations.compute_rigole
    unit_ctx            UnitContext
    rigole_id           vorgegebene ID oder None (dann wird sie ermittelt)
    label_position_doc  (x, y) fuer die Beschriftung oder None

    Rueckgabe: dict mit
        rigole_id, symbolname, instance, label,
        anzahl_objekte, symbol_neu

    Loest BauFehler aus. In diesem Fall wurde alles Erzeugte wieder entfernt.
    """
    rb = vwutils.Rollback()
    info = {
        "rigole_id": None, "symbolname": None, "instance": None,
        "label": None, "anzahl_objekte": 0, "symbol_neu": False,
    }
    symbolname = None
    symbol_selbst_erzeugt = False

    try:
        # --- Vorbereitung -------------------------------------------------
        angle_deg = (vwutils.rigole_angle(vs) if angle_deg is None
                     else vwutils.PlanFrame(angle_deg).angle)
        if not werte.get("draw_2d") and not werte.get("draw_3d"):
            raise BauFehler(
                u"Es wurde weder eine 2D- noch eine 3D-Darstellung "
                u"ausgewaehlt. Es gibt nichts zu zeichnen.")

        # Datensatzformat zuerst - lieber jetzt scheitern als nach 400 Koerben
        records.ensure_record_format()

        if not rigole_id:
            rigole_id = records.next_rigole_id()
        info["rigole_id"] = rigole_id

        # Klassen anlegen (Oberklasse zuerst) und aktive Klasse behalten
        vorherige_klasse = ""
        try:
            vorherige_klasse = vs.ActiveClass()
        except Exception:
            pass
        for klassenname in CLASSES_ALL:
            vwutils.ensure_class(klassenname)
        if vorherige_klasse:
            vwutils.ensure_class(vorherige_klasse)

        # --- Symbolname klaeren -------------------------------------------
        symbolname, muss_bauen = klaere_symbolname(
            werte.get("system_name"), rigole_id, ergebnis, unit_ctx)
        if symbolname is None:
            raise BauFehler(u"Vom Anwender abgebrochen - es wurde nichts "
                            u"erzeugt.")
        info["symbolname"] = symbolname
        info["symbol_neu"] = muss_bauen

        # --- Symboldefinition ---------------------------------------------
        if muss_bauen:
            info["anzahl_objekte"] = erzeuge_rigolensymbol(
                symbolname, werte, ergebnis, unit_ctx)
            symbol_selbst_erzeugt = True

        # --- Instanz setzen -----------------------------------------------
        vs.Symbol(symbolname, (float(origin_doc[0]), float(origin_doc[1])), angle_deg)
        h_inst = rb.merke_letztes()
        if not vwutils.handle_ok(h_inst):
            raise BauFehler(u"Die Rigole konnte nicht in die Zeichnung "
                            u"eingefuegt werden.")
        info["instance"] = h_inst

        try:
            vs.SetClass(h_inst, CLASS_MAIN)
        except Exception:
            pass

        # --- Hoehenlage ----------------------------------------------------
        z_doc = unit_ctx.to_doc(ergebnis.uk)
        if werte.get("use_layer_elevation"):
            z_doc -= geometry_3d.layer_elevation_doc()
        if z_doc != 0.0:
            try:
                vs.Move3DObj(h_inst, 0.0, 0.0, z_doc)
            except Exception as ex:
                raise BauFehler(
                    u"Die Hoehenlage der Rigole konnte nicht gesetzt "
                    u"werden.\n\nTechnische Meldung: %r" % (ex,))

        benenne(h_inst, GROUP_NAME_TEMPLATE.format(rigole_id=rigole_id))

        # --- Datensatz an die Instanz --------------------------------------
        # Bewusst an die INSTANZ, nicht an die Definition: So traegt jede
        # Rigole ihre eigenen Werte, auch wenn mehrere Instanzen desselben
        # Symbols in der Zeichnung liegen.
        werte_fuer_record = dict(werte)
        werte_fuer_record["basket_symbol_name"] = werte.get("symbol_name", "")
        werte_fuer_record["symbol_name"] = symbolname
        records.write_record(h_inst, werte_fuer_record, ergebnis, rigole_id,
                             records.heute())

        # --- Beschriftung --------------------------------------------------
        if werte.get("create_label"):
            if label_position_doc is None:
                label_position_doc = labeling.default_position_doc(
                    origin_doc, ergebnis, unit_ctx,
                    werte.get("label_offset_x"), werte.get("label_offset_y"), angle_deg)
            text = labeling.build_text(werte, ergebnis, rigole_id)
            info["label"] = labeling.create_label(
                label_position_doc, text, rb,
                name=LABEL_NAME_TEMPLATE.format(rigole_id=rigole_id), angle_deg=angle_deg)

        # --- Auswahl auf die neue Rigole setzen ---------------------------
        try:
            vs.DSelectAll()
            vs.SetSelect(h_inst)
        except Exception:
            pass

        return info

    except records.RecordFehler as ex:
        _zuruecknehmen(rb, symbolname if symbol_selbst_erzeugt else None)
        raise BauFehler(u"%s\n\nEs wurde nichts erzeugt." % (ex,))
    except geometry_3d.GeometrieFehler as ex:
        _zuruecknehmen(rb, symbolname if symbol_selbst_erzeugt else None)
        raise BauFehler(u"%s\n\nEs wurde nichts erzeugt." % (ex,))
    except geometry_schacht.SchachtFehler as ex:
        _zuruecknehmen(rb, symbolname if symbol_selbst_erzeugt else None)
        raise BauFehler(u"%s\n\nEs wurde nichts erzeugt." % (ex,))
    except BauFehler:
        _zuruecknehmen(rb, symbolname if symbol_selbst_erzeugt else None)
        raise
    except Exception as ex:
        _zuruecknehmen(rb, symbolname if symbol_selbst_erzeugt else None)
        raise BauFehler(
            u"Die Rigole konnte nicht erzeugt werden.\n\n"
            u"Technische Meldung: %r\n\nEs wurde nichts erzeugt." % (ex,))


def _zuruecknehmen(rollback, symbolname):
    """
    Nimmt alles zurueck: erst die Zeichnungsobjekte, dann - falls das
    Rigolensymbol in diesem Lauf entstanden ist - die Symboldefinition.
    Die Definition zuletzt, weil ihre Instanzen vorher weg sein muessen.
    """
    rollback.zuruecknehmen()
    if symbolname:
        loesche_symboldefinition(symbolname)
