# -*- coding: utf-8 -*-
"""
Einstellungsdialog des Werkzeugs RIGOLE (Rigolenkoerper).

Seit dem 24.08.2026 sind Rigole und Kiesrigole zwei getrennte Werkzeuge -
das gemeinsame Fenster war zu gross geworden. Dieser Dialog zeigt deshalb
nur noch den Korbaufbau; die Kiesrigole steckt in dialog_kies.py.

Erzeugt KEINE Geometrie. Liefert nur ein Wertedictionary zurueck oder None,
wenn der Anwender abbricht.

Die kleinen Lese- und Schreibhilfen samt der beiden Dialogregeln aus
Pruefbericht C2 (AddChoice nur im Ereignis 12255, Werte nur INNERHALB des
Handlers lesen) stehen in dlgutils.py.

Kompatibilitaet: Python 3.9.2 (Vectorworks 2026)
"""

import vs

MANUFACTURER = "manufactured by Julian M."


def _dialog_title(title):
    return "%s | v%s | %s" % (str(title), TOOL_VERSION, MANUFACTURER)

from rigole_config import basket_types as bt
from rigole_config import kies_types as kt
from rigole_config.basket_types import LOAD_CLASSES, DEFAULT_LOAD_CLASS
from rigole_config.constants import (
    TOOL_VERSION,
    LENGTH_MODE_COUNT, LENGTH_MODE_TOTAL,
    HEIGHT_MODE_OK, HEIGHT_MODE_UK,
    ROUND_UP, ROUND_DOWN, ROUND_NEAREST,
    LABEL_FIELDS, TEXT_OFFSET_X, TEXT_OFFSET_Y,
)
from rigole_config.dialog_ids import (
    G_ART, T_SYSTEM, E_SYSTEM, T_SYSTEM_INFO,
    G_KORB, T_KORBTYP, P_KORBTYP,
    T_KORB_L, E_KORB_L, T_KORB_B, E_KORB_B, T_KORB_H, E_KORB_H,
    C_SWAP, T_SYMBOL_INFO,
    G_ANORDNUNG, T_ANZ_B, E_ANZ_B, T_ANZ_H, E_ANZ_H,
    T_MODUS, P_MODUS, T_ANZ_L, E_ANZ_L, T_ZIEL_L, E_ZIEL_L,
    T_RUNDUNG, P_RUNDUNG,
    G_EIGENSCHAFTEN, C_VERSCHWEISST, T_KOEFF, E_KOEFF, T_KLASSE, P_KLASSE,
    G_HOEHEN, T_HBEZUG, P_HBEZUG, T_HWERT, E_HWERT, C_EBENENHOEHE,
    G_DARSTELLUNG, C_2D, C_3D,
    G_BESCHRIFTUNG, C_LABEL, T_LABEL_OFF, E_LOFF_X, E_LOFF_Y,
    T_KOMMENTAR, E_KOMMENTAR, LABEL_CHECK_BASE,
    G_ERGEBNIS, R_GESAMT, R_ANZAHL, R_VOLUMEN, R_SPEICHER, R_HOEHEN,
    R_HINWEIS,
    G_SCHACHT, C_SCHACHT, T_SCHACHT_DN, P_SCHACHT_DN,
    T_SCHACHT_OK, E_SCHACHT_OK, T_SCHACHT_INFO,
)
from rigole_core import calculations as calc
from rigole_core import formatting as fmt
from rigole_core.validation import validate_parameters
from rigole_vw import dlgutils as dl
from rigole_vw.dlgutils import (
    EV_SETUP, EV_CLOSE, EV_OK, EV_CANCEL, BREITE_LABEL, BREITE_FELD, Z,
)


# ---------------------------------------------------------------------------
# Auswahllisten
# ---------------------------------------------------------------------------
MODUS_TEXTE = ["Anzahl Koerbe hintereinander", "gewuenschte Gesamtlaenge"]
MODUS_WERTE = [LENGTH_MODE_COUNT, LENGTH_MODE_TOTAL]

RUNDUNG_TEXTE = ["aufrunden", "abrunden", "naechstliegend"]
RUNDUNG_WERTE = [ROUND_UP, ROUND_DOWN, ROUND_NEAREST]

HBEZUG_TEXTE = ["Oberkante bekannt", "Unterkante bekannt"]
HBEZUG_WERTE = [HEIGHT_MODE_OK, HEIGHT_MODE_UK]

# Beschriftungszeilen, die es nur bei der Kiesrigole gibt.
NUR_KIES = ("material", "draenrohr", "flaeche")


# ---------------------------------------------------------------------------
# Dialogaufbau
# ---------------------------------------------------------------------------

def _baue_dialog():
    dlg = vs.CreateLayout(_dialog_title("PD Rigole – Rigolenkörper"),
                          False, "Rigole erzeugen",
                          "Abbrechen")
    Z.dlg = dlg

    # --- A - Rigolenkoerper (Hersteller / System) -------------------------
    vs.CreateGroupBox(dlg, G_ART, "Rigolenkoerper", True)
    vs.CreateStaticText(dlg, T_KORBTYP, "Hersteller / System:",
                        BREITE_LABEL)
    vs.CreatePullDownMenu(dlg, P_KORBTYP, 42)
    vs.CreateStaticText(dlg, T_SYSTEM_INFO, " ", 46)
    vs.CreateStaticText(dlg, T_SYSTEM, "Bezeichnung der Rigole:",
                        BREITE_LABEL)
    vs.CreateEditText(dlg, E_SYSTEM, "", 28)

    # --- B - Korbabmessungen ---------------------------------------------
    vs.CreateGroupBox(dlg, G_KORB, "Abmessungen Rigolenkoerper", True)
    vs.CreateStaticText(dlg, T_KORB_L, "Korblaenge [m]:", BREITE_LABEL)
    vs.CreateEditReal(dlg, E_KORB_L, 1, 0.80, BREITE_FELD)
    vs.CreateStaticText(dlg, T_KORB_B, "Korbbreite [m]:", BREITE_LABEL)
    vs.CreateEditReal(dlg, E_KORB_B, 1, 0.80, BREITE_FELD)
    vs.CreateStaticText(dlg, T_KORB_H, "Korbhoehe [m]:", BREITE_LABEL)
    vs.CreateEditReal(dlg, E_KORB_H, 1, 0.33, BREITE_FELD)
    vs.CreateCheckBox(dlg, C_SWAP,
                      "Koerbe quer stellen (Laenge <-> Breite tauschen)")
    vs.CreateStaticText(dlg, T_SYMBOL_INFO, " ", 46)

    # --- C - Anordnung ----------------------------------------------------
    vs.CreateGroupBox(dlg, G_ANORDNUNG, "Anordnung der Koerbe", True)
    vs.CreateStaticText(dlg, T_ANZ_B, "Koerbe nebeneinander (Y):",
                        BREITE_LABEL)
    vs.CreateEditInteger(dlg, E_ANZ_B, 3, BREITE_FELD)
    vs.CreateStaticText(dlg, T_ANZ_H, "Koerbe uebereinander (Z):",
                        BREITE_LABEL)
    vs.CreateEditInteger(dlg, E_ANZ_H, 2, BREITE_FELD)
    vs.CreateStaticText(dlg, T_MODUS, "Laengsrichtung ueber:", BREITE_LABEL)
    vs.CreatePullDownMenu(dlg, P_MODUS, 28)
    vs.CreateStaticText(dlg, T_ANZ_L, "Koerbe hintereinander (X):",
                        BREITE_LABEL)
    vs.CreateEditInteger(dlg, E_ANZ_L, 10, BREITE_FELD)
    vs.CreateStaticText(dlg, T_ZIEL_L, "gewuenschte Gesamtlaenge [m]:",
                        BREITE_LABEL)
    vs.CreateEditReal(dlg, E_ZIEL_L, 1, 8.00, BREITE_FELD)
    vs.CreateStaticText(dlg, T_RUNDUNG, "wenn nicht teilbar:", BREITE_LABEL)
    vs.CreatePullDownMenu(dlg, P_RUNDUNG, 20)

    # --- D - Eigenschaften ------------------------------------------------
    vs.CreateGroupBox(dlg, G_EIGENSCHAFTEN, "Eigenschaften", True)
    vs.CreateCheckBox(dlg, C_VERSCHWEISST, "Rigolenkoerper verschweisst")
    vs.CreateStaticText(dlg, T_KOEFF, "Speicherkoeffizient [%]:", BREITE_LABEL)
    vs.CreateEditReal(dlg, E_KOEFF, 1, 95.0, BREITE_FELD)
    vs.CreateStaticText(dlg, T_KLASSE, "Belastungsklasse:", BREITE_LABEL)
    vs.CreatePullDownMenu(dlg, P_KLASSE, 12)

    # --- S - Kontrollschaechte --------------------------------------------
    vs.CreateGroupBox(dlg, G_SCHACHT, "Kontrollschaechte", True)
    vs.CreateCheckBox(dlg, C_SCHACHT, "Kontrollschaechte setzen")
    vs.CreateStaticText(dlg, T_SCHACHT_DN, "Schacht:", BREITE_LABEL)
    vs.CreatePullDownMenu(dlg, P_SCHACHT_DN, 20)
    vs.CreateStaticText(dlg, T_SCHACHT_OK, "OK Schacht [m]:", BREITE_LABEL)
    vs.CreateEditReal(dlg, E_SCHACHT_OK, 1, kt.DEFAULT_SCHACHT_OK,
                      BREITE_FELD)
    vs.CreateStaticText(dlg, T_SCHACHT_INFO, " ", 46)

    # --- E - Hoehen -------------------------------------------------------
    vs.CreateGroupBox(dlg, G_HOEHEN, "Hoehenlage", True)
    vs.CreateStaticText(dlg, T_HBEZUG, "Hoehenbezug:", BREITE_LABEL)
    vs.CreatePullDownMenu(dlg, P_HBEZUG, 24)
    vs.CreateStaticText(dlg, T_HWERT, "Hoehe [m]:", BREITE_LABEL)
    vs.CreateEditReal(dlg, E_HWERT, 1, 43.25, BREITE_FELD)
    vs.CreateCheckBox(dlg, C_EBENENHOEHE, "Ebenenhoehe beruecksichtigen")

    # --- F - Darstellung --------------------------------------------------
    vs.CreateGroupBox(dlg, G_DARSTELLUNG, "Darstellung", True)
    vs.CreateCheckBox(dlg, C_2D, "2D-Darstellung erzeugen")
    vs.CreateCheckBox(dlg, C_3D, "3D-Darstellung erzeugen")

    # --- G - Beschriftung -------------------------------------------------
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

    # --- Ergebnisanzeige --------------------------------------------------
    vs.CreateGroupBox(dlg, G_ERGEBNIS, "Ergebnis", True)
    for item in (R_GESAMT, R_ANZAHL, R_VOLUMEN, R_SPEICHER, R_HOEHEN,
                 R_HINWEIS):
        vs.CreateStaticText(dlg, item, " ", 46)

    # --- linke Spalte -----------------------------------------------------
    vs.SetFirstLayoutItem(dlg, G_ART)
    vs.SetBelowItem(dlg, G_ART, G_KORB, 0, 0)
    vs.SetBelowItem(dlg, G_KORB, G_ANORDNUNG, 0, 0)
    vs.SetBelowItem(dlg, G_ANORDNUNG, G_EIGENSCHAFTEN, 0, 0)
    vs.SetBelowItem(dlg, G_EIGENSCHAFTEN, G_SCHACHT, 0, 0)

    # --- rechte Spalte ----------------------------------------------------
    vs.SetRightItem(dlg, G_ART, G_HOEHEN, 0, 0)
    vs.SetBelowItem(dlg, G_HOEHEN, G_DARSTELLUNG, 0, 0)
    vs.SetBelowItem(dlg, G_DARSTELLUNG, G_BESCHRIFTUNG, 0, 0)
    vs.SetBelowItem(dlg, G_BESCHRIFTUNG, G_ERGEBNIS, 0, 0)

    # --- Inhalt der Gruppen ----------------------------------------------
    vs.SetFirstGroupItem(dlg, G_ART, T_KORBTYP)
    vs.SetRightItem(dlg, T_KORBTYP, P_KORBTYP, 0, 0)
    vs.SetBelowItem(dlg, T_KORBTYP, T_SYSTEM_INFO, 0, 0)
    vs.SetBelowItem(dlg, T_SYSTEM_INFO, T_SYSTEM, 0, 0)
    vs.SetRightItem(dlg, T_SYSTEM, E_SYSTEM, 0, 0)

    vs.SetFirstGroupItem(dlg, G_KORB, T_KORB_L)
    vs.SetRightItem(dlg, T_KORB_L, E_KORB_L, 0, 0)
    vs.SetBelowItem(dlg, T_KORB_L, T_KORB_B, 0, 0)
    vs.SetRightItem(dlg, T_KORB_B, E_KORB_B, 0, 0)
    vs.SetBelowItem(dlg, T_KORB_B, T_KORB_H, 0, 0)
    vs.SetRightItem(dlg, T_KORB_H, E_KORB_H, 0, 0)
    vs.SetBelowItem(dlg, T_KORB_H, C_SWAP, 0, 0)
    vs.SetBelowItem(dlg, C_SWAP, T_SYMBOL_INFO, 0, 0)

    vs.SetFirstGroupItem(dlg, G_ANORDNUNG, T_ANZ_B)
    vs.SetRightItem(dlg, T_ANZ_B, E_ANZ_B, 0, 0)
    vs.SetBelowItem(dlg, T_ANZ_B, T_ANZ_H, 0, 0)
    vs.SetRightItem(dlg, T_ANZ_H, E_ANZ_H, 0, 0)
    vs.SetBelowItem(dlg, T_ANZ_H, T_MODUS, 0, 0)
    vs.SetRightItem(dlg, T_MODUS, P_MODUS, 0, 0)
    vs.SetBelowItem(dlg, T_MODUS, T_ANZ_L, 0, 0)
    vs.SetRightItem(dlg, T_ANZ_L, E_ANZ_L, 0, 0)
    vs.SetBelowItem(dlg, T_ANZ_L, T_ZIEL_L, 0, 0)
    vs.SetRightItem(dlg, T_ZIEL_L, E_ZIEL_L, 0, 0)
    vs.SetBelowItem(dlg, T_ZIEL_L, T_RUNDUNG, 0, 0)
    vs.SetRightItem(dlg, T_RUNDUNG, P_RUNDUNG, 0, 0)

    vs.SetFirstGroupItem(dlg, G_EIGENSCHAFTEN, C_VERSCHWEISST)
    vs.SetBelowItem(dlg, C_VERSCHWEISST, T_KOEFF, 0, 0)
    vs.SetRightItem(dlg, T_KOEFF, E_KOEFF, 0, 0)
    vs.SetBelowItem(dlg, T_KOEFF, T_KLASSE, 0, 0)
    vs.SetRightItem(dlg, T_KLASSE, P_KLASSE, 0, 0)

    vs.SetFirstGroupItem(dlg, G_SCHACHT, C_SCHACHT)
    vs.SetBelowItem(dlg, C_SCHACHT, T_SCHACHT_DN, 0, 0)
    vs.SetRightItem(dlg, T_SCHACHT_DN, P_SCHACHT_DN, 0, 0)
    vs.SetBelowItem(dlg, T_SCHACHT_DN, T_SCHACHT_OK, 0, 0)
    vs.SetRightItem(dlg, T_SCHACHT_OK, E_SCHACHT_OK, 0, 0)
    vs.SetBelowItem(dlg, T_SCHACHT_OK, T_SCHACHT_INFO, 0, 0)

    vs.SetFirstGroupItem(dlg, G_HOEHEN, T_HBEZUG)
    vs.SetRightItem(dlg, T_HBEZUG, P_HBEZUG, 0, 0)
    vs.SetBelowItem(dlg, T_HBEZUG, T_HWERT, 0, 0)
    vs.SetRightItem(dlg, T_HWERT, E_HWERT, 0, 0)
    vs.SetBelowItem(dlg, T_HWERT, C_EBENENHOEHE, 0, 0)

    vs.SetFirstGroupItem(dlg, G_DARSTELLUNG, C_2D)
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
# Startwerte setzen  (nur im Ereignis 12255!)
# ---------------------------------------------------------------------------

def _setup(defaults):
    # Aufklappmenues fuellen - MUSS hier passieren, nicht beim Aufbau
    dl.fuelle(P_KORBTYP, bt.basket_type_names())
    dl.fuelle(P_MODUS, MODUS_TEXTE)
    dl.fuelle(P_RUNDUNG, RUNDUNG_TEXTE)
    dl.fuelle(P_KLASSE, LOAD_CLASSES)
    dl.fuelle(P_HBEZUG, HBEZUG_TEXTE)
    dl.fuelle(P_SCHACHT_DN, kt.schacht_namen())

    dl.setze_auswahl(P_KORBTYP, bt.basket_type_names(),
                     defaults.get("basket_key", bt.DEFAULT_BASKET_KEY))
    dl.setze_auswahl(P_MODUS, MODUS_WERTE,
                     defaults.get("length_mode", LENGTH_MODE_COUNT))
    dl.setze_auswahl(P_RUNDUNG, RUNDUNG_WERTE,
                     defaults.get("rounding", ROUND_UP))
    dl.setze_auswahl(P_KLASSE, LOAD_CLASSES,
                     defaults.get("load_class", DEFAULT_LOAD_CLASS))
    dl.setze_auswahl(P_HBEZUG, HBEZUG_WERTE,
                     defaults.get("height_mode", HEIGHT_MODE_OK))
    dl.setze_auswahl(P_SCHACHT_DN, kt.schacht_namen(),
                     defaults.get("schacht_dn", kt.DEFAULT_SCHACHT))

    dl.setze_text(E_SYSTEM, defaults.get("system_name", ""))
    dl.setze_text(E_KOMMENTAR, defaults.get("comment", ""))

    # Zahlenfelder - der defaultValue von CreateEditReal ist laut Referenz
    # unzuverlaessig, deshalb hier noch einmal ausdruecklich setzen.
    for item, schluessel, standard in (
            (E_KORB_L, "basket_length", 0.80),
            (E_KORB_B, "basket_width", 0.80),
            (E_KORB_H, "basket_height", 0.33),
            (E_ZIEL_L, "target_length", 8.00),
            (E_KOEFF, "storage_percent", 95.0),
            (E_HWERT, "height_value", 43.25),
            (E_LOFF_X, "label_offset_x", TEXT_OFFSET_X),
            (E_LOFF_Y, "label_offset_y", TEXT_OFFSET_Y),
            (E_SCHACHT_OK, "schacht_ok", kt.DEFAULT_SCHACHT_OK)):
        dl.setze_real(item, defaults.get(schluessel, standard))

    for item, schluessel, standard in (
            (E_ANZ_L, "count_length", 10),
            (E_ANZ_B, "count_width", 3),
            (E_ANZ_H, "count_height", 2)):
        dl.setze_ganzzahl(item, defaults.get(schluessel, standard))

    for item, schluessel, standard in (
            (C_VERSCHWEISST, "welded", False),
            (C_EBENENHOEHE, "use_layer_elevation", False),
            (C_2D, "draw_2d", True),
            (C_3D, "draw_3d", True),
            (C_LABEL, "create_label", True),
            (C_SWAP, "basket_swapped", False),
            (C_SCHACHT, "mit_schacht", True)):
        dl.setze_ja_nein(item, defaults.get(schluessel, standard))

    label_felder = defaults.get("label_fields") or {}
    for i, (schluessel, anzeige, standard) in enumerate(LABEL_FIELDS):
        dl.setze_ja_nein(LABEL_CHECK_BASE + i,
                         bool(label_felder.get(schluessel, standard)))

    # Bei einem VORDEFINIERTEN Korbtyp gewinnt immer die Konfiguration.
    # Sonst kann der Fall auftreten, dass im Aufklappmenue ein Typ steht,
    # die Massfelder darunter aber zu einem anderen Typ gehoeren - genau das
    # ist in Pruefbericht D im zweiten Lauf passiert.
    korbtyp = dl.auswahl(P_KORBTYP, bt.basket_type_names(),
                         bt.DEFAULT_BASKET_KEY)
    if not bt.is_custom(korbtyp):
        _uebernehme_korbtyp()
        # Der Speicherkoeffizient aus dem Korbtyp ist laut Anforderung 27 nur
        # ein Vorschlag - ein zuletzt abweichend eingegebener Wert bleibt
        # deshalb erhalten.
        gespeichert = defaults.get("storage_percent")
        if gespeichert is not None:
            dl.setze_real(E_KOEFF, gespeichert)

    dl.hilfetext(C_SCHACHT,
                 "Kontrollschaechte sitzen mittig auf der Oberkante eines "
                 "Rigolenkorbes, am Anfang und Ende einer Reihe. 1-2 Reihen: "
                 "Reihe 1. 3-5 Reihen: Reihe 2. Ab 6 Reihen: Reihe 2 und "
                 "vorletzte Reihe.")
    dl.hilfetext(E_SCHACHT_OK,
                 "Absolute Hoehenkote der Schachtoberkante. Die Unterkante "
                 "ist die Oberkante der Rigole - der Schacht sitzt auf dem "
                 "Korb.")
    dl.hilfetext(P_KLASSE,
                 "Reine Planungsangabe nach DIN EN 1433 / DIN EN 124. Es "
                 "findet keine statische Bemessung statt.")
    dl.hilfetext(E_KOEFF,
                 "Anteil des Bruttovolumens, der tatsaechlich Wasser "
                 "aufnimmt. Groesser 0 % und hoechstens 100 %.")
    dl.hilfetext(C_SWAP,
                 "Dreht die Koerbe um 90 Grad: Korblaenge und Korbbreite "
                 "werden vertauscht. Die Hoehe bleibt unveraendert.")
    dl.hilfetext(E_LOFF_X,
                 "Abstand der Beschriftung von der rechten bzw. oberen Kante "
                 "der Rigole. Der Text ist danach ein normales Textobjekt und "
                 "laesst sich frei verschieben.")


# ---------------------------------------------------------------------------
# Infozeilen, Zustaende, Vorbelegungen
# ---------------------------------------------------------------------------

def _aktueller_symbolname():
    """
    Symbolname zum gerade eingestellten Korbtyp.
    Bei benutzerdefinierten Massen ergibt er sich aus den Eingabefeldern.
    """
    korbtyp = dl.auswahl(P_KORBTYP, bt.basket_type_names(),
                         bt.DEFAULT_BASKET_KEY)
    return bt.symbol_for(korbtyp,
                         dl.real(E_KORB_L, 0.0),
                         dl.real(E_KORB_B, 0.0),
                         dl.real(E_KORB_H, 0.0))


def _system_info_text():
    """
    Zeigt die Elementmasse des gewaehlten Systems an - und sagt dazu, dass
    die Masse eine Vorgabe und kein Herstellernachweis sind.
    """
    korbtyp = dl.auswahl(P_KORBTYP, bt.basket_type_names(),
                         bt.DEFAULT_BASKET_KEY)
    if bt.is_custom(korbtyp):
        return u"Masse frei eingeben"
    daten = bt.get_basket_type(korbtyp) or {}
    return u"Element: %s x %s x %s mm" % (
        int(round(float(daten.get("length", 0.0)) * 1000.0)),
        int(round(float(daten.get("width", 0.0)) * 1000.0)),
        int(round(float(daten.get("height", 0.0)) * 1000.0)))


def _symbol_info_text():
    """
    Zeigt an, welches Symbol verwendet wird und ob es schon im Dokument liegt.
    Fehlt es, erzeugt das Werkzeug es selbst - das steht auch so da, damit
    niemand nach einem Symbol sucht, das er gar nicht braucht.
    """
    symbol = _aktueller_symbolname()
    if not symbol:
        return u"Symbol: — (Abmessungen unvollstaendig)"
    if Z.symbolnamen and symbol in Z.symbolnamen:
        return u"Symbol: %s   (im Dokument vorhanden)" % (symbol,)
    return u"Symbol: %s   (wird automatisch erzeugt)" % (symbol,)


def _schacht_info_text():
    """Gegenprobe: auf welchen Reihen sitzen die Schaechte, und wie viele?"""
    reihen = dl.ganzzahl(E_ANZ_B, 0)
    if reihen < 1:
        return u"—"

    indizes = calc.korb_schacht_reihen(reihen)
    if not indizes:
        return u"—"

    schacht = dl.auswahl(P_SCHACHT_DN, kt.schacht_namen(), kt.DEFAULT_SCHACHT)
    anzahl = len(indizes) * (1 if dl.ganzzahl(E_ANZ_L, 0) <= 1 else 2)
    return u"%d x %s, mittig auf Reihe %s (Anfang und Ende)" % (
        anzahl, schacht, u" und ".join(str(i + 1) for i in indizes))


def _aktualisiere_zustaende():
    korbtyp = dl.auswahl(P_KORBTYP, bt.basket_type_names(),
                         bt.DEFAULT_BASKET_KEY)
    benutzerdefiniert = bt.is_custom(korbtyp)
    for item in (E_KORB_L, E_KORB_B, E_KORB_H):
        dl.aktiv(item, benutzerdefiniert)

    dl.setze_text(T_SYMBOL_INFO, _symbol_info_text())
    dl.setze_text(T_SYSTEM_INFO, _system_info_text())

    modus = dl.auswahl(P_MODUS, MODUS_WERTE, LENGTH_MODE_COUNT)
    modus_anzahl = (modus == LENGTH_MODE_COUNT)
    dl.aktiv(E_ANZ_L, modus_anzahl)
    dl.aktiv(E_ZIEL_L, not modus_anzahl)
    dl.aktiv(P_RUNDUNG, not modus_anzahl)

    schacht_an = dl.ja_nein(C_SCHACHT, True)
    dl.aktiv(P_SCHACHT_DN, schacht_an)
    dl.aktiv(E_SCHACHT_OK, schacht_an)
    dl.setze_text(T_SCHACHT_INFO,
                  _schacht_info_text() if schacht_an else u"—")

    label_an = dl.ja_nein(C_LABEL, True)
    dl.aktiv(E_LOFF_X, label_an)
    dl.aktiv(E_LOFF_Y, label_an)
    # Zeilen, die es hier nicht gibt, sind gesperrt. (Die Textausgabe laesst
    # sie ohnehin weg - hier ist es nur sichtbar.)
    for i, (schluessel, anzeige, standard) in enumerate(LABEL_FIELDS):
        dl.aktiv(LABEL_CHECK_BASE + i,
                 label_an and schluessel not in NUR_KIES)


def _tausche_masse():
    """
    Vertauscht Korblaenge und Korbbreite in den Eingabefeldern.

    Bewusst werden die Werte SELBST getauscht und nicht nur ein Merker
    gesetzt: So zeigen die Felder immer genau die Masse, mit denen auch
    gebaut wird - und die Ergebnisanzeige darunter passt dazu.
    """
    laenge = dl.real(E_KORB_L, 0.0)
    breite = dl.real(E_KORB_B, 0.0)
    neue_laenge, neue_breite = calc.apply_orientation(laenge, breite, True)
    dl.setze_real(E_KORB_L, neue_laenge)
    dl.setze_real(E_KORB_B, neue_breite)


def _uebernehme_korbtyp():
    """
    Bei Wechsel des Korbtyps die Masse vorbelegen.
    Steht der Umschalter auf quer, gilt er auch fuer den neuen Korbtyp.
    """
    korbtyp = dl.auswahl(P_KORBTYP, bt.basket_type_names(),
                         bt.DEFAULT_BASKET_KEY)
    if bt.is_custom(korbtyp):
        return
    daten = bt.get_basket_type(korbtyp)
    if not daten:
        return

    laenge, breite = calc.apply_orientation(
        daten["length"], daten["width"], dl.ja_nein(C_SWAP, False))
    dl.setze_real(E_KORB_L, float(laenge))
    dl.setze_real(E_KORB_B, float(breite))
    dl.setze_real(E_KORB_H, float(daten["height"]))
    dl.setze_real(E_KOEFF,
                  float(daten.get("storage_coefficient", 0.95)) * 100.0)


# ---------------------------------------------------------------------------
# Werte einsammeln  (nur INNERHALB des Handlers!)
# ---------------------------------------------------------------------------

def _lies_alles():
    werte = {}
    werte["system_name"] = dl.text(E_SYSTEM, "")
    werte["basket_key"] = dl.auswahl(P_KORBTYP, bt.basket_type_names(),
                                     bt.DEFAULT_BASKET_KEY)
    # Seit 0.17.0 ist die Rigolenart die gewaehlte Hersteller-/
    # Systembezeichnung. Der Datensatz und die Beschriftung bekommen
    # damit die Angabe, die im Plan wirklich interessiert.
    werte["rigole_type"] = werte["basket_key"]
    # Die Felder enthalten bereits die EFFEKTIVEN Masse: der Umschalter
    # "quer stellen" vertauscht Laenge und Breite direkt in den Feldern.
    werte["basket_length"] = dl.real(E_KORB_L, 0.0)
    werte["basket_width"] = dl.real(E_KORB_B, 0.0)
    werte["basket_height"] = dl.real(E_KORB_H, 0.0)
    werte["basket_swapped"] = dl.ja_nein(C_SWAP, False)

    werte["count_width"] = dl.ganzzahl(E_ANZ_B, 0)
    werte["count_height"] = dl.ganzzahl(E_ANZ_H, 0)
    werte["length_mode"] = dl.auswahl(P_MODUS, MODUS_WERTE, LENGTH_MODE_COUNT)
    werte["count_length"] = dl.ganzzahl(E_ANZ_L, 0)
    werte["target_length"] = dl.real(E_ZIEL_L, 0.0)
    werte["rounding"] = dl.auswahl(P_RUNDUNG, RUNDUNG_WERTE, ROUND_UP)

    werte["welded"] = dl.ja_nein(C_VERSCHWEISST, False)
    werte["storage_percent"] = dl.real(E_KOEFF, 0.0)
    werte["load_class"] = dl.auswahl(P_KLASSE, LOAD_CLASSES,
                                     DEFAULT_LOAD_CLASS)

    werte["height_mode"] = dl.auswahl(P_HBEZUG, HBEZUG_WERTE, HEIGHT_MODE_OK)
    werte["height_value"] = dl.real(E_HWERT, 0.0)
    werte["use_layer_elevation"] = dl.ja_nein(C_EBENENHOEHE, False)

    # Symbol und Einfuegepunkt ergeben sich aus dem Korbtyp bzw. den
    # eingegebenen Massen - sie werden nicht mehr im Dialog ausgewaehlt.
    # Damit koennen Groesse und Symbol nicht mehr auseinanderlaufen.
    werte["symbol_name"] = bt.symbol_for(werte["basket_key"],
                                         werte["basket_length"],
                                         werte["basket_width"],
                                         werte["basket_height"])
    werte["symbol_anchor"] = bt.anchor_for(werte["basket_key"])
    # Fehlt das Symbol, erzeugt das Werkzeug es selbst - das ist also kein
    # Fehlerfall. Die Pruefung greift nur, wenn kein Name gebildet werden
    # konnte.
    werte["symbol_exists"] = None

    werte["mit_schacht"] = dl.ja_nein(C_SCHACHT, True)
    werte["schacht_dn"] = dl.auswahl(P_SCHACHT_DN, kt.schacht_namen(),
                                     kt.DEFAULT_SCHACHT)
    werte["schacht_durchmesser"] = kt.schacht_durchmesser(werte["schacht_dn"])
    werte["schacht_ok"] = dl.real(E_SCHACHT_OK, kt.DEFAULT_SCHACHT_OK)

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


def aufloesen_laengsrichtung(werte):
    """
    Bestimmt die endgueltige Korbanzahl in Laengsrichtung und ergaenzt
    'count_length', 'actual_length' und 'length_exact' im Wertedictionary.

    Es wird NICHT stillschweigend gerundet: Modus B benutzt ausdruecklich
    die im Dialog gewaehlte Rundungsart, und das Ergebnis wird angezeigt.
    """
    if werte.get("length_mode") != LENGTH_MODE_TOTAL:
        n = int(werte.get("count_length") or 0)
        bl = float(werte.get("basket_length") or 0.0)
        werte["actual_length"] = n * bl
        werte["length_exact"] = True
        return werte

    try:
        n, laenge, exakt = calc.calculate_basket_count(
            werte.get("target_length"), werte.get("basket_length"),
            werte.get("rounding", ROUND_UP))
    except Exception:
        werte["actual_length"] = 0.0
        werte["length_exact"] = True
        return werte

    werte["count_length"] = n
    werte["actual_length"] = laenge
    werte["length_exact"] = exakt
    return werte


def berechne(werte):
    """RigoleResult aus den Dialogwerten - auch vom Werkzeug benutzt."""
    return calc.compute_rigole(
        werte["basket_length"], werte["basket_width"], werte["basket_height"],
        werte["count_length"], werte["count_width"], werte["count_height"],
        calc.percent_to_factor(werte["storage_percent"]),
        werte["height_mode"], werte["height_value"],
        mit_schacht=werte.get("mit_schacht", False),
        schacht_dn=werte.get("schacht_dn", ""),
        schacht_durchmesser=werte.get("schacht_durchmesser", 0.0),
        schacht_ok=werte.get("schacht_ok"))


# ---------------------------------------------------------------------------
# Ergebnisanzeige
# ---------------------------------------------------------------------------

def _aktualisiere_ergebnis():
    werte = aufloesen_laengsrichtung(_lies_alles())

    hinweis = ""
    try:
        if (werte["basket_length"] <= 0 or werte["basket_width"] <= 0
                or werte["basket_height"] <= 0
                or werte["count_length"] < 1 or werte["count_width"] < 1
                or werte["count_height"] < 1):
            raise ValueError("unvollstaendig")

        ergebnis = berechne(werte)

        dl.setze_text(R_GESAMT, "Gesamtmasse: " + fmt.fmt_triple(
            ergebnis.total_length, ergebnis.total_width,
            ergebnis.total_height))
        anzahl_text = "Anzahl Koerbe: %s  (%s)" % (
            ergebnis.basket_count,
            fmt.fmt_arrangement(ergebnis.count_length, ergebnis.count_width,
                                ergebnis.count_height))
        if ergebnis.hat_schacht:
            anzahl_text += u"   |   %d Schaechte %s" % (
                ergebnis.schacht_anzahl, ergebnis.schacht_dn)
        dl.setze_text(R_ANZAHL, anzahl_text)
        dl.setze_text(R_VOLUMEN, "Bruttovolumen: " + fmt.fmt_volume(
            ergebnis.v_brutto, places=3))
        dl.setze_text(R_SPEICHER, "Speichervolumen: " + fmt.fmt_volume(
            ergebnis.v_speicher))
        dl.setze_text(R_HOEHEN, "OK %s   /   UK %s" % (
            fmt.fmt_height(ergebnis.ok), fmt.fmt_height(ergebnis.uk)))

        if (werte["length_mode"] == LENGTH_MODE_TOTAL
                and not werte["length_exact"]):
            hinweis = ("Hinweis: %s laesst sich mit einer Korblaenge von %s "
                       "nicht exakt herstellen. Erzeugt werden %d Koerbe = %s."
                       % (fmt.fmt_length(werte["target_length"]),
                          fmt.fmt_length(werte["basket_length"]),
                          werte["count_length"],
                          fmt.fmt_length(werte["actual_length"])))
    except Exception:
        for item in (R_GESAMT, R_ANZAHL, R_VOLUMEN, R_SPEICHER, R_HOEHEN):
            dl.setze_text(item, " ")
        hinweis = "Bitte alle Masse und Anzahlen ausfuellen."

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
            werte = aufloesen_laengsrichtung(_lies_alles())
            pruefung = validate_parameters(werte)
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

        # Irgendein Steuerelement wurde bedient
        if item == C_SWAP:
            _tausche_masse()
        elif item == P_KORBTYP:
            _uebernehme_korbtyp()
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

def show_dialog(defaults, symbolnamen):
    """
    Oeffnet den Einstellungsdialog.

    defaults      dict mit Vorgabewerten (aus settings.load_settings)
    symbolnamen   Liste der Symboldefinitionen im Dokument

    Rueckgabe: dict mit den Eingaben, oder None bei Abbruch.
    """
    return dl.starte(_baue_dialog, _handler, defaults, symbolnamen)


def default_values():
    """Werksvorgaben, falls noch nichts gespeichert wurde."""
    korb = bt.get_basket_type(bt.DEFAULT_BASKET_KEY) or {}
    return {
        "rigole_type": bt.DEFAULT_RIGOLE_TYPE,
        "system_name": "",
        "basket_key": bt.DEFAULT_BASKET_KEY,
        "basket_length": korb.get("length", 0.80),
        "basket_width": korb.get("width", 0.80),
        "basket_height": korb.get("height", 0.33),
        "basket_swapped": False,
        "count_width": 3,
        "count_height": 2,
        "length_mode": LENGTH_MODE_COUNT,
        "count_length": 10,
        "target_length": 8.00,
        "rounding": ROUND_UP,
        "welded": False,
        "storage_percent": korb.get("storage_coefficient", 0.95) * 100.0,
        "load_class": DEFAULT_LOAD_CLASS,
        "height_mode": HEIGHT_MODE_OK,
        "height_value": 43.25,
        "use_layer_elevation": False,
        "draw_2d": True,
        "draw_3d": True,
        "mit_schacht": True,
        "schacht_dn": kt.DEFAULT_SCHACHT,
        "schacht_ok": kt.DEFAULT_SCHACHT_OK,
        "create_label": True,
        "label_offset_x": TEXT_OFFSET_X,
        "label_offset_y": TEXT_OFFSET_Y,
        "label_fields": dict((k, d) for (k, _t, d) in LABEL_FIELDS),
        "comment": "",
    }
