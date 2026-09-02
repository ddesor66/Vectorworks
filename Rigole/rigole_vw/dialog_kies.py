# -*- coding: utf-8 -*-
"""
Einstellungsdialog des Werkzeugs KIESRIGOLE.

Seit dem 24.08.2026 sind Rigole und Kiesrigole zwei getrennte Werkzeuge -
das gemeinsame Fenster war schlicht zu gross geworden. Dieser Dialog zeigt
deshalb nur noch, was zur Kiesrigole gehoert: Abmessungen, Fuellmaterial,
Draenrohr und Kontrollschaechte. Kein Korbraster, keine Anordnung.

Erzeugt KEINE Geometrie. Liefert nur ein Wertedictionary zurueck oder None,
wenn der Anwender abbricht.

Die kleinen Lese- und Schreibhilfen samt der beiden Dialogregeln aus
Pruefbericht C2 stehen in dlgutils.py.

Kompatibilitaet: Python 3.9.2 (Vectorworks 2026)
"""

import vs

MANUFACTURER = "manufactured by Julian M."


def _dialog_title(title):
    return "%s | v%s | %s" % (str(title), TOOL_VERSION, MANUFACTURER)

from rigole_config import kies_types as kt
from rigole_config.basket_types import LOAD_CLASSES, DEFAULT_LOAD_CLASS
from rigole_config.constants import (
    TOOL_VERSION,
    HEIGHT_MODE_OK, HEIGHT_MODE_UK,
    LABEL_FIELDS, TEXT_OFFSET_X, TEXT_OFFSET_Y,
    ART_KIESRIGOLE,
)
from rigole_config.dialog_ids import (
    G_ART, T_SYSTEM, E_SYSTEM,
    T_KOEFF, E_KOEFF, T_KLASSE, P_KLASSE,
    T_HBEZUG, P_HBEZUG, T_HWERT, E_HWERT, C_EBENENHOEHE,
    C_2D, C_3D,
    G_KIES_ROHR, G_KIES_SCHACHT, G_KIES_SPEICHER,
    G_BESCHRIFTUNG, C_LABEL, T_LABEL_OFF, E_LOFF_X, E_LOFF_Y,
    T_KOMMENTAR, E_KOMMENTAR, LABEL_CHECK_BASE,
    G_ERGEBNIS, R_GESAMT, R_ANZAHL, R_VOLUMEN, R_SPEICHER, R_HOEHEN,
    R_HINWEIS,
    G_KIES, T_KIES_L, E_KIES_L, T_KIES_B, E_KIES_B, T_KIES_H, E_KIES_H,
    T_KIES_MATERIAL, P_KIES_MATERIAL, T_KIES_ROHR, P_KIES_ROHR,
    T_KIES_UK, E_KIES_UK, T_KIES_INFO,
    C_KIES_SCHACHT, T_KIES_SCHACHT_DN, P_KIES_SCHACHT_DN,
    T_KIES_SCHACHT_OK, E_KIES_SCHACHT_OK, T_KIES_SCHACHT_INFO,
)
from rigole_core import calculations as calc
from rigole_core import formatting as fmt
from rigole_core.validation import validate_kies_parameters
from rigole_vw import dlgutils as dl
from rigole_vw.dlgutils import (
    EV_SETUP, EV_CLOSE, EV_OK, EV_CANCEL, BREITE_LABEL, BREITE_FELD, Z,
)


HBEZUG_TEXTE = ["Oberkante bekannt", "Unterkante bekannt"]
HBEZUG_WERTE = [HEIGHT_MODE_OK, HEIGHT_MODE_UK]

# Beschriftungszeilen, die es bei der Kiesrigole nicht gibt.
NUR_KOERBE = ("korb", "anordnung", "verschweisst", "flaeche")


# ---------------------------------------------------------------------------
# Dialogaufbau
# ---------------------------------------------------------------------------

def _baue_dialog():
    dlg = vs.CreateLayout(_dialog_title("PD Rigole – Kiesrigole"), False,
                          "Kiesrigole erzeugen", "Abbrechen")
    Z.dlg = dlg

    # --- A - Bezeichnung --------------------------------------------------
    vs.CreateGroupBox(dlg, G_ART, "Kiesrigole", True)
    vs.CreateStaticText(dlg, T_SYSTEM, "Bezeichnung / System:", BREITE_LABEL)
    vs.CreateEditText(dlg, E_SYSTEM, "", 28)

    # --- K - Abmessungen und Fuellung -------------------------------------
    vs.CreateGroupBox(dlg, G_KIES, "Abmessungen und Fuellung", True)
    vs.CreateStaticText(dlg, T_KIES_L, "Laenge [m]:", BREITE_LABEL)
    vs.CreateEditReal(dlg, E_KIES_L, 1, kt.DEFAULT_KIES_LAENGE, BREITE_FELD)
    vs.CreateStaticText(dlg, T_KIES_B, "Breite [m]:", BREITE_LABEL)
    vs.CreateEditReal(dlg, E_KIES_B, 1, kt.DEFAULT_KIES_BREITE, BREITE_FELD)
    vs.CreateStaticText(dlg, T_KIES_H, "Hoehe [m]:", BREITE_LABEL)
    vs.CreateEditReal(dlg, E_KIES_H, 1, kt.DEFAULT_KIES_HOEHE, BREITE_FELD)
    vs.CreateStaticText(dlg, T_KIES_MATERIAL, "Material:", BREITE_LABEL)
    vs.CreatePullDownMenu(dlg, P_KIES_MATERIAL, 24)

    # --- Draenrohr ---------------------------------------------------------
    vs.CreateGroupBox(dlg, G_KIES_ROHR, "Draenrohr", True)
    vs.CreateStaticText(dlg, T_KIES_ROHR, "Draenrohr:", BREITE_LABEL)
    vs.CreatePullDownMenu(dlg, P_KIES_ROHR, 20)
    vs.CreateStaticText(dlg, T_KIES_UK, "UK Rohr ueber Sohle [m]:",
                        BREITE_LABEL)
    vs.CreateEditReal(dlg, E_KIES_UK, 1, kt.DEFAULT_ROHR_UK, BREITE_FELD)
    vs.CreateStaticText(dlg, T_KIES_INFO, " ", 46)

    # --- Kontrollschaechte -------------------------------------------------
    vs.CreateGroupBox(dlg, G_KIES_SCHACHT, "Kontrollschaechte", True)
    vs.CreateCheckBox(dlg, C_KIES_SCHACHT, "Kontrollschaechte setzen")
    vs.CreateStaticText(dlg, T_KIES_SCHACHT_DN, "Schacht:", BREITE_LABEL)
    vs.CreatePullDownMenu(dlg, P_KIES_SCHACHT_DN, 20)
    vs.CreateStaticText(dlg, T_KIES_SCHACHT_OK, "OK Schacht [m]:",
                        BREITE_LABEL)
    vs.CreateEditReal(dlg, E_KIES_SCHACHT_OK, 1, kt.DEFAULT_SCHACHT_OK,
                      BREITE_FELD)
    vs.CreateStaticText(dlg, T_KIES_SCHACHT_INFO, " ", 46)

    # --- Speicher und Hoehenlage ------------------------------------------
    vs.CreateGroupBox(dlg, G_KIES_SPEICHER, "Speicher und Hoehenlage", True)
    vs.CreateStaticText(dlg, T_KOEFF, "Speicherkoeffizient [%]:", BREITE_LABEL)
    vs.CreateEditReal(dlg, E_KOEFF, 1, 30.0, BREITE_FELD)
    vs.CreateStaticText(dlg, T_KLASSE, "Belastungsklasse:", BREITE_LABEL)
    vs.CreatePullDownMenu(dlg, P_KLASSE, 12)
    vs.CreateStaticText(dlg, T_HBEZUG, "Hoehenbezug:", BREITE_LABEL)
    vs.CreatePullDownMenu(dlg, P_HBEZUG, 24)
    vs.CreateStaticText(dlg, T_HWERT, "Hoehe [m]:", BREITE_LABEL)
    vs.CreateEditReal(dlg, E_HWERT, 1, 43.25, BREITE_FELD)
    vs.CreateCheckBox(dlg, C_EBENENHOEHE, "Ebenenhoehe beruecksichtigen")
    vs.CreateCheckBox(dlg, C_2D, "2D-Darstellung erzeugen")
    vs.CreateCheckBox(dlg, C_3D, "3D-Darstellung erzeugen")

    # --- Beschriftung ------------------------------------------------------
    vs.CreateGroupBox(dlg, G_BESCHRIFTUNG, "Beschriftung", True)
    vs.CreateCheckBox(dlg, C_LABEL, "Beschriftung erzeugen")
    vs.CreateStaticText(dlg, T_LABEL_OFF, "Versatz rechts / oben [m]:",
                        BREITE_LABEL)
    vs.CreateEditReal(dlg, E_LOFF_X, 1, TEXT_OFFSET_X, 8)
    vs.CreateEditReal(dlg, E_LOFF_Y, 1, TEXT_OFFSET_Y, 8)
    for i, (schluessel, anzeige, standard) in enumerate(LABEL_FIELDS):
        vs.CreateCheckBox(dlg, LABEL_CHECK_BASE + i, anzeige)
    vs.CreateStaticText(dlg, T_KOMMENTAR, "Kommentar:", BREITE_LABEL)
    vs.CreateEditText(dlg, E_KOMMENTAR, "", 28)

    # --- Ergebnisanzeige ---------------------------------------------------
    vs.CreateGroupBox(dlg, G_ERGEBNIS, "Ergebnis", True)
    for item in (R_GESAMT, R_ANZAHL, R_VOLUMEN, R_SPEICHER, R_HOEHEN,
                 R_HINWEIS):
        vs.CreateStaticText(dlg, item, " ", 46)

    # --- linke Spalte ------------------------------------------------------
    vs.SetFirstLayoutItem(dlg, G_ART)
    vs.SetBelowItem(dlg, G_ART, G_KIES, 0, 0)
    vs.SetBelowItem(dlg, G_KIES, G_KIES_ROHR, 0, 0)
    vs.SetBelowItem(dlg, G_KIES_ROHR, G_KIES_SCHACHT, 0, 0)

    # --- rechte Spalte -----------------------------------------------------
    vs.SetRightItem(dlg, G_ART, G_KIES_SPEICHER, 0, 0)
    vs.SetBelowItem(dlg, G_KIES_SPEICHER, G_BESCHRIFTUNG, 0, 0)
    vs.SetBelowItem(dlg, G_BESCHRIFTUNG, G_ERGEBNIS, 0, 0)

    # --- Inhalt der Gruppen ------------------------------------------------
    vs.SetFirstGroupItem(dlg, G_ART, T_SYSTEM)
    vs.SetRightItem(dlg, T_SYSTEM, E_SYSTEM, 0, 0)

    vs.SetFirstGroupItem(dlg, G_KIES, T_KIES_L)
    vs.SetRightItem(dlg, T_KIES_L, E_KIES_L, 0, 0)
    vs.SetBelowItem(dlg, T_KIES_L, T_KIES_B, 0, 0)
    vs.SetRightItem(dlg, T_KIES_B, E_KIES_B, 0, 0)
    vs.SetBelowItem(dlg, T_KIES_B, T_KIES_H, 0, 0)
    vs.SetRightItem(dlg, T_KIES_H, E_KIES_H, 0, 0)
    vs.SetBelowItem(dlg, T_KIES_H, T_KIES_MATERIAL, 0, 0)
    vs.SetRightItem(dlg, T_KIES_MATERIAL, P_KIES_MATERIAL, 0, 0)

    vs.SetFirstGroupItem(dlg, G_KIES_ROHR, T_KIES_ROHR)
    vs.SetRightItem(dlg, T_KIES_ROHR, P_KIES_ROHR, 0, 0)
    vs.SetBelowItem(dlg, T_KIES_ROHR, T_KIES_UK, 0, 0)
    vs.SetRightItem(dlg, T_KIES_UK, E_KIES_UK, 0, 0)
    vs.SetBelowItem(dlg, T_KIES_UK, T_KIES_INFO, 0, 0)

    vs.SetFirstGroupItem(dlg, G_KIES_SCHACHT, C_KIES_SCHACHT)
    vs.SetBelowItem(dlg, C_KIES_SCHACHT, T_KIES_SCHACHT_DN, 0, 0)
    vs.SetRightItem(dlg, T_KIES_SCHACHT_DN, P_KIES_SCHACHT_DN, 0, 0)
    vs.SetBelowItem(dlg, T_KIES_SCHACHT_DN, T_KIES_SCHACHT_OK, 0, 0)
    vs.SetRightItem(dlg, T_KIES_SCHACHT_OK, E_KIES_SCHACHT_OK, 0, 0)
    vs.SetBelowItem(dlg, T_KIES_SCHACHT_OK, T_KIES_SCHACHT_INFO, 0, 0)

    vs.SetFirstGroupItem(dlg, G_KIES_SPEICHER, T_KOEFF)
    vs.SetRightItem(dlg, T_KOEFF, E_KOEFF, 0, 0)
    vs.SetBelowItem(dlg, T_KOEFF, T_KLASSE, 0, 0)
    vs.SetRightItem(dlg, T_KLASSE, P_KLASSE, 0, 0)
    vs.SetBelowItem(dlg, T_KLASSE, T_HBEZUG, 0, 0)
    vs.SetRightItem(dlg, T_HBEZUG, P_HBEZUG, 0, 0)
    vs.SetBelowItem(dlg, T_HBEZUG, T_HWERT, 0, 0)
    vs.SetRightItem(dlg, T_HWERT, E_HWERT, 0, 0)
    vs.SetBelowItem(dlg, T_HWERT, C_EBENENHOEHE, 0, 0)
    vs.SetBelowItem(dlg, C_EBENENHOEHE, C_2D, 0, 0)
    vs.SetBelowItem(dlg, C_2D, C_3D, 0, 0)

    vs.SetFirstGroupItem(dlg, G_BESCHRIFTUNG, C_LABEL)
    vs.SetBelowItem(dlg, C_LABEL, T_LABEL_OFF, 0, 0)
    vs.SetRightItem(dlg, T_LABEL_OFF, E_LOFF_X, 0, 0)
    vs.SetRightItem(dlg, E_LOFF_X, E_LOFF_Y, 0, 0)
    vorheriges = T_LABEL_OFF
    for i in range(len(LABEL_FIELDS)):
        aktuell = LABEL_CHECK_BASE + i
        if i % 2 == 0:
            vs.SetBelowItem(dlg, vorheriges, aktuell, 0, 0)
            vorheriges = aktuell
        else:
            vs.SetRightItem(dlg, aktuell - 1, aktuell, 0, 0)
    vs.SetBelowItem(dlg, vorheriges, T_KOMMENTAR, 0, 0)
    vs.SetRightItem(dlg, T_KOMMENTAR, E_KOMMENTAR, 0, 0)

    vs.SetFirstGroupItem(dlg, G_ERGEBNIS, R_GESAMT)
    vs.SetBelowItem(dlg, R_GESAMT, R_ANZAHL, 0, 0)
    vs.SetBelowItem(dlg, R_ANZAHL, R_VOLUMEN, 0, 0)
    vs.SetBelowItem(dlg, R_VOLUMEN, R_SPEICHER, 0, 0)
    vs.SetBelowItem(dlg, R_SPEICHER, R_HOEHEN, 0, 0)
    vs.SetBelowItem(dlg, R_HOEHEN, R_HINWEIS, 0, 0)

    return dlg


# ---------------------------------------------------------------------------
# Startwerte  (nur im Ereignis 12255!)
# ---------------------------------------------------------------------------

def _setup(defaults):
    dl.fuelle(P_KIES_MATERIAL, kt.material_names())
    dl.fuelle(P_KIES_ROHR, kt.draenrohr_names())
    dl.fuelle(P_KIES_SCHACHT_DN, kt.schacht_namen())
    dl.fuelle(P_KLASSE, LOAD_CLASSES)
    dl.fuelle(P_HBEZUG, HBEZUG_TEXTE)

    dl.setze_auswahl(P_KIES_MATERIAL, kt.material_names(),
                     defaults.get("kies_material", kt.DEFAULT_KIES_MATERIAL))
    dl.setze_auswahl(P_KIES_ROHR, kt.draenrohr_names(),
                     defaults.get("kies_rohr_dn", kt.DEFAULT_DRAENROHR))
    dl.setze_auswahl(P_KIES_SCHACHT_DN, kt.schacht_namen(),
                     defaults.get("kies_schacht_dn", kt.DEFAULT_SCHACHT))
    dl.setze_auswahl(P_KLASSE, LOAD_CLASSES,
                     defaults.get("load_class", DEFAULT_LOAD_CLASS))
    dl.setze_auswahl(P_HBEZUG, HBEZUG_WERTE,
                     defaults.get("height_mode", HEIGHT_MODE_OK))

    dl.setze_text(E_SYSTEM, defaults.get("system_name", ""))
    dl.setze_text(E_KOMMENTAR, defaults.get("comment", ""))

    for item, schluessel, standard in (
            (E_KIES_L, "kies_laenge", kt.DEFAULT_KIES_LAENGE),
            (E_KIES_B, "kies_breite", kt.DEFAULT_KIES_BREITE),
            (E_KIES_H, "kies_hoehe", kt.DEFAULT_KIES_HOEHE),
            (E_KIES_UK, "kies_rohr_uk", kt.DEFAULT_ROHR_UK),
            (E_KIES_SCHACHT_OK, "kies_schacht_ok", kt.DEFAULT_SCHACHT_OK),
            (E_HWERT, "height_value", 43.25),
            (E_LOFF_X, "label_offset_x", TEXT_OFFSET_X),
            (E_LOFF_Y, "label_offset_y", TEXT_OFFSET_Y)):
        dl.setze_real(item, defaults.get(schluessel, standard))

    for item, schluessel, standard in (
            (C_EBENENHOEHE, "use_layer_elevation", False),
            (C_2D, "draw_2d", True),
            (C_3D, "draw_3d", True),
            (C_LABEL, "create_label", True),
            (C_KIES_SCHACHT, "kies_mit_schacht", True)):
        dl.setze_ja_nein(item, defaults.get(schluessel, standard))

    label_felder = defaults.get("label_fields") or {}
    for i, (schluessel, anzeige, standard) in enumerate(LABEL_FIELDS):
        dl.setze_ja_nein(LABEL_CHECK_BASE + i,
                         bool(label_felder.get(schluessel, standard)))

    # Der Hohlraumanteil kommt aus dem Fuellmaterial. Ein zuletzt abweichend
    # eingegebener Wert bleibt erhalten - er ist nur ein Vorschlag.
    gespeichert = defaults.get("storage_percent")
    if gespeichert is None:
        _uebernehme_material()
    else:
        dl.setze_real(E_KOEFF, gespeichert)

    dl.hilfetext(P_KIES_MATERIAL,
                 "Der Hohlraumanteil des Materials wird als Vorschlag in den "
                 "Speicherkoeffizienten uebernommen und kann dort "
                 "ueberschrieben werden.")
    dl.hilfetext(E_KIES_UK,
                 "Abstand der ROHRUNTERKANTE zur Kiessohle. 0 bedeutet "
                 "aufliegend. Die Rohrachse errechnet das Werkzeug daraus "
                 "selbst: UK + halber Nenndurchmesser.")
    dl.hilfetext(C_KIES_SCHACHT,
                 "Je ein senkrechter Kontrollschacht vorne und hinten; ihre "
                 "Aussenkante liegt 20 cm innerhalb der Kiesfuellung. Ueber "
                 "20 m Achsabstand kommt einer in die Mitte. Das Draenrohr "
                 "laeuft nur zwischen den Schaechten.")
    dl.hilfetext(E_KIES_SCHACHT_OK,
                 "Absolute Hoehenkote der Schachtoberkante, im selben Bezug "
                 "wie OK und UK der Rigole. Die Unterkante liegt 20 cm unter "
                 "der Rohrunterkante.")
    dl.hilfetext(P_KLASSE,
                 "Reine Planungsangabe nach DIN EN 1433 / DIN EN 124. Es "
                 "findet keine statische Bemessung statt.")
    dl.hilfetext(E_KOEFF,
                 "Anteil des Bruttovolumens, der tatsaechlich Wasser "
                 "aufnimmt. Groesser 0 % und hoechstens 100 %.")


def _uebernehme_material():
    """Traegt den Hohlraumanteil des Materials als Vorschlag ein."""
    material = dl.auswahl(P_KIES_MATERIAL, kt.material_names(),
                          kt.DEFAULT_KIES_MATERIAL)
    dl.setze_real(E_KOEFF, float(kt.coefficient_for(material)) * 100.0)


# ---------------------------------------------------------------------------
# Infozeilen und Zustaende
# ---------------------------------------------------------------------------

def _rohr_info_text():
    """
    Gegenprobe zur Rohrauswahl: mit welchem Durchmesser wird tatsaechlich
    gebaut, und wo liegt die Achse dadurch?
    """
    rohr = dl.auswahl(P_KIES_ROHR, kt.draenrohr_names(), kt.DEFAULT_DRAENROHR)
    if not kt.hat_draenrohr(rohr):
        return u"ohne Draenrohr"
    d = kt.rohr_durchmesser(rohr)
    uk = max(0.0, dl.real(E_KIES_UK, 0.0))
    achse = calc.pipe_axis_height(d, uk)
    zusatz = u" (aufliegend)" if uk <= 0.0 else u""
    return u"%s: Durchmesser %s, UK %s ueber Sohle%s, Achse %s" % (
        rohr, fmt.fmt_length(d, places=3), fmt.fmt_length(uk, places=3),
        zusatz, fmt.fmt_length(achse, places=3))


def _schacht_info_text():
    """Wie viele Schaechte entstehen, wo sie sitzen, wie tief sie reichen."""
    laenge = dl.real(E_KIES_L, 0.0)
    rohr = dl.auswahl(P_KIES_ROHR, kt.draenrohr_names(), kt.DEFAULT_DRAENROHR)
    if laenge <= 0.0 or not kt.hat_draenrohr(rohr):
        return u"—"

    schacht = dl.auswahl(P_KIES_SCHACHT_DN, kt.schacht_namen(),
                         kt.DEFAULT_SCHACHT)
    schacht_d = kt.schacht_durchmesser(schacht)
    positionen = calc.schacht_positionen(laenge, schacht_d, kt.SCHACHT_RAND,
                                         kt.SCHACHT_MITTE_AB_LAENGE)
    if not positionen:
        return (u"%s passt nicht in eine %s lange Rigole (noetig: mehr als "
                u"%s)." % (schacht, fmt.fmt_length(laenge),
                           fmt.fmt_length(schacht_d + 2 * kt.SCHACHT_RAND)))

    rohr_uk = max(0.0, dl.real(E_KIES_UK, 0.0))
    unter_sohle = kt.SCHACHT_TIEFE_UNTER_ROHR - rohr_uk

    text = u"%d x %s, Achsen bei %s" % (
        len(positionen), schacht,
        u" / ".join(fmt.fmt_length(p, unit=False) for p in positionen))
    if unter_sohle > 0.0:
        text += u", UK %s unter der Kiessohle" % (
            fmt.fmt_length(unter_sohle, places=3),)
    return text


def _aktualisiere_zustaende():
    mit_rohr = kt.hat_draenrohr(
        dl.auswahl(P_KIES_ROHR, kt.draenrohr_names(), kt.DEFAULT_DRAENROHR))
    dl.aktiv(E_KIES_UK, mit_rohr)
    dl.setze_text(T_KIES_INFO, _rohr_info_text())

    # Schaechte gibt es nur zusammen mit einem Draenrohr.
    dl.aktiv(C_KIES_SCHACHT, mit_rohr)
    schacht_an = mit_rohr and dl.ja_nein(C_KIES_SCHACHT, True)
    dl.aktiv(P_KIES_SCHACHT_DN, schacht_an)
    dl.aktiv(E_KIES_SCHACHT_OK, schacht_an)
    dl.setze_text(T_KIES_SCHACHT_INFO,
                  _schacht_info_text() if schacht_an else u"—")

    label_an = dl.ja_nein(C_LABEL, True)
    dl.aktiv(E_LOFF_X, label_an)
    dl.aktiv(E_LOFF_Y, label_an)
    for i, (schluessel, anzeige, standard) in enumerate(LABEL_FIELDS):
        dl.aktiv(LABEL_CHECK_BASE + i,
                 label_an and schluessel not in NUR_KOERBE)


# ---------------------------------------------------------------------------
# Werte einsammeln  (nur INNERHALB des Handlers!)
# ---------------------------------------------------------------------------

def _lies_alles():
    werte = {}
    werte["rigole_type"] = ART_KIESRIGOLE
    werte["ist_kiesrigole"] = True
    werte["system_name"] = dl.text(E_SYSTEM, "")

    werte["kies_laenge"] = dl.real(E_KIES_L, 0.0)
    werte["kies_breite"] = dl.real(E_KIES_B, 0.0)
    werte["kies_hoehe"] = dl.real(E_KIES_H, 0.0)
    werte["kies_material"] = dl.auswahl(P_KIES_MATERIAL, kt.material_names(),
                                        kt.DEFAULT_KIES_MATERIAL)

    werte["kies_rohr_dn"] = dl.auswahl(P_KIES_ROHR, kt.draenrohr_names(),
                                       kt.DEFAULT_DRAENROHR)
    werte["kies_rohr_durchmesser"] = kt.rohr_durchmesser(werte["kies_rohr_dn"])
    werte["kies_rohr_uk"] = dl.real(E_KIES_UK, 0.0)

    werte["kies_mit_schacht"] = dl.ja_nein(C_KIES_SCHACHT, True)
    werte["kies_schacht_dn"] = dl.auswahl(P_KIES_SCHACHT_DN,
                                          kt.schacht_namen(),
                                          kt.DEFAULT_SCHACHT)
    werte["kies_schacht_durchmesser"] = kt.schacht_durchmesser(
        werte["kies_schacht_dn"])
    werte["kies_schacht_ok"] = dl.real(E_KIES_SCHACHT_OK,
                                       kt.DEFAULT_SCHACHT_OK)
    werte["kies_schacht_tiefe"] = kt.SCHACHT_TIEFE_UNTER_ROHR
    werte["kies_schacht_rand"] = kt.SCHACHT_RAND
    werte["kies_schacht_grenze"] = kt.SCHACHT_MITTE_AB_LAENGE

    werte["storage_percent"] = dl.real(E_KOEFF, 0.0)
    werte["load_class"] = dl.auswahl(P_KLASSE, LOAD_CLASSES,
                                     DEFAULT_LOAD_CLASS)
    werte["height_mode"] = dl.auswahl(P_HBEZUG, HBEZUG_WERTE, HEIGHT_MODE_OK)
    werte["height_value"] = dl.real(E_HWERT, 0.0)
    werte["use_layer_elevation"] = dl.ja_nein(C_EBENENHOEHE, False)

    werte["draw_2d"] = dl.ja_nein(C_2D, True)
    werte["draw_3d"] = dl.ja_nein(C_3D, True)

    werte["create_label"] = dl.ja_nein(C_LABEL, True)
    werte["label_offset_x"] = dl.real(E_LOFF_X, TEXT_OFFSET_X)
    werte["label_offset_y"] = dl.real(E_LOFF_Y, TEXT_OFFSET_Y)
    label_felder = {}
    for i, (schluessel, anzeige, standard) in enumerate(LABEL_FIELDS):
        label_felder[schluessel] = dl.ja_nein(LABEL_CHECK_BASE + i, standard)
    werte["label_fields"] = label_felder
    werte["comment"] = dl.text(E_KOMMENTAR, "")
    return werte


def berechne(werte):
    """KiesResult aus den Dialogwerten - auch vom Werkzeug benutzt."""
    return calc.compute_kiesrigole(
        werte["kies_laenge"], werte["kies_breite"], werte["kies_hoehe"],
        calc.percent_to_factor(werte["storage_percent"]),
        werte["height_mode"], werte["height_value"],
        material=werte.get("kies_material", ""),
        rohr_dn=werte.get("kies_rohr_dn", ""),
        rohr_durchmesser=werte.get("kies_rohr_durchmesser", 0.0),
        rohr_uk_ueber_sohle=werte.get("kies_rohr_uk", 0.0),
        mit_schacht=werte.get("kies_mit_schacht", False),
        schacht_dn=werte.get("kies_schacht_dn", ""),
        schacht_durchmesser=werte.get("kies_schacht_durchmesser", 0.0),
        schacht_ok=werte.get("kies_schacht_ok"),
        schacht_tiefe_unter_rohr=werte.get("kies_schacht_tiefe", 0.20),
        schacht_rand=werte.get("kies_schacht_rand", 0.20),
        schacht_mitte_ab_laenge=werte.get("kies_schacht_grenze", 20.0))


# ---------------------------------------------------------------------------
# Ergebnisanzeige
# ---------------------------------------------------------------------------

def _aktualisiere_ergebnis():
    werte = _lies_alles()
    hinweis = ""
    try:
        if (werte["kies_laenge"] <= 0 or werte["kies_breite"] <= 0
                or werte["kies_hoehe"] <= 0):
            raise ValueError("unvollstaendig")

        ergebnis = berechne(werte)

        dl.setze_text(R_GESAMT, "Gesamtmasse: " + fmt.fmt_triple(
            ergebnis.total_length, ergebnis.total_width,
            ergebnis.total_height))
        if ergebnis.hat_schacht:
            dl.setze_text(R_ANZAHL, u"Material: %s   |   %d Schaechte %s"
                          % (ergebnis.material, ergebnis.schacht_anzahl,
                             ergebnis.schacht_dn))
        else:
            dl.setze_text(R_ANZAHL, "Material: %s" % (ergebnis.material,))
        dl.setze_text(R_VOLUMEN, "Bruttovolumen: " + fmt.fmt_volume(
            ergebnis.v_brutto, places=3))
        dl.setze_text(R_SPEICHER, "Speichervolumen: " + fmt.fmt_volume(
            ergebnis.v_speicher))
        dl.setze_text(R_HOEHEN, "OK %s   /   UK %s" % (
            fmt.fmt_height(ergebnis.ok), fmt.fmt_height(ergebnis.uk)))

        if ergebnis.hat_rohr:
            hinweis = (u"Draenrohr %s: %s verlegt, Volumen %s "
                       u"(im Speichervolumen NICHT beruecksichtigt)."
                       % (ergebnis.rohr_dn,
                          fmt.fmt_length(ergebnis.rohr_laenge),
                          fmt.fmt_volume(ergebnis.rohr_volumen, places=3)))
            if ergebnis.hat_schacht:
                hinweis += (u"  %d Schaechte %s, Bauhoehe %s."
                            % (ergebnis.schacht_anzahl, ergebnis.schacht_dn,
                               fmt.fmt_length(ergebnis.schacht_hoehe)))
    except Exception:
        for item in (R_GESAMT, R_ANZAHL, R_VOLUMEN, R_SPEICHER, R_HOEHEN):
            dl.setze_text(item, " ")
        hinweis = "Bitte Laenge, Breite und Hoehe der Kiesrigole ausfuellen."

    dl.setze_text(R_HINWEIS, hinweis if hinweis else " ")


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

def _handler(item, data):
    try:
        if item == EV_SETUP:
            _setup(Z.defaults)
            _aktualisiere_zustaende()
            _aktualisiere_ergebnis()
            return item

        if item == EV_CLOSE:
            return item

        if item == EV_CANCEL:
            Z.abgebrochen = True
            return item

        if item == EV_OK:
            # Werte lesen, SOLANGE der Dialog noch existiert.
            werte = _lies_alles()
            pruefung = validate_kies_parameters(werte)
            if not pruefung.ok:
                vs.AlrtDialog(pruefung.message_text(include_warnings=False))
                return -1        # Dialog offen lassen
            if pruefung.warnings:
                text = pruefung.message_text()
                if not vs.YNDialog(text + "\n\nTrotzdem fortfahren?"):
                    return -1
            Z.werte = werte
            Z.abgebrochen = False
            return item

        if item == P_KIES_MATERIAL:
            _uebernehme_material()
        _aktualisiere_zustaende()
        _aktualisiere_ergebnis()
        return item

    except Exception as ex:
        try:
            vs.AlrtDialog("Unerwarteter Fehler im Dialog:\n\n%r" % (ex,))
        except Exception:
            pass
        return item


# ---------------------------------------------------------------------------
# Oeffentliche Schnittstelle
# ---------------------------------------------------------------------------

def show_dialog(defaults, symbolnamen=None):
    """Rueckgabe: dict mit den Eingaben, oder None bei Abbruch."""
    return dl.starte(_baue_dialog, _handler, defaults, symbolnamen)


def default_values():
    """Werksvorgaben, falls noch nichts gespeichert wurde."""
    return {
        "system_name": "",
        "kies_laenge": kt.DEFAULT_KIES_LAENGE,
        "kies_breite": kt.DEFAULT_KIES_BREITE,
        "kies_hoehe": kt.DEFAULT_KIES_HOEHE,
        "kies_material": kt.DEFAULT_KIES_MATERIAL,
        "kies_rohr_dn": kt.DEFAULT_DRAENROHR,
        "kies_rohr_uk": kt.DEFAULT_ROHR_UK,
        "kies_mit_schacht": True,
        "kies_schacht_dn": kt.DEFAULT_SCHACHT,
        "kies_schacht_ok": kt.DEFAULT_SCHACHT_OK,
        "storage_percent": kt.coefficient_for(kt.DEFAULT_KIES_MATERIAL) * 100.0,
        "load_class": DEFAULT_LOAD_CLASS,
        "height_mode": HEIGHT_MODE_OK,
        "height_value": 43.25,
        "use_layer_elevation": False,
        "draw_2d": True,
        "draw_3d": True,
        "create_label": True,
        "label_offset_x": TEXT_OFFSET_X,
        "label_offset_y": TEXT_OFFSET_Y,
        "label_fields": dict((k, d) for (k, _t, d) in LABEL_FIELDS),
        "comment": "",
    }
