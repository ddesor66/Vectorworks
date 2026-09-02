# -*- coding: utf-8 -*-
"""
Zusammenbau der KIESRIGOLE.

Bewusst eine eigene Datei: der Ablauf der Koerbe-Rigole in builder.py ist
abgenommen und soll unveraendert bleiben (Vorgabe des Anwenders vom
24.08.2026: „Daran in Zukunft nichts aendern."). Gemeinsam genutzt werden nur
die Hilfsfunktionen, die dort ohnehin allgemein gehalten sind
(_freier_symbolname, loesche_symboldefinition, benenne).

Ergebnis in der Zeichnung
-------------------------
    Symbolinstanz „Kiesrigole KIES-001"     Klasse PD-EW-Kiesrigole
        Symboldefinition = Bezeichnung, z. B. „Kiesrigole Nord"
        │                                    <- die INSTANZ traegt DB_Kiesrigole
        ├── Schuettkoerper (Extrusion)       Klasse PD-EW-Kiesrigole-Füllung
        ├── Umgrenzung im Plan (Rechteck)    Klasse PD-EW-Kiesrigole-Füllung
        ├── Draenrohr (liegende Zylinder)    Klasse PD-EW-Kiesrigole-Drainrohr
        ├── Rohrkontur im Plan (Linienpaare) Klasse PD-EW-Kiesrigole-Drainrohr
        ├── Kontrollschaechte (Zylinder)     Klasse PD-EW-Kiesrigole-Schacht
        └── Schachtkreise im Plan            Klasse PD-EW-Kiesrigole-Schacht

    Textobjekt Beschriftung                  Klasse PD-EW-Kiesrigole-Beschriftung
                                             (ausserhalb, frei verschiebbar)

Hoehenlage
----------
Wie bei der Koerbe-Rigole liegt die Sohle innerhalb der Symboldefinition auf
z = 0; die fertige Instanz wird anschliessend als Ganzes auf die Planungshoehe
gehoben. Dieselbe Definition ist damit auf jeder Hoehe verwendbar.

Kompatibilitaet: Python 3.9.2 (Vectorworks 2026)
"""

import vs

from rigole_config.constants import (
    CLASS_KIES, CLASSES_KIES, CLASS_KIES_LABEL,
    GROUP_NAME_TEMPLATE_KIES, LABEL_NAME_TEMPLATE_KIES,
    SYMBOL_TOLERANZ,
)
from rigole_vw import (vwutils, records, geometry_3d, geometry_kies,
                       labeling, builder)
from rigole_vw.builder import BauFehler, loesche_symboldefinition, benenne


# ---------------------------------------------------------------------------
# Symbolname
# ---------------------------------------------------------------------------

def kies_symbolname(bezeichnung, kies_id):
    """Der Symbolname ist die eingegebene Bezeichnung, ersatzweise die ID."""
    name = str(bezeichnung or "").strip()
    if not name:
        name = u"Kiesrigole %s" % (kies_id,)
    return name


def _zahl(text, standard=None):
    try:
        return float(str(text).replace(",", "."))
    except (TypeError, ValueError):
        return standard


def _rohr_passt_zum_symbol(symbolname, ergebnis):
    """
    Prueft, ob die vorhandene Symboldefinition denselben Innenausbau hat wie
    die neu einzufuegende Kiesrigole - Draenrohr UND Kontrollschaechte.

    Die Aussenmasse allein reichen dafuer NICHT: Laenge, Breite und Hoehe
    koennen gleich sein, waehrend im Symbol ein DN 160 statt eines DN 300
    steckt. Da eine Symboldefinition ihre Bauteile nicht als Merkmale
    ausweist, wird ueber den Datensatz der bereits vorhandenen Instanzen
    verglichen - dort steht im Feld "Symbolname", zu welcher Definition sie
    gehoeren.

    Die Schachtoberkante wird RELATIV zur Unterkante der Rigole verglichen:
    innerhalb der Symboldefinition zaehlt nur diese Differenz, damit dasselbe
    Symbol auf jeder Hoehenlage verwendbar bleibt.

    Rueckgabe: (passt, klartext_begruendung)
    """
    eintraege = records.kies_daten_zu_symbol(symbolname)
    if not eintraege:
        return (False, u"Zu diesem Symbol liegt keine Kiesrigole mit "
                       u"Datensatz im Dokument. Das Werkzeug kann deshalb "
                       u"nicht feststellen, welches Draenrohr darin steckt.")

    neu_dn = str(ergebnis.rohr_dn or "")
    neu_uk = float(ergebnis.rohr_uk or 0.0)

    for eintrag in eintraege:
        alt_dn = str(eintrag.get("rohr_dn") or "")
        if alt_dn != neu_dn:
            return (False, u"vorhandenes Symbol: %s\nneue Kiesrigole   : %s"
                           % (alt_dn or u"unbekannt", neu_dn or u"ohne Rohr"))
        alt_uk = _zahl(eintrag.get("rohr_uk"))
        if alt_uk is None:
            return (False, u"Der Abstand der Rohrunterkante zur Sohle ist im "
                           u"vorhandenen Symbol nicht vermerkt (aelterer "
                           u"Datensatz).")
        if abs(alt_uk - neu_uk) > SYMBOL_TOLERANZ:
            return (False, u"UK Rohr ueber Sohle - vorhanden: %.3f m, "
                           u"neu: %.3f m" % (alt_uk, neu_uk))

        # --- Kontrollschaechte -------------------------------------------
        alt_schacht_dn = str(eintrag.get("schacht_dn") or "")
        neu_schacht_dn = str(ergebnis.schacht_dn or "")
        if alt_schacht_dn != neu_schacht_dn:
            return (False, u"Schacht - vorhanden: %s, neu: %s"
                           % (alt_schacht_dn or u"ohne",
                              neu_schacht_dn or u"ohne"))

        alt_anzahl = _zahl(eintrag.get("schacht_anz"), 0.0)
        if int(alt_anzahl or 0) != int(ergebnis.schacht_anzahl):
            return (False, u"Anzahl Schaechte - vorhanden: %d, neu: %d"
                           % (int(alt_anzahl or 0), ergebnis.schacht_anzahl))

        if ergebnis.hat_schacht:
            alt_ok = _zahl(eintrag.get("schacht_ok"))
            alt_uk_rigole = _zahl(eintrag.get("uk_rigole"))
            if alt_ok is None or alt_uk_rigole is None:
                return (False, u"Die Schachthoehe ist im vorhandenen Symbol "
                               u"nicht vermerkt (aelterer Datensatz).")
            alt_rel = alt_ok - alt_uk_rigole
            neu_rel = float(ergebnis.schacht_ok) - float(ergebnis.uk)
            if abs(alt_rel - neu_rel) > SYMBOL_TOLERANZ:
                return (False, u"Schachthoehe ueber UK Rigole - vorhanden: "
                               u"%.3f m, neu: %.3f m" % (alt_rel, neu_rel))

    return (True, u"")


def klaere_symbolname(bezeichnung, kies_id, ergebnis, unit_ctx):
    """
    Bestimmt den Symbolnamen und ob neu gebaut werden muss.
    Rueckgabe: (name, muss_erzeugt_werden); (None, False) = abgebrochen.

    Gleiche Logik wie bei der Koerbe-Rigole: Ein vorhandenes Symbol wird nur
    dann wiederverwendet, wenn seine gemessenen Abmessungen zu den neuen
    Werten passen. Sonst wird nachgefragt und ein Ersatzname angeboten.
    """
    name = kies_symbolname(bezeichnung, kies_id)
    h = vs.GetObject(name)

    if not vwutils.handle_ok(h):
        return (name, True)

    if vs.GetTypeN(h) != vwutils.TYP_SYMBOLDEFINITION:
        ersatz = builder._freier_symbolname(name, kies_id)
        if ersatz is None:
            raise BauFehler(
                u"Der Name „%s“ ist bereits vergeben und es liess sich kein "
                u"freier Ersatzname bilden. Bitte eine andere Bezeichnung "
                u"eingeben." % (name,))
        return (ersatz, True)

    gemessen = geometry_kies.measure_symbol(name, unit_ctx)
    masse_passen = (gemessen is not None and geometry_3d.dimensions_match(
        gemessen, ergebnis.total_length, ergebnis.total_width,
        ergebnis.total_height, SYMBOL_TOLERANZ))

    if masse_passen:
        rohr_passt, grund = _rohr_passt_zum_symbol(name, ergebnis)
        if rohr_passt:
            return (name, False)                # wiederverwenden
        # Die Aussenmasse stimmen, das Draenrohr aber nicht. Genau hier lag
        # der Fehler vom 24.08.2026: Das vorhandene Symbol wurde stillschwei-
        # gend wiederverwendet, und die neue Rigole bekam das ALTE Rohr.
        ersatz = builder._freier_symbolname(name, kies_id)
        if ersatz is None:
            raise BauFehler(
                u"Der Name „%s“ ist vergeben und es liess sich kein freier "
                u"Ersatzname bilden." % (name,))
        weiter = vwutils.frage(
            u"Im Dokument gibt es bereits ein Symbol „%s“ mit denselben "
            u"Aussenmassen, aber anderem Innenausbau.\n\n"
            u"%s\n\n"
            u"Ein Symbol kann nur EINEN Innenausbau enthalten. Soll die neue "
            u"Kiesrigole als eigenes Symbol „%s“ angelegt werden?\n\n"
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
    ersatz = builder._freier_symbolname(name, kies_id)
    if ersatz is None:
        raise BauFehler(
            u"Der Name „%s“ ist vergeben und es liess sich kein freier "
            u"Ersatzname bilden." % (name,))

    weiter = vwutils.frage(
        u"Im Dokument gibt es bereits ein Symbol „%s“ - allerdings mit "
        u"anderen Abmessungen.\n\n"
        u"vorhandenes Symbol : %s m\n"
        u"neue Kiesrigole    : %s m\n\n"
        u"Soll die neue Kiesrigole als eigenes Symbol „%s“ angelegt werden?\n\n"
        u"Ja   = neues Symbol anlegen\n"
        u"Nein = abbrechen, es wird nichts erzeugt"
        % (name, gem, neu, ersatz))
    if not weiter:
        return (None, False)
    return (ersatz, True)


# ---------------------------------------------------------------------------
# Symboldefinition aufbauen
# ---------------------------------------------------------------------------

def erzeuge_kiessymbol(symbolname, werte, ergebnis, unit_ctx):
    """
    Baut die Symboldefinition der Kiesrigole. Sohle auf z = 0,
    Einfuegepunkt vorne links.

    Rueckgabe: Anzahl der erzeugten Einzelobjekte.
    """
    anzahl = 0
    ursprung = (0.0, 0.0)

    try:
        vs.BeginSym(symbolname)
        try:
            if werte.get("draw_3d"):
                h = geometry_kies.build_fuellkoerper(ergebnis, unit_ctx,
                                                     ursprung)
                if vwutils.handle_ok(h):
                    anzahl += 1
                anzahl += len(geometry_kies.build_draenrohr(
                    ergebnis, unit_ctx, ursprung))
                anzahl += len(geometry_kies.build_schaechte(
                    ergebnis, unit_ctx, ursprung))

            if werte.get("draw_2d"):
                handles = geometry_kies.draw_plan(ergebnis, unit_ctx, ursprung)
                anzahl += len(handles)
        finally:
            vs.EndSym()
    except geometry_kies.KiesGeometrieFehler as ex:
        loesche_symboldefinition(symbolname)
        raise BauFehler(u"%s" % (ex,))
    except Exception as ex:
        loesche_symboldefinition(symbolname)
        raise BauFehler(
            u"Die Symboldefinition „%s“ konnte nicht aufgebaut werden.\n\n"
            u"Technische Meldung: %r" % (symbolname, ex))

    if not vwutils.symbol_exists(symbolname):
        raise BauFehler(
            u"Die Symboldefinition „%s“ wurde nicht angelegt." % (symbolname,))

    return anzahl


# ---------------------------------------------------------------------------
# Hauptfunktion
# ---------------------------------------------------------------------------

def build_kiesrigole(origin_doc, werte, ergebnis, unit_ctx,
                     kies_id=None, label_position_doc=None, angle_deg=None):
    """
    Baut die komplette Kiesrigole.

    origin_doc          (x, y) Einfuegepunkt in DOKUMENTEINHEITEN
    werte               Wertedictionary aus dem Dialog
    ergebnis            KiesResult aus calculations.compute_kiesrigole
    unit_ctx            UnitContext
    kies_id             vorgegebene ID oder None
    label_position_doc  (x, y) fuer die Beschriftung oder None

    Rueckgabe: dict mit
        rigole_id, symbolname, instance, label, anzahl_objekte, symbol_neu

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

        # Datensatzformat zuerst - lieber jetzt scheitern als nach dem Bau
        records.ensure_kies_record_format()

        if not kies_id:
            kies_id = records.next_kies_id()
        info["rigole_id"] = kies_id

        # Klassen anlegen (Oberklasse zuerst), aktive Klasse anschliessend
        # wiederherstellen
        vorherige_klasse = ""
        try:
            vorherige_klasse = vs.ActiveClass()
        except Exception:
            pass
        for klassenname in CLASSES_KIES:
            vwutils.ensure_class(klassenname)
        if vorherige_klasse:
            vwutils.ensure_class(vorherige_klasse)

        # --- Symbolname klaeren -------------------------------------------
        symbolname, muss_bauen = klaere_symbolname(
            werte.get("system_name"), kies_id, ergebnis, unit_ctx)
        if symbolname is None:
            raise BauFehler(u"Vom Anwender abgebrochen - es wurde nichts "
                            u"erzeugt.")
        info["symbolname"] = symbolname
        info["symbol_neu"] = muss_bauen

        # --- Symboldefinition ---------------------------------------------
        if muss_bauen:
            info["anzahl_objekte"] = erzeuge_kiessymbol(
                symbolname, werte, ergebnis, unit_ctx)
            symbol_selbst_erzeugt = True

        # --- Instanz setzen -----------------------------------------------
        vs.Symbol(symbolname, (float(origin_doc[0]), float(origin_doc[1])), angle_deg)
        h_inst = rb.merke_letztes()
        if not vwutils.handle_ok(h_inst):
            raise BauFehler(u"Die Kiesrigole konnte nicht in die Zeichnung "
                            u"eingefuegt werden.")
        info["instance"] = h_inst

        try:
            vs.SetClass(h_inst, CLASS_KIES)
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
                    u"Die Hoehenlage der Kiesrigole konnte nicht gesetzt "
                    u"werden.\n\nTechnische Meldung: %r" % (ex,))

        benenne(h_inst, GROUP_NAME_TEMPLATE_KIES.format(rigole_id=kies_id))

        # --- Datensatz an die INSTANZ --------------------------------------
        werte_fuer_record = dict(werte)
        werte_fuer_record["symbol_name"] = symbolname
        records.write_kies_record(h_inst, werte_fuer_record, ergebnis,
                                  kies_id, records.heute())

        # --- Beschriftung --------------------------------------------------
        if werte.get("create_label"):
            if label_position_doc is None:
                label_position_doc = labeling.default_position_doc(
                    origin_doc, ergebnis, unit_ctx,
                    werte.get("label_offset_x"), werte.get("label_offset_y"), angle_deg)
            text = labeling.build_kies_text(werte, ergebnis, kies_id)
            info["label"] = labeling.create_label(
                label_position_doc, text, rb, klasse=CLASS_KIES_LABEL,
                name=LABEL_NAME_TEMPLATE_KIES.format(rigole_id=kies_id), angle_deg=angle_deg)

        # --- Auswahl auf die neue Kiesrigole setzen -----------------------
        try:
            vs.DSelectAll()
            vs.SetSelect(h_inst)
        except Exception:
            pass

        return info

    except records.RecordFehler as ex:
        _zuruecknehmen(rb, symbolname if symbol_selbst_erzeugt else None)
        raise BauFehler(u"%s\n\nEs wurde nichts erzeugt." % (ex,))
    except geometry_kies.KiesGeometrieFehler as ex:
        _zuruecknehmen(rb, symbolname if symbol_selbst_erzeugt else None)
        raise BauFehler(u"%s\n\nEs wurde nichts erzeugt." % (ex,))
    except BauFehler:
        _zuruecknehmen(rb, symbolname if symbol_selbst_erzeugt else None)
        raise
    except Exception as ex:
        _zuruecknehmen(rb, symbolname if symbol_selbst_erzeugt else None)
        raise BauFehler(
            u"Die Kiesrigole konnte nicht erzeugt werden.\n\n"
            u"Technische Meldung: %r\n\nEs wurde nichts erzeugt." % (ex,))


def _zuruecknehmen(rollback, symbolname):
    """Erst die Zeichnungsobjekte, dann die Symboldefinition."""
    rollback.zuruecknehmen()
    if symbolname:
        loesche_symboldefinition(symbolname)
