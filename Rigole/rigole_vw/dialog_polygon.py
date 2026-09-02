# -*- coding: utf-8 -*-
"""
Einstellungsdialog des Werkzeugs "RIGOLE KOMPLEX" (26.08.2026).

Drittes Werkzeug, dritter Dialog. Der Unterschied zum Werkzeug "Rigole":
Laenge und Breite werden nicht eingegeben, sondern kommen aus dem
angeklickten Polygon. An ihre Stelle tritt die Frage, WIE das Korbraster in
dieses Polygon gelegt wird.

Der Dialog rechnet die Belegung waehrend der Eingabe mit und zeigt sofort,
wie viele Koerbe hineinpassen und wie gut die Flaeche ausgenutzt ist. Das
ist die eigentliche Entscheidungshilfe: ob sich ein anderer Korbtyp oder
eine andere Rasterrichtung lohnt, sieht man erst an dieser Zahl.

Erzeugt KEINE Geometrie. Liefert ein Wertedictionary oder None bei Abbruch.

Kompatibilitaet: Python 3.9.2 (Vectorworks 2026)
"""

import vs
import json

MANUFACTURER = "manufactured by Julian M."


def _dialog_title(title):
    return "%s | v%s | %s" % (str(title), TOOL_VERSION, MANUFACTURER)

from rigole_config import basket_types as bt
from rigole_config import kies_types as kt
from rigole_config.basket_types import LOAD_CLASSES, DEFAULT_LOAD_CLASS
from rigole_config.constants import (
    TOOL_VERSION,
    HEIGHT_MODE_OK, HEIGHT_MODE_UK,
    LABEL_FIELDS, TEXT_OFFSET_X, TEXT_OFFSET_Y,
    RASTER_SUCHSCHRITTE, POLY_MAX_KOERBE, POLY_SCHACHT_MITTE_AB,
    ART_POLYGON,          # noqa - bleibt fuer die Bauartkennung im Modul
)
from rigole_config.dialog_ids import (
    G_ART, T_SYSTEM, E_SYSTEM, T_SYSTEM_INFO,
    G_KORB, T_KORBTYP, P_KORBTYP,
    T_KORB_L, E_KORB_L, T_KORB_B, E_KORB_B, T_KORB_H, E_KORB_H,
    C_SWAP, T_SYMBOL_INFO,
    G_POLY, T_POLY_INFO, T_RASTER, P_RASTER, T_WINKEL, E_WINKEL,
    T_SUCHE, P_SUCHE, C_ZELLEN, T_POLY_HINWEIS,
    T_ANZ_H, E_ANZ_H,
    G_EIGENSCHAFTEN, C_VERSCHWEISST, T_KOEFF, E_KOEFF, T_KLASSE, P_KLASSE,
    G_HOEHEN, T_HBEZUG, P_HBEZUG, T_HWERT, E_HWERT, C_EBENENHOEHE,
    G_DARSTELLUNG, C_2D, C_3D,
    G_BESCHRIFTUNG, C_LABEL, T_LABEL_OFF, E_LOFF_X, E_LOFF_Y,
    T_KOMMENTAR, E_KOMMENTAR, LABEL_CHECK_BASE,
    G_ERGEBNIS, R_GESAMT, R_ANZAHL, R_VOLUMEN, R_SPEICHER, R_HOEHEN,
    R_HINWEIS, R_FLAECHE, R_RASTER,
    G_SCHACHT, C_SCHACHT, T_SCHACHT_DN, P_SCHACHT_DN,
    T_SCHACHT_OK, E_SCHACHT_OK, T_SCHACHT_INFO,
)
from rigole_core import calculations as calc
from rigole_core import formatting as fmt
from rigole_core import polygon as poly
from rigole_core.validation import validate_polygon_parameters
from rigole_vw import dlgutils as dl
from rigole_vw.dlgutils import (
    EV_SETUP, EV_CLOSE, EV_OK, EV_CANCEL, BREITE_LABEL, BREITE_FELD, Z,
)


# ---------------------------------------------------------------------------
# Auswahllisten
# ---------------------------------------------------------------------------
RASTER_TEXTE = ["an der laengsten Polygonkante", "an den Zeichnungsachsen",
                "eigener Winkel"]
RASTER_KANTE = "kante"
RASTER_ACHSEN = "achsen"
RASTER_WINKEL = "winkel"
RASTER_WERTE = [RASTER_KANTE, RASTER_ACHSEN, RASTER_WINKEL]

SUCHE_TEXTE = ["aus - Raster buendig an der Huellbox",
               "normal (4 x 4 Lagen)", "fein (8 x 8 Lagen)"]
SUCHE_WERTE = [1, 4, 8]

HBEZUG_TEXTE = ["Oberkante bekannt", "Unterkante bekannt"]
HBEZUG_WERTE = [HEIGHT_MODE_OK, HEIGHT_MODE_UK]

# Beschriftungszeilen, die es hier nicht gibt.
NICHT_HIER = ("material", "draenrohr")


# ---------------------------------------------------------------------------
# Dialogaufbau
# ---------------------------------------------------------------------------

def _baue_dialog():
    dlg = vs.CreateLayout(_dialog_title("PD Rigole – Komplexe Rigole"), False,
                          "Komplexe Rigole erzeugen", "Abbrechen")
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

    # --- P - Umgrenzung und Raster ---------------------------------------
    vs.CreateGroupBox(dlg, G_POLY, "Umgrenzung und Raster", True)
    vs.CreateStaticText(dlg, T_POLY_INFO, " ", 46)
    vs.CreateStaticText(dlg, T_RASTER, "Raster ausrichten:", BREITE_LABEL)
    vs.CreatePullDownMenu(dlg, P_RASTER, 28)
    vs.CreateStaticText(dlg, T_WINKEL, "Rasterwinkel [Grad]:", BREITE_LABEL)
    vs.CreateEditReal(dlg, E_WINKEL, 2, 0.0, BREITE_FELD)
    vs.CreateStaticText(dlg, T_SUCHE, "Beste Rasterlage suchen:",
                        BREITE_LABEL)
    vs.CreatePullDownMenu(dlg, P_SUCHE, 28)
    vs.CreateStaticText(dlg, T_ANZ_H, "Koerbe uebereinander (Z):",
                        BREITE_LABEL)
    vs.CreateEditInteger(dlg, E_ANZ_H, 2, BREITE_FELD)
    vs.CreateStaticText(dlg, T_POLY_HINWEIS, " ", 46)

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
    vs.CreateCheckBox(dlg, C_ZELLEN, "jeden Korbplatz im Plan zeichnen")

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
    for item in (R_ANZAHL, R_FLAECHE, R_RASTER, R_GESAMT, R_VOLUMEN,
                 R_SPEICHER, R_HOEHEN, R_HINWEIS):
        vs.CreateStaticText(dlg, item, " ", 46)

    # --- linke Spalte -----------------------------------------------------
    vs.SetFirstLayoutItem(dlg, G_ART)
    vs.SetBelowItem(dlg, G_ART, G_KORB, 0, 0)
    vs.SetBelowItem(dlg, G_KORB, G_POLY, 0, 0)
    vs.SetBelowItem(dlg, G_POLY, G_EIGENSCHAFTEN, 0, 0)
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

    vs.SetFirstGroupItem(dlg, G_POLY, T_POLY_INFO)
    vs.SetBelowItem(dlg, T_POLY_INFO, T_RASTER, 0, 0)
    vs.SetRightItem(dlg, T_RASTER, P_RASTER, 0, 0)
    vs.SetBelowItem(dlg, T_RASTER, T_WINKEL, 0, 0)
    vs.SetRightItem(dlg, T_WINKEL, E_WINKEL, 0, 0)
    vs.SetBelowItem(dlg, T_WINKEL, T_SUCHE, 0, 0)
    vs.SetRightItem(dlg, T_SUCHE, P_SUCHE, 0, 0)
    vs.SetBelowItem(dlg, T_SUCHE, T_ANZ_H, 0, 0)
    vs.SetRightItem(dlg, T_ANZ_H, E_ANZ_H, 0, 0)
    vs.SetBelowItem(dlg, T_ANZ_H, T_POLY_HINWEIS, 0, 0)

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
    vs.SetBelowItem(dlg, C_3D, C_ZELLEN, 0, 0)

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

    vs.SetFirstGroupItem(dlg, G_ERGEBNIS, R_ANZAHL)
    vs.SetBelowItem(dlg, R_ANZAHL, R_FLAECHE, 0, 0)
    vs.SetBelowItem(dlg, R_FLAECHE, R_RASTER, 0, 0)
    vs.SetBelowItem(dlg, R_RASTER, R_GESAMT, 0, 0)
    vs.SetBelowItem(dlg, R_GESAMT, R_VOLUMEN, 0, 0)
    vs.SetBelowItem(dlg, R_VOLUMEN, R_SPEICHER, 0, 0)
    vs.SetBelowItem(dlg, R_SPEICHER, R_HOEHEN, 0, 0)
    vs.SetBelowItem(dlg, R_HOEHEN, R_HINWEIS, 0, 0)

    return dlg


# ---------------------------------------------------------------------------
# Startwerte  (nur im Ereignis 12255!)
# ---------------------------------------------------------------------------

def _setup(defaults):
    dl.fuelle(P_KORBTYP, bt.basket_type_names())
    dl.fuelle(P_RASTER, RASTER_TEXTE)
    dl.fuelle(P_SUCHE, SUCHE_TEXTE)
    dl.fuelle(P_KLASSE, LOAD_CLASSES)
    dl.fuelle(P_HBEZUG, HBEZUG_TEXTE)
    dl.fuelle(P_SCHACHT_DN, kt.schacht_namen())

    dl.setze_auswahl(P_KORBTYP, bt.basket_type_names(),
                     defaults.get("basket_key", bt.DEFAULT_BASKET_KEY))
    dl.setze_auswahl(P_RASTER, RASTER_WERTE,
                     defaults.get("raster_modus", RASTER_KANTE))
    dl.setze_auswahl(P_SUCHE, SUCHE_WERTE,
                     defaults.get("raster_suche", RASTER_SUCHSCHRITTE))
    dl.setze_auswahl(P_KLASSE, LOAD_CLASSES,
                     defaults.get("load_class", DEFAULT_LOAD_CLASS))
    dl.setze_auswahl(P_HBEZUG, HBEZUG_WERTE,
                     defaults.get("height_mode", HEIGHT_MODE_OK))
    dl.setze_auswahl(P_SCHACHT_DN, kt.schacht_namen(),
                     defaults.get("schacht_dn", kt.DEFAULT_SCHACHT))

    dl.setze_text(E_SYSTEM, defaults.get("system_name", ""))
    dl.setze_text(E_KOMMENTAR, defaults.get("comment", ""))

    for item, schluessel, standard in (
            (E_KORB_L, "basket_length", 0.80),
            (E_KORB_B, "basket_width", 0.80),
            (E_KORB_H, "basket_height", 0.33),
            (E_WINKEL, "raster_winkel", 0.0),
            (E_KOEFF, "storage_percent", 95.0),
            (E_HWERT, "height_value", 43.25),
            (E_LOFF_X, "label_offset_x", TEXT_OFFSET_X),
            (E_LOFF_Y, "label_offset_y", TEXT_OFFSET_Y),
            (E_SCHACHT_OK, "schacht_ok", kt.DEFAULT_SCHACHT_OK)):
        dl.setze_real(item, defaults.get(schluessel, standard))

    dl.setze_ganzzahl(E_ANZ_H, defaults.get("count_height", 2))

    for item, schluessel, standard in (
            (C_VERSCHWEISST, "welded", False),
            (C_EBENENHOEHE, "use_layer_elevation", False),
            (C_2D, "draw_2d", True),
            (C_3D, "draw_3d", True),
            (C_ZELLEN, "zeige_zellen", True),
            (C_LABEL, "create_label", True),
            (C_SWAP, "basket_swapped", False),
            (C_SCHACHT, "mit_schacht", True)):
        dl.setze_ja_nein(item, defaults.get(schluessel, standard))

    label_felder = defaults.get("label_fields") or {}
    for i, (schluessel, anzeige, standard) in enumerate(LABEL_FIELDS):
        dl.setze_ja_nein(LABEL_CHECK_BASE + i,
                         bool(label_felder.get(schluessel, standard)))

    korbtyp = dl.auswahl(P_KORBTYP, bt.basket_type_names(),
                         bt.DEFAULT_BASKET_KEY)
    if not bt.is_custom(korbtyp):
        _uebernehme_korbtyp()
        gespeichert = defaults.get("storage_percent")
        if gespeichert is not None:
            dl.setze_real(E_KOEFF, gespeichert)

    dl.hilfetext(P_RASTER,
                 "Richtung des Korbrasters. „Laengste Polygonkante\" ist die "
                 "Regel - bei schraeg liegenden Rigolen passen so deutlich "
                 "mehr Koerbe hinein.")
    dl.hilfetext(P_SUCHE,
                 "Das Raster wird innerhalb einer Korbzelle verschoben und "
                 "die Lage mit den meisten Koerben genommen. Fein rechnet "
                 "laenger, findet aber gelegentlich eine Reihe mehr.")
    dl.hilfetext(C_ZELLEN,
                 "Zeichnet in der Draufsicht jeden belegten Korbplatz als "
                 "Rechteck. Bei sehr vielen Koerben wird darauf automatisch "
                 "verzichtet.")
    dl.hilfetext(C_SCHACHT,
                 "Die Schaechte sitzen mittig auf einem Korb, je einer am "
                 "Anfang und am Ende der laengsten belegten Reihe; ab %g m "
                 "Spannweite kommt einer in der Mitte dazu."
                 % (POLY_SCHACHT_MITTE_AB,))
    dl.hilfetext(E_SCHACHT_OK,
                 "Absolute Hoehenkote der Schachtoberkante. Die Unterkante "
                 "ist die Oberkante der Rigole.")
    dl.hilfetext(E_KOEFF,
                 "Anteil des Bruttovolumens, der tatsaechlich Wasser "
                 "aufnimmt. Groesser 0 % und hoechstens 100 %.")


# ---------------------------------------------------------------------------
# Zwischenstaende
# ---------------------------------------------------------------------------

def _aktueller_symbolname():
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
    symbol = _aktueller_symbolname()
    if not symbol:
        return u"Symbol: — (Abmessungen unvollstaendig)"
    if Z.symbolnamen and symbol in Z.symbolnamen:
        return u"Symbol: %s   (im Dokument vorhanden)" % (symbol,)
    return u"Symbol: %s   (wird automatisch erzeugt)" % (symbol,)


def _polygon_info_text():
    punkte = Z.polygon or []
    if len(punkte) < 3:
        return u"Umgrenzung: — (kein Polygon uebergeben)"
    _i, kante, winkel = poly.laengste_kante(punkte)
    return u"Umgrenzung: %d Ecken, %s Flaeche, laengste Kante %s bei %.1f Grad" % (
        len(punkte), fmt.fmt_area(poly.flaeche(punkte)),
        fmt.fmt_length(kante), winkel)


def _schacht_info_text(ergebnis):
    if ergebnis is None or not ergebnis.hat_schacht:
        return u"—"
    return u"%d x %s, mittig auf einem Korb" % (
        ergebnis.schacht_anzahl, ergebnis.schacht_dn)


def _aktualisiere_zustaende():
    korbtyp = dl.auswahl(P_KORBTYP, bt.basket_type_names(),
                         bt.DEFAULT_BASKET_KEY)
    benutzerdefiniert = bt.is_custom(korbtyp)
    for item in (E_KORB_L, E_KORB_B, E_KORB_H):
        dl.aktiv(item, benutzerdefiniert)

    dl.setze_text(T_SYMBOL_INFO, _symbol_info_text())
    dl.setze_text(T_SYSTEM_INFO, _system_info_text())
    dl.setze_text(T_POLY_INFO, _polygon_info_text())

    modus = dl.auswahl(P_RASTER, RASTER_WERTE, RASTER_KANTE)
    plan_locked = bool(Z.defaults.get("_plan_raster_locked"))
    dl.aktiv(P_RASTER, not plan_locked)
    dl.aktiv(E_WINKEL, modus == RASTER_WINKEL and not plan_locked)
    if plan_locked:
        dl.setze_text(T_RASTER, "Ausrichtung: Plan / Bestand")

    schacht_an = dl.ja_nein(C_SCHACHT, True)
    dl.aktiv(P_SCHACHT_DN, schacht_an)
    dl.aktiv(E_SCHACHT_OK, schacht_an)

    dl.aktiv(C_ZELLEN, dl.ja_nein(C_2D, True))

    label_an = dl.ja_nein(C_LABEL, True)
    dl.aktiv(E_LOFF_X, label_an)
    dl.aktiv(E_LOFF_Y, label_an)
    for i, (schluessel, anzeige, standard) in enumerate(LABEL_FIELDS):
        dl.aktiv(LABEL_CHECK_BASE + i,
                 label_an and schluessel not in NICHT_HIER)


def _tausche_masse():
    laenge = dl.real(E_KORB_L, 0.0)
    breite = dl.real(E_KORB_B, 0.0)
    neue_laenge, neue_breite = calc.apply_orientation(laenge, breite, True)
    dl.setze_real(E_KORB_L, neue_laenge)
    dl.setze_real(E_KORB_B, neue_breite)


def _uebernehme_korbtyp():
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
    werte["basket_length"] = dl.real(E_KORB_L, 0.0)
    werte["basket_width"] = dl.real(E_KORB_B, 0.0)
    werte["basket_height"] = dl.real(E_KORB_H, 0.0)
    werte["basket_swapped"] = dl.ja_nein(C_SWAP, False)

    werte["raster_modus"] = dl.auswahl(P_RASTER, RASTER_WERTE, RASTER_KANTE)
    werte["raster_winkel"] = dl.real(E_WINKEL, 0.0)
    if Z.defaults.get("_plan_raster_locked"):
        werte["raster_modus"] = RASTER_WINKEL
        werte["raster_winkel"] = float(Z.defaults["raster_winkel"])
    werte["raster_suche"] = dl.auswahl(P_SUCHE, SUCHE_WERTE,
                                       RASTER_SUCHSCHRITTE)
    werte["count_height"] = dl.ganzzahl(E_ANZ_H, 0)

    werte["welded"] = dl.ja_nein(C_VERSCHWEISST, False)
    werte["storage_percent"] = dl.real(E_KOEFF, 0.0)
    werte["load_class"] = dl.auswahl(P_KLASSE, LOAD_CLASSES,
                                     DEFAULT_LOAD_CLASS)

    werte["height_mode"] = dl.auswahl(P_HBEZUG, HBEZUG_WERTE, HEIGHT_MODE_OK)
    werte["height_value"] = dl.real(E_HWERT, 0.0)
    werte["use_layer_elevation"] = dl.ja_nein(C_EBENENHOEHE, False)

    werte["symbol_name"] = bt.symbol_for(werte["basket_key"],
                                         werte["basket_length"],
                                         werte["basket_width"],
                                         werte["basket_height"])
    werte["symbol_anchor"] = bt.anchor_for(werte["basket_key"])
    werte["symbol_exists"] = None

    werte["mit_schacht"] = dl.ja_nein(C_SCHACHT, True)
    werte["schacht_dn"] = dl.auswahl(P_SCHACHT_DN, kt.schacht_namen(),
                                     kt.DEFAULT_SCHACHT)
    werte["schacht_durchmesser"] = kt.schacht_durchmesser(werte["schacht_dn"])
    werte["schacht_ok"] = dl.real(E_SCHACHT_OK, kt.DEFAULT_SCHACHT_OK)

    werte["draw_2d"] = dl.ja_nein(C_2D, True)
    werte["draw_3d"] = dl.ja_nein(C_3D, True)
    werte["zeige_zellen"] = dl.ja_nein(C_ZELLEN, True)

    werte["create_label"] = dl.ja_nein(C_LABEL, True)
    werte["label_offset_x"] = dl.real(E_LOFF_X, TEXT_OFFSET_X)
    werte["label_offset_y"] = dl.real(E_LOFF_Y, TEXT_OFFSET_Y)
    label_felder = {}
    for i, (schluessel, anzeige, standard) in enumerate(LABEL_FIELDS):
        label_felder[schluessel] = dl.ja_nein(LABEL_CHECK_BASE + i, standard)
    werte["label_fields"] = label_felder
    werte["comment"] = dl.text(E_KOMMENTAR, "")
    werte["polygon"] = list(Z.polygon or [])
    return werte


# ---------------------------------------------------------------------------
# Rechnen
# ---------------------------------------------------------------------------

def raster_winkel_aus(werte):
    """
    Der zu verwendende Rasterwinkel - oder None, wenn er sich aus der
    laengsten Polygonkante ergeben soll.
    """
    modus = werte.get("raster_modus", RASTER_KANTE)
    if modus == RASTER_ACHSEN:
        return 0.0
    if modus == RASTER_WINKEL:
        return float(werte.get("raster_winkel") or 0.0)
    return None


def berechne(werte, punkte=None):
    """PolygonResult aus den Dialogwerten - auch vom Werkzeug benutzt."""
    ecken = punkte if punkte is not None else werte.get("polygon")
    return calc.compute_rigole_polygon(
        ecken,
        werte["basket_length"], werte["basket_width"], werte["basket_height"],
        werte["count_height"],
        calc.percent_to_factor(werte["storage_percent"]),
        werte["height_mode"], werte["height_value"],
        raster_winkel=raster_winkel_aus(werte),
        such_schritte=int(werte.get("raster_suche") or RASTER_SUCHSCHRITTE),
        mit_schacht=werte.get("mit_schacht", False),
        schacht_dn=werte.get("schacht_dn", ""),
        schacht_durchmesser=werte.get("schacht_durchmesser", 0.0),
        schacht_ok=werte.get("schacht_ok"),
        schacht_mitte_ab_laenge=POLY_SCHACHT_MITTE_AB)


# ---------------------------------------------------------------------------
# Ergebnisanzeige
# ---------------------------------------------------------------------------

_preview_key = None
_preview_result = None


def _preview(werte):
    global _preview_key, _preview_result
    keys = ("polygon", "basket_length", "basket_width", "basket_height",
            "count_height", "storage_percent", "height_mode", "height_value",
            "raster_modus", "raster_winkel", "raster_suche", "mit_schacht",
            "schacht_dn", "schacht_durchmesser", "schacht_ok")
    key = json.dumps({k: werte.get(k) for k in keys}, sort_keys=True)
    if key != _preview_key:
        result = berechne(werte)
        _preview_result, _preview_key = result, key
    return _preview_result


def _aktualisiere_ergebnis():
    werte = _lies_alles()
    hinweis = ""
    ergebnis = None
    try:
        if (werte["basket_length"] <= 0 or werte["basket_width"] <= 0
                or werte["basket_height"] <= 0 or werte["count_height"] < 1
                or len(werte.get("polygon") or []) < 3):
            raise ValueError("unvollstaendig")

        ergebnis = _preview(werte)

        dl.setze_text(R_ANZAHL, u"Koerbe: %d  (%d je Lage x %d Lagen)" % (
            ergebnis.basket_count, ergebnis.koerbe_je_lage,
            ergebnis.count_height))
        dl.setze_text(R_FLAECHE, u"Flaeche: %s Polygon, %s belegt  (%s)" % (
            fmt.fmt_area(ergebnis.polygon_flaeche),
            fmt.fmt_area(ergebnis.belegte_flaeche),
            fmt.fmt_percent(ergebnis.ausnutzung)))
        dl.setze_text(R_RASTER, u"Rasterwinkel: %.2f Grad" %
                      (ergebnis.raster_winkel,))
        dl.setze_text(R_GESAMT, u"Huellmass der Koerbe: " + fmt.fmt_triple(
            ergebnis.total_length, ergebnis.total_width,
            ergebnis.total_height))
        dl.setze_text(R_VOLUMEN, u"Bruttovolumen: " + fmt.fmt_volume(
            ergebnis.v_brutto, places=3))
        dl.setze_text(R_SPEICHER, u"Speichervolumen: " + fmt.fmt_volume(
            ergebnis.v_speicher))
        dl.setze_text(R_HOEHEN, u"OK %s   /   UK %s" % (
            fmt.fmt_height(ergebnis.ok), fmt.fmt_height(ergebnis.uk)))

        if ergebnis.koerbe_je_lage == 0:
            hinweis = (u"In diese Umgrenzung passt kein einziger ganzer "
                       u"Korb. Kleinere Koerbe waehlen oder das Polygon "
                       u"vergroessern.")
        elif ergebnis.basket_count > POLY_MAX_KOERBE:
            hinweis = (u"Hinweis: %d Koerbe. Das Erzeugen dauert und macht "
                       u"die Datei gross." % (ergebnis.basket_count,))
    except Exception as error:
        for item in (R_ANZAHL, R_FLAECHE, R_RASTER, R_GESAMT, R_VOLUMEN,
                     R_SPEICHER, R_HOEHEN):
            dl.setze_text(item, " ")
        hinweis = u"Keine Vorschau: " + str(error)

    dl.setze_text(T_SCHACHT_INFO,
                  _schacht_info_text(ergebnis)
                  if dl.ja_nein(C_SCHACHT, True) else u"—")
    dl.setze_text(T_POLY_HINWEIS, u" ")
    dl.setze_text(R_HINWEIS, hinweis if hinweis else u" ")


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
            werte = _lies_alles()
            pruefung = validate_polygon_parameters(werte)
            if not pruefung.ok:
                vs.AlrtDialog(pruefung.message_text(include_warnings=False))
                return -1
            if pruefung.warnings:
                text = pruefung.message_text()
                if not vs.YNDialog(text + "\n\nTrotzdem fortfahren?"):
                    return -1
            Z.werte = werte
            Z.abgebrochen = False
            return item

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
        return -1 if item == EV_OK else item


# ---------------------------------------------------------------------------
# Oeffentliche Schnittstelle
# ---------------------------------------------------------------------------

def show_dialog(defaults, symbolnamen, polygon):
    """
    Oeffnet den Einstellungsdialog.

    polygon   Eckpunkte der Umgrenzung in Metern - Grundlage der Vorschau.

    Rueckgabe: dict mit den Eingaben, oder None bei Abbruch.
    """
    return dl.starte(_baue_dialog, _handler, defaults, symbolnamen,
                     polygon=polygon)


def default_values():
    korb = bt.get_basket_type(bt.DEFAULT_BASKET_KEY) or {}
    return {
        "rigole_type": bt.DEFAULT_BASKET_KEY,
        "system_name": "",
        "basket_key": bt.DEFAULT_BASKET_KEY,
        "basket_length": korb.get("length", 0.80),
        "basket_width": korb.get("width", 0.80),
        "basket_height": korb.get("height", 0.33),
        "basket_swapped": False,
        "count_height": 2,
        "raster_modus": RASTER_KANTE,
        "raster_winkel": 0.0,
        "raster_suche": RASTER_SUCHSCHRITTE,
        "welded": False,
        "storage_percent": korb.get("storage_coefficient", 0.95) * 100.0,
        "load_class": DEFAULT_LOAD_CLASS,
        "height_mode": HEIGHT_MODE_OK,
        "height_value": 43.25,
        "use_layer_elevation": False,
        "draw_2d": True,
        "draw_3d": True,
        "zeige_zellen": True,
        "mit_schacht": True,
        "schacht_dn": kt.DEFAULT_SCHACHT,
        "schacht_ok": kt.DEFAULT_SCHACHT_OK,
        "create_label": True,
        "label_offset_x": TEXT_OFFSET_X,
        "label_offset_y": TEXT_OFFSET_Y,
        "label_fields": dict((k, d) for (k, _t, d) in LABEL_FIELDS),
        "comment": "",
    }
