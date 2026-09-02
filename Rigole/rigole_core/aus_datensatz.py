# -*- coding: utf-8 -*-
"""
Datensatz zurueck in Dialogwerte - Grundlage des Modus "Vorhandenes
bearbeiten" (24.08.2026).

Kein "import vs" -> ausserhalb von Vectorworks testbar.

WARUM DAS UEBERHAUPT GEHT
-------------------------
Der Datensatz an der Symbolinstanz enthaelt seit jeher ALLE Eingabewerte -
das war beim Entwurf Absicht. Zum Bearbeiten muss deshalb nichts geraten
werden: die Felder werden gelesen und in genau das Wertedictionary
zurueckuebersetzt, das Dialog, Berechnung und Bauteil ohnehin verwenden.

WAS DER DATENSATZ NICHT WEISS
-----------------------------
Ein paar Angaben sind reine Bedienentscheidungen und werden bewusst nicht
gespeichert: ob 2D und/oder 3D erzeugt wurde, der Versatz der Beschriftung,
welche Beschriftungszeilen angekreuzt waren, der Rechenweg in Laengsrichtung
(Anzahl oder Zielmass) und die Rundungsart.

Fuer diese Werte gilt: die zuletzt gespeicherten Einstellungen sind die
Vorgabe, der Datensatz gewinnt ueberall dort, wo er etwas zu sagen hat.
Deshalb nehmen beide Funktionen ein 'vorgaben'-dict entgegen und
ueberschreiben nur, was sie wirklich wissen.

Kompatibilitaet: Python 3.9.2 (Vectorworks 2026)
"""

from rigole_config import basket_types as bt
from rigole_config import kies_types as kt
from rigole_config.constants import (
    HEIGHT_MODE_OK, HEIGHT_MODE_UK, LENGTH_MODE_COUNT,
    ART_KIESRIGOLE,
    FIELD_ID, FIELD_ART, FIELD_SYSTEM,
    FIELD_KORB_L, FIELD_KORB_B, FIELD_KORB_H,
    FIELD_ANZ_L, FIELD_ANZ_B, FIELD_ANZ_H,
    FIELD_VERSCHWEISST, FIELD_KOEFF,
    FIELD_HOEHENBEZUG, FIELD_OK, FIELD_UK,
    FIELD_BELASTUNG, FIELD_KOMMENTAR,
    FIELD_SCHACHT_DN, FIELD_SCHACHT_ANZ, FIELD_SCHACHT_OK,
    KFIELD_ID, KFIELD_SYSTEM,
    KFIELD_LAENGE, KFIELD_BREITE, KFIELD_HOEHE,
    KFIELD_MATERIAL, KFIELD_KOEFF,
    KFIELD_ROHR_DN, KFIELD_ROHR_UK,
    KFIELD_HOEHENBEZUG, KFIELD_OK, KFIELD_UK,
    KFIELD_BELASTUNG, KFIELD_KOMMENTAR,
    KFIELD_SCHACHT_DN, KFIELD_SCHACHT_ANZ, KFIELD_SCHACHT_OK,
    ART_POLYGON, RASTER_SUCHSCHRITTE,
    PFIELD_ID, PFIELD_ART, PFIELD_SYSTEM,
    PFIELD_KORB_L, PFIELD_KORB_B, PFIELD_KORB_H,
    PFIELD_ANZ_HOEHE, PFIELD_WINKEL, PFIELD_UMGRENZUNG,
    PFIELD_VERSCHWEISST, PFIELD_KOEFF,
    PFIELD_HOEHENBEZUG, PFIELD_OK, PFIELD_UK,
    PFIELD_BELASTUNG, PFIELD_KOMMENTAR,
    PFIELD_SCHACHT_DN, PFIELD_SCHACHT_ANZ, PFIELD_SCHACHT_OK,
)


LAENGEN_TOLERANZ = 0.001        # m, zum Wiedererkennen eines Korbtyps


# ---------------------------------------------------------------------------
# Umwandlung der Datensatztexte
# ---------------------------------------------------------------------------
# vs.GetRField liefert IMMER Text, auch bei Zahlenfeldern. Je nach
# Spracheinstellung kann darin ein Komma als Dezimaltrennzeichen stehen -
# deshalb wird beides akzeptiert.

def zahl(text, standard=None):
    try:
        return float(str(text).strip().replace(",", "."))
    except (TypeError, ValueError, AttributeError):
        return standard


def ganzzahl(text, standard=None):
    wert = zahl(text)
    if wert is None:
        return standard
    try:
        return int(round(wert))
    except (TypeError, ValueError):
        return standard


def ja_nein(text, standard=False):
    s = str(text or "").strip().upper()
    if s in ("TRUE", "WAHR", "1", "JA", "YES", "T"):
        return True
    if s in ("FALSE", "FALSCH", "0", "NEIN", "NO", "F"):
        return False
    return standard


def text_wert(wert, standard=""):
    s = str(wert or "").strip()
    return s if s else standard


# ---------------------------------------------------------------------------
# Hilfen
# ---------------------------------------------------------------------------

def _hoehenwert(felder, feld_bezug, feld_ok, feld_uk, standard=0.0):
    """
    Der Dialog kennt Bezug + EINEN Wert, der Datensatz beide Koten.
    Zurueck kommt der Wert, der zum gespeicherten Bezug gehoert.
    """
    bezug = text_wert(felder.get(feld_bezug), HEIGHT_MODE_OK).upper()
    if bezug not in (HEIGHT_MODE_OK, HEIGHT_MODE_UK):
        bezug = HEIGHT_MODE_OK
    quelle = feld_ok if bezug == HEIGHT_MODE_OK else feld_uk
    return bezug, zahl(felder.get(quelle), standard)


def _korbtyp_erkennen(laenge, breite, hoehe, gespeicherte_art=None):
    """
    Findet den Eintrag der Auswahlliste "Hersteller / System" zu einer
    vorhandenen Rigole.

    ZUERST wird der im Datensatz gespeicherte Text genommen (Feld
    "Rigolenart"). Seit 0.17.0 steht dort genau der Auswahltext, und das ist
    die einzige verlaessliche Angabe: Mehrere Systeme haben DIESELBEN
    Elementmasse (800 x 800 x 660 mm gibt es dreimal). Ueber die Masse
    allein liesse sich der Hersteller nicht zurueckgewinnen - die Rigole
    haette nach dem Bearbeiten plotzlich einen anderen Hersteller im
    Datensatz.

    Erst wenn der Text nicht (mehr) in der Liste steht - etwa bei einer
    Rigole aus einem aelteren Programmstand mit "Rigolenkoerper" - wird
    ueber die Masse gesucht. Wird auch dort nichts gefunden, kommt der
    Eintrag fuer benutzerdefinierte Abmessungen zurueck; dann bleiben die
    Massfelder im Dialog bedienbar.
    """
    art = str(gespeicherte_art or "").strip()
    if art and bt.ist_bekanntes_system(art):
        return art

    if None in (laenge, breite, hoehe):
        return bt.CUSTOM_BASKET_KEY
    for key in bt.basket_type_names():
        if bt.is_custom(key):
            continue
        daten = bt.get_basket_type(key) or {}
        masse = (daten.get("length"), daten.get("width"), daten.get("height"))
        if None in masse:
            continue
        # Auch quer gestellte Koerbe erkennen: Laenge und Breite duerfen
        # vertauscht sein, die Hoehe nicht.
        passt_laengs = (abs(masse[0] - laenge) <= LAENGEN_TOLERANZ
                        and abs(masse[1] - breite) <= LAENGEN_TOLERANZ)
        passt_quer = (abs(masse[1] - laenge) <= LAENGEN_TOLERANZ
                      and abs(masse[0] - breite) <= LAENGEN_TOLERANZ)
        if (passt_laengs or passt_quer) \
                and abs(masse[2] - hoehe) <= LAENGEN_TOLERANZ:
            return key
    return bt.CUSTOM_BASKET_KEY


def _schacht(felder, feld_dn, feld_anzahl, feld_ok, schacht_namen,
             standard_dn, standard_ok):
    """Schachtangaben; 0 Stueck bzw. leere Nennweite heisst 'ohne'."""
    dn = text_wert(felder.get(feld_dn))
    anzahl = ganzzahl(felder.get(feld_anzahl), 0) or 0
    mit = bool(dn) and dn in schacht_namen and anzahl > 0
    return {
        "mit_schacht": mit,
        "dn": dn if dn in schacht_namen else standard_dn,
        "ok": zahl(felder.get(feld_ok), standard_ok),
    }


# ---------------------------------------------------------------------------
# Koerbe-Rigole
# ---------------------------------------------------------------------------

def werte_aus_rigole_record(felder, vorgaben=None):
    """
    Baut aus den Feldern von DB_Rigole das Wertedictionary des Dialogs.

    felder    dict {Feldname: Text}, so wie vs.GetRField es liefert
    vorgaben  zuletzt gespeicherte Einstellungen; sie fuellen alles auf,
              was der Datensatz nicht weiss

    Rueckgabe: (werte, rigole_id)
    """
    werte = dict(vorgaben or {})

    werte["rigole_type"] = text_wert(felder.get(FIELD_ART),
                                     werte.get("rigole_type",
                                               bt.DEFAULT_RIGOLE_TYPE))
    werte["system_name"] = text_wert(felder.get(FIELD_SYSTEM),
                                     werte.get("system_name", ""))
    werte["comment"] = text_wert(felder.get(FIELD_KOMMENTAR), "")

    laenge = zahl(felder.get(FIELD_KORB_L))
    breite = zahl(felder.get(FIELD_KORB_B))
    hoehe = zahl(felder.get(FIELD_KORB_H))
    if laenge is not None:
        werte["basket_length"] = laenge
    if breite is not None:
        werte["basket_width"] = breite
    if hoehe is not None:
        werte["basket_height"] = hoehe
    werte["basket_key"] = _korbtyp_erkennen(laenge, breite, hoehe,
                                            werte.get("rigole_type"))
    # Der Umschalter "quer stellen" ist nur ein Bedienhilfsmittel - die
    # Massfelder enthalten bereits die effektiven Werte.
    werte["basket_swapped"] = False

    for feld, schluessel in ((FIELD_ANZ_L, "count_length"),
                             (FIELD_ANZ_B, "count_width"),
                             (FIELD_ANZ_H, "count_height")):
        anzahl = ganzzahl(felder.get(feld))
        if anzahl is not None:
            werte[schluessel] = anzahl

    # Die Anzahl steht fest - der Weg ueber ein Zielmass waere beim
    # Bearbeiten nur verwirrend.
    werte["length_mode"] = LENGTH_MODE_COUNT

    werte["welded"] = ja_nein(felder.get(FIELD_VERSCHWEISST),
                              bool(werte.get("welded", False)))
    koeff = zahl(felder.get(FIELD_KOEFF))
    if koeff is not None:
        werte["storage_percent"] = koeff * 100.0
    werte["load_class"] = text_wert(felder.get(FIELD_BELASTUNG),
                                    werte.get("load_class", ""))

    bezug, hoehenwert = _hoehenwert(felder, FIELD_HOEHENBEZUG,
                                    FIELD_OK, FIELD_UK,
                                    werte.get("height_value", 0.0))
    werte["height_mode"] = bezug
    werte["height_value"] = hoehenwert

    schacht = _schacht(felder, FIELD_SCHACHT_DN, FIELD_SCHACHT_ANZ,
                       FIELD_SCHACHT_OK, kt.schacht_namen(),
                       werte.get("schacht_dn", kt.DEFAULT_SCHACHT),
                       werte.get("schacht_ok", kt.DEFAULT_SCHACHT_OK))
    werte["mit_schacht"] = schacht["mit_schacht"]
    werte["schacht_dn"] = schacht["dn"]
    werte["schacht_durchmesser"] = kt.schacht_durchmesser(schacht["dn"])
    werte["schacht_ok"] = schacht["ok"]

    werte["symbol_name"] = bt.symbol_for(werte["basket_key"],
                                         werte.get("basket_length"),
                                         werte.get("basket_width"),
                                         werte.get("basket_height"))
    werte["symbol_anchor"] = bt.anchor_for(werte["basket_key"])
    werte["symbol_exists"] = None

    return werte, text_wert(felder.get(FIELD_ID))


# ---------------------------------------------------------------------------
# Kiesrigole
# ---------------------------------------------------------------------------

def werte_aus_kies_record(felder, vorgaben=None):
    """
    Baut aus den Feldern von DB_Kiesrigole das Wertedictionary des Dialogs.
    Rueckgabe: (werte, kies_id)
    """
    werte = dict(vorgaben or {})

    werte["rigole_type"] = ART_KIESRIGOLE
    werte["ist_kiesrigole"] = True
    werte["system_name"] = text_wert(felder.get(KFIELD_SYSTEM),
                                     werte.get("system_name", ""))
    werte["comment"] = text_wert(felder.get(KFIELD_KOMMENTAR), "")

    for feld, schluessel in ((KFIELD_LAENGE, "kies_laenge"),
                             (KFIELD_BREITE, "kies_breite"),
                             (KFIELD_HOEHE, "kies_hoehe")):
        wert = zahl(felder.get(feld))
        if wert is not None:
            werte[schluessel] = wert

    material = text_wert(felder.get(KFIELD_MATERIAL))
    if material in kt.material_names():
        werte["kies_material"] = material

    koeff = zahl(felder.get(KFIELD_KOEFF))
    if koeff is not None:
        werte["storage_percent"] = koeff * 100.0
    werte["load_class"] = text_wert(felder.get(KFIELD_BELASTUNG),
                                    werte.get("load_class", ""))

    rohr = text_wert(felder.get(KFIELD_ROHR_DN))
    if rohr not in kt.draenrohr_names():
        rohr = kt.KEIN_DRAENROHR
    werte["kies_rohr_dn"] = rohr
    werte["kies_rohr_durchmesser"] = kt.rohr_durchmesser(rohr)
    werte["kies_rohr_uk"] = zahl(felder.get(KFIELD_ROHR_UK), 0.0)

    bezug, hoehenwert = _hoehenwert(felder, KFIELD_HOEHENBEZUG,
                                    KFIELD_OK, KFIELD_UK,
                                    werte.get("height_value", 0.0))
    werte["height_mode"] = bezug
    werte["height_value"] = hoehenwert

    schacht = _schacht(felder, KFIELD_SCHACHT_DN, KFIELD_SCHACHT_ANZ,
                       KFIELD_SCHACHT_OK, kt.schacht_namen(),
                       werte.get("kies_schacht_dn", kt.DEFAULT_SCHACHT),
                       werte.get("kies_schacht_ok", kt.DEFAULT_SCHACHT_OK))
    werte["kies_mit_schacht"] = schacht["mit_schacht"]
    werte["kies_schacht_dn"] = schacht["dn"]
    werte["kies_schacht_durchmesser"] = kt.schacht_durchmesser(schacht["dn"])
    werte["kies_schacht_ok"] = schacht["ok"]
    werte["kies_schacht_tiefe"] = kt.SCHACHT_TIEFE_UNTER_ROHR
    werte["kies_schacht_rand"] = kt.SCHACHT_RAND
    werte["kies_schacht_grenze"] = kt.SCHACHT_MITTE_AB_LAENGE

    return werte, text_wert(felder.get(KFIELD_ID))


# ---------------------------------------------------------------------------
# RIGOLE KOMPLEX
# ---------------------------------------------------------------------------

def werte_aus_polygon_record(felder, vorgaben=None):
    """
    Baut aus den Feldern von DB_Rigole_komplex das Wertedictionary des
    Dialogs.

    Was hier NICHT herauskommt, sind die Eckpunkte der Umgrenzung. Sie
    stehen bewusst nicht im Datensatz - gespeichert ist nur der Objektname
    des gezeichneten Polygons (Feld "Umgrenzung"). Das Werkzeug holt es
    darueber aus der Zeichnung zurueck; fehlt es, sagt es das.

    Der Rasterwinkel wird als fester Winkel uebernommen. Beim Bearbeiten
    soll das Raster genau so liegen wie vorher - wuerde es neu aus der
    laengsten Kante bestimmt, koennte sich die ganze Rigole drehen, nur
    weil das Polygon inzwischen leicht veraendert wurde.

    Rueckgabe: (werte, rigole_id)
    """
    werte = dict(vorgaben or {})

    werte["rigole_type"] = text_wert(felder.get(PFIELD_ART),
                                     werte.get("rigole_type", ART_POLYGON))
    werte["system_name"] = text_wert(felder.get(PFIELD_SYSTEM),
                                     werte.get("system_name", ""))
    werte["comment"] = text_wert(felder.get(PFIELD_KOMMENTAR), "")
    werte["umgrenzung_name"] = text_wert(felder.get(PFIELD_UMGRENZUNG), "")

    laenge = zahl(felder.get(PFIELD_KORB_L))
    breite = zahl(felder.get(PFIELD_KORB_B))
    hoehe = zahl(felder.get(PFIELD_KORB_H))
    if laenge is not None:
        werte["basket_length"] = laenge
    if breite is not None:
        werte["basket_width"] = breite
    if hoehe is not None:
        werte["basket_height"] = hoehe
    werte["basket_key"] = _korbtyp_erkennen(laenge, breite, hoehe,
                                            werte.get("rigole_type"))
    werte["basket_swapped"] = False

    lagen = ganzzahl(felder.get(PFIELD_ANZ_HOEHE))
    if lagen is not None:
        werte["count_height"] = lagen

    winkel = zahl(felder.get(PFIELD_WINKEL))
    if winkel is not None:
        werte["raster_modus"] = "winkel"
        werte["raster_winkel"] = winkel
    werte.setdefault("raster_suche", RASTER_SUCHSCHRITTE)

    werte["welded"] = ja_nein(felder.get(PFIELD_VERSCHWEISST),
                              bool(werte.get("welded", False)))
    koeff = zahl(felder.get(PFIELD_KOEFF))
    if koeff is not None:
        werte["storage_percent"] = koeff * 100.0
    werte["load_class"] = text_wert(felder.get(PFIELD_BELASTUNG),
                                    werte.get("load_class", ""))

    bezug, hoehenwert = _hoehenwert(felder, PFIELD_HOEHENBEZUG,
                                    PFIELD_OK, PFIELD_UK,
                                    werte.get("height_value", 0.0))
    werte["height_mode"] = bezug
    werte["height_value"] = hoehenwert

    schacht = _schacht(felder, PFIELD_SCHACHT_DN, PFIELD_SCHACHT_ANZ,
                       PFIELD_SCHACHT_OK, kt.schacht_namen(),
                       werte.get("schacht_dn", kt.DEFAULT_SCHACHT),
                       werte.get("schacht_ok", kt.DEFAULT_SCHACHT_OK))
    werte["mit_schacht"] = schacht["mit_schacht"]
    werte["schacht_dn"] = schacht["dn"]
    werte["schacht_durchmesser"] = kt.schacht_durchmesser(schacht["dn"])
    werte["schacht_ok"] = schacht["ok"]

    werte["symbol_name"] = bt.symbol_for(werte["basket_key"],
                                         werte.get("basket_length"),
                                         werte.get("basket_width"),
                                         werte.get("basket_height"))
    werte["symbol_anchor"] = bt.anchor_for(werte["basket_key"])
    werte["symbol_exists"] = None

    return werte, text_wert(felder.get(PFIELD_ID))
