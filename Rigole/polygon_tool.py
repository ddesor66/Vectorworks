# -*- coding: utf-8 -*-
"""
Werkzeug RIGOLE KOMPLEX - Einstiegspunkt (26.08.2026).

Drittes Werkzeug der Reihe. Die beiden anderen erzeugen einen Quader; dieses
fuellt ein GEZEICHNETES POLYGON mit Rigolenkoerben.

ABLAUF
------
    Polygon anklicken  ->  Dialog  ->  belegen  ->  bauen  ->  fertig

Das Umgrenzungspolygon bleibt liegen und bekommt einen Namen; nur so laesst
sich dieselbe Rigole spaeter wieder bearbeiten (die Eckpunkte stehen
bewusst nicht im Datensatz).

NEU ODER BEARBEITEN
-------------------
Wie bei den anderen Werkzeugen entscheidet der Klickpunkt:

    Klick auf eine vorhandene komplexe Rigole  -> Rueckfrage, dann bearbeiten
    Klick auf ein Polygon / eine Polylinie     -> neu fuellen
    alles andere                               -> Meldung, was gebraucht wird

Der gesamte Durchlauf ist ein einziger Undo-Schritt.

Kompatibilitaet: Python 3.9.2 (Vectorworks 2026)
"""

import vs

from rigole_config.constants import (
    TOOL_VERSION, MODE_GROUP, MODE_BEARBEITEN, PERSISTED_KEYS_POLY,
)
from rigole_core import formatting as fmt
from rigole_core import polygon as poly
from rigole_core.validation import validate_polygon_computed
from rigole_vw import (
    bearbeiten, builder, builder_polygon, dialog_polygon as dlgmod,
    geometry_3d, settings, vwutils, vwpolygon,
)
from rigole_tool import symbolnamen_im_dokument


PROTOKOLL = []
PROTOKOLL_AN = False


def log(text=""):
    if PROTOKOLL_AN:
        PROTOKOLL.append(text)


def protokoll_text():
    return "\n".join(PROTOKOLL)


# ---------------------------------------------------------------------------

def _umgrenzung_holen(h, einheiten):
    """
    (punkte, hinweise) oder (None, None) - dann wurde bereits gemeldet.
    """
    try:
        punkte, hinweise = vwpolygon.lies_umgrenzung(h, einheiten)
    except vwpolygon.UmgrenzungFehler as ex:
        vwutils.alert(str(ex))
        return (None, None)
    return (punkte, hinweise)


def run():
    """Ein kompletter Werkzeuglauf."""
    del PROTOKOLL[:]
    log("=" * 70)
    log("Rigole komplex %s" % (TOOL_VERSION,))
    log("=" * 70)

    try:
        vs.vstNameUndoEvent(u"Rigole komplex")
    except Exception:
        pass
    try:
        vs.NameUndoEvent(u"Rigole komplex")
    except Exception:
        pass

    # --- 1  Klickpunkt -----------------------------------------------------
    punkt = vwutils.get_tool_point()
    log("Klickpunkt (Dokumenteinheiten): %s" % (punkt,))
    if punkt is None:
        vwutils.alert(
            u"Es konnte kein Klickpunkt ermittelt werden.\n\n"
            u"Bitte pruefen Sie im Plug-in-Manager unter „Einstellungen > "
            u"Eigenschaften“, ob „Script ausfuehren“ auf „Nach Mausklick“ "
            u"steht.")
        return False

    # --- 2  Umgebung -------------------------------------------------------
    einheiten = vwutils.get_unit_context()
    log("Einheiten: upi=%s   1,00 m = %s Dokumenteinheiten"
        % (einheiten.upi, round(einheiten.to_doc(1.0), 6)))
    symbole = symbolnamen_im_dokument()
    log("Symbole im Dokument: %d" % (len(symbole),))

    vorgaben = settings.load_settings(dlgmod.default_values(),
                                      settings.SETTINGS_KEY_POLY)

    # --- 3  Was liegt unter dem Klick? -------------------------------------
    modus = vwutils.mode_value(MODE_GROUP)
    getroffen = (bearbeiten.finde_objekt(punkt) if modus == MODE_BEARBEITEN
                 else bearbeiten.finde_am_punkt(punkt))
    art = bearbeiten.art_des_objekts(getroffen)

    alt = None
    kennung = None
    h_umgrenzung = None
    punkte = None

    if art == bearbeiten.ART_POLYGON:
        # --- eine vorhandene komplexe Rigole --------------------------------
        if modus != MODE_BEARBEITEN:
            eigene = bearbeiten.kennung_des_objekts(getroffen, art)
            if not vwutils.frage(bearbeiten.frage_bearbeiten(art, eigene)):
                vwutils.alert(
                    u"Zum Anlegen einer weiteren komplexen Rigole klicken "
                    u"Sie bitte auf das gewuenschte Umgrenzungspolygon, "
                    u"nicht auf eine vorhandene Rigole.")
                return False

        alt = getroffen
        vorgaben, kennung, fehlend = bearbeiten.lies_werte(alt, art, vorgaben)
        if fehlend:
            vwutils.alert(bearbeiten.meldung_fehlende_felder(fehlend))

        name = str(vorgaben.get("umgrenzung_name") or "")
        h_umgrenzung = vwpolygon.hole_nach_name(name)
        if h_umgrenzung is None:
            vwutils.alert(
                u"Zu dieser Rigole gehoert das Umgrenzungspolygon „%s“ - es "
                u"ist im Dokument nicht mehr zu finden.\n\n"
                u"Ohne Umgrenzung laesst sich die Rigole nicht neu "
                u"berechnen. Bitte zeichnen Sie ein neues Polygon und legen "
                u"Sie damit eine neue Rigole an.\n\n"
                u"Es wurde nichts veraendert." % (name or u"ohne Namen",))
            return False

        punkte, hinweise = _umgrenzung_holen(h_umgrenzung, einheiten)
        if punkte is None:
            return False
        log(u"Bearbeite %s, Umgrenzung %r mit %d Ecken"
            % (kennung, name, len(punkte)))

    elif art is not None:
        vwutils.alert(bearbeiten.meldung_falsche_bauart(art))
        return False

    else:
        # --- neu: ein Umgrenzungspolygon --------------------------------
        if not vwpolygon.ist_umgrenzung(getroffen):
            if getroffen is None:
                vwutils.alert(vwpolygon.meldung_nichts_getroffen())
            else:
                vwutils.alert(vwpolygon.meldung_falscher_typ(
                    vwpolygon.objekttyp(getroffen)))
            return False

        h_umgrenzung = getroffen
        punkte, hinweise = _umgrenzung_holen(h_umgrenzung, einheiten)
        if punkte is None:
            return False
        log(u"Umgrenzung mit %d Ecken, %s"
            % (len(punkte), fmt.fmt_area(poly.flaeche(punkte))))
        for zeile in (hinweise or ()):
            log(u"Hinweis: %s" % (zeile,))
            vwutils.alert(zeile)

    # --- 4  Dialog ---------------------------------------------------------
    # A new raster follows the rotated plan, never an arbitrary boundary edge.
    # Existing polygons keep the saved construction angle and source boundary.
    vorgaben = dict(vorgaben)
    vorgaben["raster_winkel"] = (float(vorgaben.get("raster_winkel") or 0.0)
                                 if alt is not None else vwutils.rigole_angle(vs))
    vorgaben["raster_modus"] = dlgmod.RASTER_WINKEL
    vorgaben["_plan_raster_locked"] = True
    werte = dlgmod.show_dialog(vorgaben, symbole, punkte)
    if werte is None:
        log("Dialog abgebrochen - es wurde nichts veraendert.")
        vwutils.status(u"Rigole komplex: abgebrochen.")
        return False
    werte["polygon"] = punkte

    # --- 5  Korbsymbol bereitstellen --------------------------------------
    # Genau wie beim Werkzeug "Rigole": fehlt die Symboldefinition des
    # einzelnen Korbes im Dokument, legt das Werkzeug sie an.
    if werte.get("draw_3d"):
        try:
            war_da, erzeugt = geometry_3d.ensure_basket_symbol(
                werte.get("symbol_name"),
                werte["basket_length"], werte["basket_width"],
                werte["basket_height"], einheiten)
        except geometry_3d.GeometrieFehler as ex:
            vwutils.alert(u"%s\n\nEs wurde nichts erzeugt." % (ex,))
            log(u"Symbolerzeugung FEHLER: %s" % (ex,))
            return False
        werte["symbol_exists"] = True
        log(u"Korbtyp %r -> Symbol %r: %s"
            % (werte.get("basket_key"), werte.get("symbol_name"),
               u"neu erzeugt" if erzeugt else u"war vorhanden"))
        if erzeugt:
            vwutils.status(u"Symbol „%s“ wurde angelegt."
                           % (werte.get("symbol_name"),))

    # --- 6  Belegen und rechnen -------------------------------------------
    try:
        ergebnis = dlgmod.berechne(werte, punkte)
    except poly.PolygonFehler as ex:
        vwutils.alert(u"%s\n\nEs wurde nichts erzeugt." % (ex,))
        return False
    except Exception as ex:
        vwutils.alert(u"Die Rigole konnte nicht berechnet werden.\n\n"
                      u"Technische Meldung: %r" % (ex,))
        return False

    pruefung = validate_polygon_computed(ergebnis)
    if not pruefung.ok:
        vwutils.alert(pruefung.message_text())
        return False

    log("Rasterwinkel    : %.3f Grad" % (ergebnis.raster_winkel,))
    log("Koerbe          : %d  (%d je Lage x %d Lagen)"
        % (ergebnis.basket_count, ergebnis.koerbe_je_lage,
           ergebnis.count_height))
    log("Flaeche         : %s Polygon, %s belegt (%s)"
        % (fmt.fmt_area(ergebnis.polygon_flaeche),
           fmt.fmt_area(ergebnis.belegte_flaeche),
           fmt.fmt_percent(ergebnis.ausnutzung)))
    log("Huellmass       : " + fmt.fmt_triple(ergebnis.total_length,
                                              ergebnis.total_width,
                                              ergebnis.total_height))
    log("Speichervolumen : " + fmt.fmt_volume(ergebnis.v_speicher))
    if ergebnis.hat_schacht:
        log("Schaechte       : %d x %s, OK %s"
            % (ergebnis.schacht_anzahl, ergebnis.schacht_dn,
               fmt.fmt_height(ergebnis.schacht_ok)))
    log("OK / UK         : %s / %s" % (fmt.fmt_height(ergebnis.ok),
                                       fmt.fmt_height(ergebnis.uk)))

    # --- 7  Einstellungen merken ------------------------------------------
    settings.save_settings(werte, settings.SETTINGS_KEY_POLY,
                           PERSISTED_KEYS_POLY)

    # Der Altbestand wird erst nach einem erfolgreichen Neubau entfernt.

    # --- 9  Bauen ----------------------------------------------------------
    try:
        info = bearbeiten.neu_aufbauen(
            alt, bearbeiten.ART_POLYGON, kennung,
            lambda: builder_polygon.build_rigole_polygon(
                werte, ergebnis, einheiten, rigole_id=kennung,
                h_umgrenzung=h_umgrenzung))
    except builder.BauFehler as ex:
        vwutils.alert(str(ex))
        log("FEHLER: %s" % (ex,))
        return False

    log(u"Rigole %s erzeugt. Symbol %r %s, %d Einzelobjekte. Umgrenzung %r."
        % (info["rigole_id"], info["symbolname"],
           u"neu angelegt" if info["symbol_neu"] else u"wiederverwendet",
           info["anzahl_objekte"], info["umgrenzung_name"]))

    if not info["umgrenzung_name"]:
        vwutils.alert(
            u"Die Umgrenzung konnte nicht benannt werden. Die Rigole ist "
            u"erzeugt, laesst sich spaeter aber nicht ueber das Werkzeug "
            u"bearbeiten - dafuer wird das Polygon ueber seinen Namen "
            u"wiedergefunden.")

    vwutils.status(
        u"Rigole komplex %s „%s“%s: %d Koerbe, %s, Ausnutzung %s"
        % (info["rigole_id"], info["symbolname"],
           u" (bearbeitet)" if alt is not None else u"",
           ergebnis.basket_count, fmt.fmt_volume(ergebnis.v_speicher),
           fmt.fmt_percent(ergebnis.ausnutzung)))

    return True
