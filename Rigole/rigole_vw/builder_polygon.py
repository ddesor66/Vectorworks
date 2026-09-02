# -*- coding: utf-8 -*-
"""
PHASE 17 - Zusammenbau der Rigole nach Polygon ("Rigole komplex").

Aufbau wie bei den anderen beiden Bauarten: ein transaktionsaehnlicher
Vorgang, der bei einem Fehler alles Erzeugte wieder entfernt.

Ergebnis in der Zeichnung
-------------------------
    Symbolinstanz „Rigole komplex RIGK-001"   Klasse PD-EW-RW-Rigole
        (eingefuegt MIT dem Rasterwinkel)
        Symboldefinition = Bezeichnung        <- traegt DB_Rigole_komplex
        │
        ├── Umgrenzung + Korbplaetze          Klasse PD-EW-RW-Rigole-2D
        ├── n x Korbsymbol                    Klasse PD-EW-RW-Rigole-3D
        └── Kontrollschaechte                 Klasse PD-EW-RW-Rigole-Schacht

    Textobjekt Beschriftung                   Klasse ...-Beschriftung
    das gezeichnete Umgrenzungspolygon        bleibt unveraendert liegen

WARUM DIE DREHUNG UEBER DIE INSTANZ LAEUFT
------------------------------------------
Die Symboldefinition wird achsparallel im Rastersystem aufgebaut. Erst beim
Einfuegen bekommt sie den Rasterwinkel mit: vs.Symbol(name, punkt, winkel)
nimmt den Winkel entgegen. Damit muss keine einzige Koordinate von Hand
zurueckgedreht werden - und die Definition bleibt lesbar.

Kompatibilitaet: Python 3.9.2 (Vectorworks 2026)
"""

import vs

from rigole_config.constants import (
    CLASS_MAIN, CLASS_SCHACHT, CLASSES_ALL,
    GROUP_NAME_TEMPLATE_POLY, LABEL_NAME_TEMPLATE_POLY,
    UMGRENZUNG_NAME_TEMPLATE, SYMBOL_TOLERANZ,
)
from rigole_vw import (vwutils, records, geometry_3d, geometry_polygon,
                       geometry_schacht, labeling, vwpolygon)
from rigole_vw.builder import (BauFehler, loesche_symboldefinition, benenne,
                               _freier_symbolname, _zahl)


def rigole_symbolname(bezeichnung, rigole_id):
    name = str(bezeichnung or "").strip()
    if not name:
        name = u"Rigole komplex %s" % (rigole_id,)
    return name


# ---------------------------------------------------------------------------
# Symbolname klaeren
# ---------------------------------------------------------------------------

def _passt_vorhandenes_symbol(symbolname, ergebnis):
    """
    Passt eine bereits vorhandene Symboldefinition zu dieser Rigole?

    Bei der Polygonrigole reicht ein Vergleich der Aussenmasse NICHT: Zwei
    voellig verschiedene Umrisse koennen dieselbe Huellbox haben. Verglichen
    wird deshalb ueber den Datensatz - dieselbe Falle wie beim Draenrohr der
    Kiesrigole (24.08.2026), nur noch eine Nummer groesser.

    Rueckgabe: (passt, klartext_begruendung)
    """
    eintraege = records.poly_daten_zu_symbol(symbolname)
    if not eintraege:
        return (False, u"Zu diesem Symbol liegt keine komplexe Rigole mit "
                       u"Datensatz im Dokument. Das Werkzeug kann deshalb "
                       u"nicht feststellen, welche Korbverteilung darin "
                       u"steckt.")

    for eintrag in eintraege:
        for schluessel, neu, name in (
                ("je_lage", ergebnis.koerbe_je_lage, u"Koerbe je Lage"),
                ("lagen", ergebnis.count_height, u"Lagen"),
                ("ecken", ergebnis.eckenzahl, u"Eckpunkte")):
            alt = _zahl(eintrag.get(schluessel), None)
            if alt is None or int(alt) != int(neu):
                return (False, u"%s - vorhanden: %s, neu: %d"
                               % (name,
                                  u"unbekannt" if alt is None else int(alt),
                                  int(neu)))

        for schluessel, neu, name in (
                ("korb_l", ergebnis.basket_length, u"Korblaenge"),
                ("korb_b", ergebnis.basket_width, u"Korbbreite"),
                ("korb_h", ergebnis.basket_height, u"Korbhoehe"),
                ("winkel", ergebnis.raster_winkel, u"Rasterwinkel")):
            alt = _zahl(eintrag.get(schluessel), None)
            if alt is None or abs(float(alt) - float(neu)) > SYMBOL_TOLERANZ:
                return (False, u"%s - vorhanden: %s, neu: %.3f"
                               % (name,
                                  u"unbekannt" if alt is None
                                  else ("%.3f" % alt),
                                  float(neu)))

        alt_dn = str(eintrag.get("schacht_dn") or "")
        if alt_dn != str(ergebnis.schacht_dn or ""):
            return (False, u"Schacht - vorhanden: %s, neu: %s"
                           % (alt_dn or u"ohne",
                              ergebnis.schacht_dn or u"ohne"))

    return (True, u"")


def klaere_symbolname(bezeichnung, rigole_id, ergebnis):
    """
    Rueckgabe: (name, muss_erzeugt_werden); (None, False) = abgebrochen.
    """
    name = rigole_symbolname(bezeichnung, rigole_id)
    h = vs.GetObject(name)

    if not vwutils.handle_ok(h):
        return (name, True)

    if vs.GetTypeN(h) != vwutils.TYP_SYMBOLDEFINITION:
        ersatz = _freier_symbolname(name, rigole_id)
        if ersatz is None:
            raise BauFehler(
                u"Der Name „%s“ ist bereits vergeben und es liess sich kein "
                u"freier Ersatzname bilden. Bitte eine andere Bezeichnung "
                u"eingeben." % (name,))
        return (ersatz, True)

    passt, grund = _passt_vorhandenes_symbol(name, ergebnis)
    if passt:
        return (name, False)

    ersatz = _freier_symbolname(name, rigole_id)
    if ersatz is None:
        raise BauFehler(
            u"Der Name „%s“ ist vergeben und es liess sich kein freier "
            u"Ersatzname bilden." % (name,))

    weiter = vwutils.frage(
        u"Im Dokument gibt es bereits ein Symbol „%s“ - allerdings mit einer "
        u"anderen Korbverteilung.\n\n"
        u"%s\n\n"
        u"Soll die neue Rigole als eigenes Symbol „%s“ angelegt werden?\n\n"
        u"Ja   = neues Symbol anlegen\n"
        u"Nein = abbrechen, es wird nichts erzeugt"
        % (name, grund, ersatz))
    if not weiter:
        return (None, False)
    return (ersatz, True)


# ---------------------------------------------------------------------------
# Symboldefinition aufbauen
# ---------------------------------------------------------------------------

def erzeuge_rigolensymbol(symbolname, werte, ergebnis, unit_ctx):
    """
    Baut die Symboldefinition. Unterkante auf z = 0, Nullpunkt in der linken
    unteren Ecke der belegten Huellbox, x-Achse in Rasterrichtung.

    Rueckgabe: Anzahl der erzeugten Einzelobjekte.
    """
    rb_intern = vwutils.Rollback()
    anzahl = 0

    try:
        vs.BeginSym(symbolname)
        try:
            if werte.get("draw_3d"):
                anzahl += len(geometry_polygon.place_baskets(
                    ergebnis, unit_ctx, rb_intern,
                    werte.get("symbol_name"),
                    anchor=werte.get("symbol_anchor", "corner")))

            if werte.get("draw_2d"):
                anzahl += len(geometry_polygon.draw_plan(
                    ergebnis, unit_ctx, rb_intern,
                    mit_zellen=bool(werte.get("zeige_zellen", True))))

            if ergebnis.hat_schacht:
                mittelpunkte = [
                    (unit_ctx.to_doc(float(x)), unit_ctx.to_doc(float(y)))
                    for (x, y) in (ergebnis.schacht_positionen or ())]
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


# ---------------------------------------------------------------------------
# Hauptfunktion
# ---------------------------------------------------------------------------

def build_rigole_polygon(werte, ergebnis, unit_ctx, rigole_id=None,
                         h_umgrenzung=None):
    """
    Baut die komplette Rigole nach Polygon.

    werte           Wertedictionary aus dem Dialog
    ergebnis        PolygonResult aus calculations.compute_rigole_polygon
    unit_ctx        UnitContext
    rigole_id       vorgegebene ID oder None
    h_umgrenzung    Handle des gezeichneten Polygons (fuer den Namen)

    Rueckgabe: dict mit rigole_id, symbolname, instance, label,
               anzahl_objekte, symbol_neu, umgrenzung_name

    Loest BauFehler aus. In diesem Fall wurde alles Erzeugte entfernt.
    """
    rb = vwutils.Rollback()
    info = {
        "rigole_id": None, "symbolname": None, "instance": None,
        "label": None, "anzahl_objekte": 0, "symbol_neu": False,
        "umgrenzung_name": "",
    }
    symbolname = None
    symbol_selbst_erzeugt = False

    try:
        if not werte.get("draw_2d") and not werte.get("draw_3d"):
            raise BauFehler(
                u"Es wurde weder eine 2D- noch eine 3D-Darstellung "
                u"ausgewaehlt. Es gibt nichts zu zeichnen.")
        if not ergebnis.zellen:
            raise BauFehler(
                u"In die Umgrenzung passt kein einziger vollstaendiger "
                u"Korb. Es wurde nichts erzeugt.")

        records.ensure_poly_record_format()

        if not rigole_id:
            rigole_id = records.next_poly_id()
        info["rigole_id"] = rigole_id

        vorherige_klasse = ""
        try:
            vorherige_klasse = vs.ActiveClass()
        except Exception:
            pass
        for klassenname in CLASSES_ALL:
            vwutils.ensure_class(klassenname)
        if vorherige_klasse:
            vwutils.ensure_class(vorherige_klasse)

        # --- Umgrenzung benennen ------------------------------------------
        # Damit sie beim Bearbeiten wiedergefunden wird. Ein bereits vom
        # Anwender vergebener Name bleibt stehen.
        if h_umgrenzung is not None and vwutils.handle_ok(h_umgrenzung):
            info["umgrenzung_name"] = vwpolygon.name_sichern(
                h_umgrenzung,
                UMGRENZUNG_NAME_TEMPLATE.format(rigole_id=rigole_id))

        # --- Symbolname ----------------------------------------------------
        symbolname, muss_bauen = klaere_symbolname(
            werte.get("system_name"), rigole_id, ergebnis)
        if symbolname is None:
            raise BauFehler(u"Vom Anwender abgebrochen - es wurde nichts "
                            u"erzeugt.")
        info["symbolname"] = symbolname
        info["symbol_neu"] = muss_bauen

        if muss_bauen:
            info["anzahl_objekte"] = erzeuge_rigolensymbol(
                symbolname, werte, ergebnis, unit_ctx)
            symbol_selbst_erzeugt = True

        # --- Instanz setzen, MIT Rasterwinkel ------------------------------
        punkt = ergebnis.einfuegepunkt
        x_doc = unit_ctx.to_doc(float(punkt[0]))
        y_doc = unit_ctx.to_doc(float(punkt[1]))
        vs.Symbol(symbolname, (x_doc, y_doc), float(ergebnis.raster_winkel))
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

        benenne(h_inst, GROUP_NAME_TEMPLATE_POLY.format(rigole_id=rigole_id))

        # --- Datensatz -----------------------------------------------------
        werte_fuer_record = dict(werte)
        werte_fuer_record["basket_symbol_name"] = werte.get("symbol_name", "")
        werte_fuer_record["symbol_name"] = symbolname
        records.write_poly_record(h_inst, werte_fuer_record, ergebnis,
                                  rigole_id, records.heute(),
                                  umgrenzung_name=info["umgrenzung_name"])

        # --- Beschriftung --------------------------------------------------
        if werte.get("create_label"):
            position = labeling.polygon_label_position_doc(
                (x_doc, y_doc), ergebnis, unit_ctx,
                werte.get("label_offset_x"), werte.get("label_offset_y"))
            text = labeling.build_polygon_text(werte, ergebnis, rigole_id)
            info["label"] = labeling.create_label(
                position, text, rb,
                name=LABEL_NAME_TEMPLATE_POLY.format(rigole_id=rigole_id),
                angle_deg=ergebnis.raster_winkel)

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
    rollback.zuruecknehmen()
    if symbolname:
        loesche_symboldefinition(symbolname)
