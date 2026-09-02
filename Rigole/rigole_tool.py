# -*- coding: utf-8 -*-
"""
Werkzeug RIGOLE (Rigolenkoerper) - Einstiegspunkt.

Seit dem 24.08.2026 gibt es zwei Werkzeuge; die Kiesrigole steckt in
kies_tool.py. Beide teilen sich denselben Modulordner.

Dieses Modul wird vom Werkzeugskript in der .vst-Datei aufgerufen. Es laeuft
bei JEDEM Mausklick einmal komplett durch:

    Klickpunkt holen  ->  Dialog  ->  rechnen  ->  bauen  ->  fertig

NEU ODER BEARBEITEN
-------------------
Das Werkzeug erkennt das selbst am Klickpunkt: liegt dort schon eine Rigole
dieses Werkzeugs, fragt es nach, ob sie bearbeitet werden soll. Klick ins
Leere heisst neu anlegen. Warum es dafuer keine Modusleiste gibt, steht in
rigole_vw/bearbeiten.py.

Der gesamte Durchlauf ist ein einziger Undo-Schritt (bestaetigt in
Pruefbericht C2, Punkt D2).

Kompatibilitaet: Python 3.9.2 (Vectorworks 2026)
"""

import vs

from rigole_config.constants import (
    TOOL_NAME, TOOL_VERSION, SYMBOL_TOLERANZ,
    MODE_GROUP,
)
from rigole_core import formatting as fmt
from rigole_core.validation import validate_computed
from rigole_vw import (
    bearbeiten, builder, dialog as dlgmod, geometry_3d, settings,
    vwutils,
)


PROTOKOLL = []
PROTOKOLL_AN = False        # von aussen setzbar, siehe Werkzeugskript


def log(text=""):
    if PROTOKOLL_AN:
        PROTOKOLL.append(text)


def protokoll_text():
    return "\n".join(PROTOKOLL)


# ---------------------------------------------------------------------------

def symbolnamen_im_dokument():
    """
    Alle Symboldefinitionen des aktuellen Dokuments.

    Der Ressourcenlisten-Index ist 1-basiert - so steht es im Beispiel
    'WorkingWithResrouceList' der Skriptreferenz, und Pruefbericht C2 hat es
    bestaetigt (Eintrag 1 = erstes Symbol).
    """
    namen = []
    try:
        listID, anzahl = vs.BuildResourceList(
            vwutils.TYP_SYMBOLDEFINITION, 0, "")
        for i in range(1, int(anzahl) + 1):
            try:
                name = vs.GetActualNameFromResourceList(listID, i)
                if name:
                    namen.append(name)
            except Exception:
                pass
    except Exception:
        pass
    return namen


def pruefe_symbolmasse(werte, ergebnis, einheiten):
    """
    Vergleicht die tatsaechlichen Abmessungen der gewaehlten Symboldefinition
    mit den eingegebenen Korbmassen.

    Hintergrund: Das Werkzeug setzt die Koerbe im Raster der EINGEGEBENEN
    Masse. Ist das Symbol in Wirklichkeit kleiner, entstehen sichtbare Luecken
    zwischen den Lagen; ist es groesser, durchdringen sich die Koerbe. Beides
    faellt in der Draufsicht kaum auf, in der Vorderansicht sofort.

    Rueckgabe: True = weiterbauen, False = abbrechen.
    """
    gemessen = geometry_3d.measure_symbol(werte.get("symbol_name"), einheiten)
    if gemessen is None:
        log("Symbolmaße nicht messbar - Erstellung blockiert.")
        vwutils.alert(
            "Die Symbolabmessungen konnten nicht geprüft werden. "
            "Bitte eine gültige 3D-Symboldefinition wählen. Es wurde nichts gebaut.")
        return False

    log(u"Symbolmasse gemessen (Get3DInfo): %s"
        % (tuple(round(w, 4) for w in gemessen),))

    if geometry_3d.dimensions_match(gemessen,
                                    ergebnis.basket_length,
                                    ergebnis.basket_width,
                                    ergebnis.basket_height,
                                    SYMBOL_TOLERANZ):
        return True

    gem = sorted(round(float(w), 3) for w in gemessen)
    ein = sorted(round(float(w), 3) for w in (ergebnis.basket_length,
                                              ergebnis.basket_width,
                                              ergebnis.basket_height))
    log(u"ABWEICHUNG: Symbol %s  <->  Eingabe %s" % (gem, ein))

    return vwutils.frage(
        u"Das Symbol „%s“ hat andere Abmessungen als eingegeben.\n\n"
        u"gemessen am Symbol : %s m\n"
        u"im Dialog eingegeben: %s m\n\n"
        u"Das Werkzeug setzt die Koerbe im Raster der eingegebenen Masse. "
        u"Weichen die Symbolmasse davon ab, entstehen Luecken zwischen den "
        u"Lagen oder die Koerbe durchdringen sich.\n\n"
        u"Empfehlung: Abbrechen und entweder die Korbmasse an das Symbol "
        u"anpassen oder ein passendes Symbol waehlen.\n\n"
        u"Trotzdem fortfahren?"
        % (werte.get("symbol_name"),
           u" x ".join(("%.3f" % w).replace(".", ",") for w in gem),
           u" x ".join(("%.3f" % w).replace(".", ",") for w in ein)))


# ---------------------------------------------------------------------------

def run():
    """Ein kompletter Werkzeuglauf."""
    del PROTOKOLL[:]
    log("=" * 70)
    log("%s %s" % (TOOL_NAME, TOOL_VERSION))
    log("=" * 70)

    try:
        vs.vstNameUndoEvent(u"Rigole")
    except Exception:
        pass
    try:
        vs.NameUndoEvent(u"Rigole")
    except Exception:
        pass

    # --- 1  Einfuegepunkt --------------------------------------------------
    punkt = vwutils.get_tool_point()
    log("Klickpunkt (Dokumenteinheiten): %s" % (punkt,))
    if punkt is None:
        vwutils.alert(
            u"Es konnte kein Einfuegepunkt ermittelt werden.\n\n"
            u"Bitte pruefen Sie im Plug-in-Manager unter „Einstellungen > "
            u"Eigenschaften“, ob „Script ausfuehren“ auf „Nach Mausklick“ "
            u"steht.")
        return False

    # --- 2  Umgebung einmal einlesen --------------------------------------
    einheiten = vwutils.get_unit_context()
    log("Einheiten: upi=%s   1,00 m = %s Dokumenteinheiten"
        % (einheiten.upi, round(einheiten.to_doc(1.0), 6)))

    symbole = symbolnamen_im_dokument()
    log("Symbole im Dokument: %d" % (len(symbole),))

    # --- 3  Neu anlegen oder Vorhandenes bearbeiten? -----------------------
    # Ohne Modusleiste (der Regelfall, siehe rigole_vw/bearbeiten.py)
    # entscheidet der Klickpunkt: liegt dort schon eine Rigole, fragt das
    # Werkzeug nach.
    modus = vwutils.mode_value(MODE_GROUP)

    vorb = bearbeiten.vorbereiten(
        punkt, bearbeiten.ART_RIGOLE,
        settings.load_settings(dlgmod.default_values()), modus)
    log(u"Modus: %s" % (vorb.text or u"Abbruch",))
    if not vorb.weiter:
        vwutils.status(u"Rigole: abgebrochen.")
        return False

    alt = vorb.alt
    kennung = vorb.kennung
    punkt = vorb.punkt
    vorgaben = vorb.vorgaben
    # Capture before the dialog; editing retains the existing instance angle.
    angle_deg = vwutils.rigole_angle(vs, alt)

    # --- 4  Dialog ---------------------------------------------------------
    werte = dlgmod.show_dialog(vorgaben, symbole)
    if werte is None:
        log("Dialog abgebrochen - es wurde nichts veraendert.")
        vwutils.status(u"Rigole: abgebrochen.")
        return False

    # --- 5  Symbol bereitstellen -------------------------------------------
    # Der Name ergibt sich aus dem Korbtyp bzw. den eingegebenen Massen.
    # Fehlt die Symboldefinition im Dokument, legt das Werkzeug sie an.
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

    # --- 6  Rechnen --------------------------------------------------------
    try:
        ergebnis = dlgmod.berechne(werte)
    except Exception as ex:
        vwutils.alert(u"Die Rigolendaten konnten nicht berechnet werden.\n\n"
                      u"Technische Meldung: %r" % (ex,))
        return False

    pruefung = validate_computed(ergebnis)
    if not pruefung.ok:
        vwutils.alert(pruefung.message_text())
        return False

    log("Gesamt          : " + fmt.fmt_triple(ergebnis.total_length,
                                              ergebnis.total_width,
                                              ergebnis.total_height))
    log("Anzahl Koerbe   : %d" % (ergebnis.basket_count,))
    if ergebnis.hat_schacht:
        log("Schaechte       : %d x %s, OK %s / UK %s"
            % (ergebnis.schacht_anzahl, ergebnis.schacht_dn,
               fmt.fmt_height(ergebnis.schacht_ok),
               fmt.fmt_height(ergebnis.schacht_uk)))
    log("Speichervolumen : " + fmt.fmt_volume(ergebnis.v_speicher))
    log("OK / UK         : %s / %s" % (fmt.fmt_height(ergebnis.ok),
                                       fmt.fmt_height(ergebnis.uk)))

    # --- 7  Symbolmasse gegen die Eingabe pruefen -------------------------
    if werte.get("draw_3d"):
        if not pruefe_symbolmasse(werte, ergebnis, einheiten):
            log(u"Vom Anwender abgebrochen (Symbolmasse).")
            vwutils.status(u"Rigole: abgebrochen.")
            return False

    # --- 8  Einstellungen merken ------------------------------------------
    settings.save_settings(werte)

    # Der Altbestand wird erst nach einem erfolgreichen Neubau entfernt.

    # --- 10  Bauen ---------------------------------------------------------
    try:
        info = bearbeiten.neu_aufbauen(
            alt, bearbeiten.ART_RIGOLE, kennung,
            lambda: builder.build_rigole(punkt, werte, ergebnis, einheiten,
                rigole_id=kennung, angle_deg=angle_deg))
    except builder.BauFehler as ex:
        vwutils.alert(str(ex))
        log("FEHLER: %s" % (ex,))
        return False

    log(u"Rigole %s erzeugt. Symbol %r %s, %d Einzelobjekte."
        % (info["rigole_id"], info["symbolname"],
           u"neu angelegt" if info["symbol_neu"] else u"wiederverwendet",
           info["anzahl_objekte"]))

    vwutils.status(
        u"Rigole %s „%s“%s: %s, %s, %d Koerbe"
        % (info["rigole_id"], info["symbolname"],
           u" (bearbeitet)" if alt is not None else u"",
           fmt.fmt_triple(ergebnis.total_length, ergebnis.total_width,
                          ergebnis.total_height),
           fmt.fmt_volume(ergebnis.v_speicher),
           ergebnis.basket_count))

    return True


# ---------------------------------------------------------------------------
# Warum es KEINEN zweiten Klick fuer die Beschriftung gibt
# ---------------------------------------------------------------------------
# Anforderung Punkt 10 sah vor, die Textposition optional mit einem zweiten
# Klick festzulegen. In einem Werkzeug mit der Einstellung
# "Script ausfuehren = Nach Mausklick" ist das nicht sinnvoll umsetzbar:
#
#   * vs.GetPt() laesst sich zwar aufrufen, der Rueckruf kommt aber nicht an -
#     der naechste Mausklick startet stattdessen einen neuen Werkzeuglauf und
#     damit eine zweite Rigole.
#   * vstGetPt2D/vstNumPts liefern auch bei "Nach Mausbewegung" keine zwei
#     Punkte (gemessen in den Pruefberichten C, C2 und D).
#
# Stattdessen: Der Versatz der Beschriftung ist im Dialog einstellbar, und der
# fertige Text ist ein ganz normales Vectorworks-Textobjekt - ein Klick
# darauf, und er laesst sich frei verschieben.
#
# Wer den zweiten Klick wirklich braucht, bekommt ihn spaeter sauber ueber
# einen eigenen Menuebefehl (.vsm) "Rigolenbeschriftung setzen": Rigole
# auswaehlen, Befehl aufrufen, Position anklicken. In einem Menuebefehl ist
# vs.GetPt der dokumentierte und funktionierende Weg.
