# -*- coding: utf-8 -*-
"""
Werkzeug KIESRIGOLE - Einstiegspunkt.

Seit dem 24.08.2026 sind Rigole und Kiesrigole zwei getrennte .vst-Werkzeuge;
das gemeinsame Fenster war zu gross geworden. Beide teilen sich denselben
Modulordner - nur der Dialog und dieser Einstieg sind je Bauart eigen.

Wie beim Werkzeug 'Rigole' laeuft dieses Modul bei JEDEM Mausklick einmal
komplett durch:

    Klickpunkt holen  ->  Dialog  ->  rechnen  ->  bauen  ->  fertig

NEU ODER BEARBEITEN
-------------------
Das Werkzeug erkennt das selbst am Klickpunkt: liegt dort schon eine
Kiesrigole dieses Werkzeugs, fragt es nach, ob sie bearbeitet werden soll.
Klick ins Leere heisst neu anlegen. Warum es dafuer keine Modusleiste gibt,
steht in rigole_vw/bearbeiten.py.

Der gesamte Durchlauf ist ein einziger Undo-Schritt.

Kompatibilitaet: Python 3.9.2 (Vectorworks 2026)
"""

import vs

from rigole_config.constants import (
    TOOL_VERSION, MODE_GROUP,
)
from rigole_core import formatting as fmt
from rigole_core.validation import validate_kies_computed
from rigole_vw import (
    bearbeiten, builder, builder_kies, dialog_kies as dlgmod, settings,
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

def run():
    """Ein kompletter Werkzeuglauf."""
    del PROTOKOLL[:]
    log("=" * 70)
    log("Kiesrigole %s" % (TOOL_VERSION,))
    log("=" * 70)

    try:
        vs.vstNameUndoEvent(u"Kiesrigole")
    except Exception:
        pass
    try:
        vs.NameUndoEvent(u"Kiesrigole")
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

    # --- 3  Neu anlegen oder Vorhandenes bearbeiten? -----------------------
    # Ohne Modusleiste (der Regelfall, siehe rigole_vw/bearbeiten.py)
    # entscheidet der Klickpunkt: liegt dort schon eine Kiesrigole, fragt das
    # Werkzeug nach.
    modus = vwutils.mode_value(MODE_GROUP)

    vorb = bearbeiten.vorbereiten(
        punkt, bearbeiten.ART_KIES,
        settings.load_settings(dlgmod.default_values(),
                               settings.SETTINGS_KEY_KIES), modus)
    log(u"Modus: %s" % (vorb.text or u"Abbruch",))
    if not vorb.weiter:
        vwutils.status(u"Kiesrigole: abgebrochen.")
        return False

    alt = vorb.alt
    kennung = vorb.kennung
    punkt = vorb.punkt
    vorgaben = vorb.vorgaben
    angle_deg = vwutils.rigole_angle(vs, alt)

    # --- 4  Dialog ---------------------------------------------------------
    werte = dlgmod.show_dialog(vorgaben)
    if werte is None:
        log("Dialog abgebrochen - es wurde nichts veraendert.")
        vwutils.status(u"Kiesrigole: abgebrochen.")
        return False

    # --- 5  Rechnen --------------------------------------------------------
    try:
        ergebnis = dlgmod.berechne(werte)
    except Exception as ex:
        vwutils.alert(u"Die Kiesrigole konnte nicht berechnet werden.\n\n"
                      u"Technische Meldung: %r" % (ex,))
        return False

    pruefung = validate_kies_computed(ergebnis)
    if not pruefung.ok:
        vwutils.alert(pruefung.message_text())
        return False

    log("Gesamt          : " + fmt.fmt_triple(ergebnis.total_length,
                                              ergebnis.total_width,
                                              ergebnis.total_height))
    log("Material        : %s" % (ergebnis.material,))
    log("Speichervolumen : " + fmt.fmt_volume(ergebnis.v_speicher))
    log("Draenrohr       : %s" % (ergebnis.rohr_dn if ergebnis.hat_rohr
                                  else u"ohne",))
    if ergebnis.hat_rohr:
        log("Rohrlaenge      : %s verlegt (brutto %s)"
            % (fmt.fmt_length(ergebnis.rohr_laenge),
               fmt.fmt_length(ergebnis.rohr_laenge_brutto)))
    if ergebnis.hat_schacht:
        log("Schaechte       : %d x %s bei %s"
            % (ergebnis.schacht_anzahl, ergebnis.schacht_dn,
               ", ".join(fmt.fmt_length(p)
                         for p in ergebnis.schacht_positionen)))
        log("Schacht OK / UK : %s / %s"
            % (fmt.fmt_height(ergebnis.schacht_ok),
               fmt.fmt_height(ergebnis.schacht_uk)))
    log("OK / UK         : %s / %s" % (fmt.fmt_height(ergebnis.ok),
                                       fmt.fmt_height(ergebnis.uk)))

    # --- 6  Einstellungen merken ------------------------------------------
    settings.save_settings(werte, settings.SETTINGS_KEY_KIES)

    # Der Altbestand wird erst nach einem erfolgreichen Neubau entfernt.

    # --- 8  Bauen ----------------------------------------------------------
    try:
        info = bearbeiten.neu_aufbauen(
            alt, bearbeiten.ART_KIES, kennung,
            lambda: builder_kies.build_kiesrigole(punkt, werte, ergebnis, einheiten,
                kies_id=kennung, angle_deg=angle_deg))
    except builder.BauFehler as ex:
        vwutils.alert(str(ex))
        log("FEHLER: %s" % (ex,))
        return False

    log(u"Kiesrigole %s erzeugt. Symbol %r %s, %d Einzelobjekte."
        % (info["rigole_id"], info["symbolname"],
           u"neu angelegt" if info["symbol_neu"] else u"wiederverwendet",
           info["anzahl_objekte"]))

    vwutils.status(
        u"Kiesrigole %s „%s“%s: %s, %s, %s"
        % (info["rigole_id"], info["symbolname"],
           u" (bearbeitet)" if alt is not None else u"",
           fmt.fmt_triple(ergebnis.total_length, ergebnis.total_width,
                          ergebnis.total_height),
           fmt.fmt_volume(ergebnis.v_speicher),
           ergebnis.material))

    return True
