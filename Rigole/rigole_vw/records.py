# -*- coding: utf-8 -*-
"""
PHASE 5 - Datensatzformat DB_Rigole und Rigolen-ID.

Zustaendig fuer:
  * Record Format anlegen bzw. vorhandenes erkennen und ergaenzen
  * die naechste freie Rigolen-ID ermitteln
  * alle Werte an das zentrale Hauptobjekt schreiben

Wichtige Erkenntnisse aus den Pruefberichten, die hier eingebaut sind:
  * vs.GetObject liefert fuer nicht vorhandene Namen KEIN None -> Pruefung
    ueber vwutils.record_format_exists (Typ 47).
  * vs.ForEachObject mit dem Kriterium ((R IN ['DB_Rigole'])) durchsucht das
    GANZE Dokument, auch andere Ebenen. Eine Schleife ueber Ebenen ist nicht
    noetig (Pruefbericht A, U8).
  * vs.Count liefert einen Float -> int() darum.
  * vs.SetRField erwartet den Wert IMMER als String.
  * vs.NewField kuerzt Feldnamen stillschweigend auf 20 Zeichen - alle
    Feldnamen in constants.py sind darauf geprueft.

Alle Laengen werden in METERN gespeichert, unabhaengig von den
Dokumenteinheiten. Das Feld 'Einheit_Laengen' dokumentiert das in der Datei.

Kompatibilitaet: Python 3.9.2 (Vectorworks 2026)
"""

import vs

from rigole_config.constants import (
    RECORD_NAME, RECORD_FIELDS,
    FIELD_ID, FIELD_ART, FIELD_SYSTEM,
    FIELD_KORB_L, FIELD_KORB_B, FIELD_KORB_H,
    FIELD_ANZ_L, FIELD_ANZ_B, FIELD_ANZ_H,
    FIELD_GES_L, FIELD_GES_B, FIELD_GES_H,
    FIELD_VERSCHWEISST, FIELD_KOEFF,
    FIELD_V_BRUTTO, FIELD_V_SPEICHER,
    FIELD_HOEHENBEZUG, FIELD_OK, FIELD_UK,
    FIELD_BELASTUNG, FIELD_SYMBOL, FIELD_KORB_SYMBOL,
    FIELD_SCHACHT_DN, FIELD_SCHACHT_ANZ,
    FIELD_SCHACHT_OK, FIELD_SCHACHT_UK,
    FIELD_KOMMENTAR, FIELD_DATUM, FIELD_EINHEIT,
    ID_PREFIX, ID_DIGITS, ID_START,
    RECORD_NAME_KIES, RECORD_FIELDS_KIES, ID_PREFIX_KIES, ID_DIGITS_KIES,
    KFIELD_ID, KFIELD_ART, KFIELD_SYSTEM,
    KFIELD_LAENGE, KFIELD_BREITE, KFIELD_HOEHE,
    KFIELD_MATERIAL, KFIELD_KOEFF, KFIELD_V_BRUTTO, KFIELD_V_SPEICHER,
    KFIELD_ROHR_DN, KFIELD_ROHR_DA, KFIELD_ROHR_UK, KFIELD_ROHR_ACHSE,
    KFIELD_ROHR_LAENGE, KFIELD_ROHR_BRUTTO, KFIELD_ROHR_VOLUMEN,
    KFIELD_SCHACHT_DN, KFIELD_SCHACHT_ANZ,
    KFIELD_SCHACHT_OK, KFIELD_SCHACHT_UK,
    KFIELD_HOEHENBEZUG, KFIELD_OK, KFIELD_UK,
    KFIELD_BELASTUNG, KFIELD_SYMBOL,
    KFIELD_KOMMENTAR, KFIELD_DATUM, KFIELD_EINHEIT,
    RECORD_NAME_POLY, RECORD_FIELDS_POLY, ID_PREFIX_POLY, ID_DIGITS_POLY,
    PFIELD_ID, PFIELD_ART, PFIELD_SYSTEM,
    PFIELD_KORB_L, PFIELD_KORB_B, PFIELD_KORB_H,
    PFIELD_ANZ_KOERBE, PFIELD_ANZ_LAGE, PFIELD_ANZ_HOEHE,
    PFIELD_POLY_FLAECHE, PFIELD_BELEGT, PFIELD_AUSNUTZUNG,
    PFIELD_WINKEL, PFIELD_ECKEN, PFIELD_UMGRENZUNG,
    PFIELD_GES_L, PFIELD_GES_B, PFIELD_GES_H,
    PFIELD_VERSCHWEISST, PFIELD_KOEFF, PFIELD_V_BRUTTO, PFIELD_V_SPEICHER,
    PFIELD_HOEHENBEZUG, PFIELD_OK, PFIELD_UK,
    PFIELD_BELASTUNG, PFIELD_SYMBOL, PFIELD_KORB_SYMBOL,
    PFIELD_SCHACHT_DN, PFIELD_SCHACHT_ANZ,
    PFIELD_SCHACHT_OK, PFIELD_SCHACHT_UK,
    PFIELD_KOMMENTAR, PFIELD_DATUM, PFIELD_EINHEIT,
)
from rigole_core.calculations import generate_next_rigole_id
from rigole_vw import vwutils


KRITERIUM = "((R IN ['" + RECORD_NAME + "']))"
KRITERIUM_KIES = "((R IN ['" + RECORD_NAME_KIES + "']))"
KRITERIUM_POLY = "((R IN ['" + RECORD_NAME_POLY + "']))"


def _collect_ids(record_name, field_name, criteria):
    format_handle = vs.GetObject(record_name)
    if int(vs.GetTypeN(format_handle) or 0) == 0:
        return []
    if int(vs.GetTypeN(format_handle)) != 47:
        raise RuntimeError("Datenbankname ist anderweitig vergeben: " + record_name)
    values, errors = [], []
    def collect(handle):
        try:
            value = vs.GetRField(handle, record_name, field_name)
            if value is None:
                raise ValueError("ID nicht lesbar")
            if value:
                values.append(str(value))
        except Exception as error:
            errors.append(str(error))
    vs.ForEachObject(collect, criteria)
    if errors:
        raise RuntimeError("Bestehende Rigolen-IDs nicht vollständig lesbar: " + "; ".join(errors))
    return values


class RecordFehler(Exception):
    """Wird ausgeloest, wenn das Datensatzformat nicht nutzbar ist."""
    pass


# ---------------------------------------------------------------------------
# Datensatzformat sicherstellen
# ---------------------------------------------------------------------------

def kriterium_fuer(record_name):
    """Suchkriterium fuer ein Datensatzformat."""
    return "((R IN ['" + record_name + "']))"


def ensure_record_format(record_name=RECORD_NAME, felder=None):
    """
    Legt DB_Rigole an, falls es fehlt, und ergaenzt fehlende Felder in einem
    bereits vorhandenen Format.

    vs.NewField legt den Datensatz laut Referenz mit an, wenn er noch nicht
    existiert - ein eigener Erzeugungsaufruf ist also nicht noetig. Bei einem
    bereits vorhandenen Feld tut NewField nichts; das ist der gewuenschte
    Fall 'vorhandenes Format verwenden'.

    Rueckgabe: (war_schon_da, liste_der_neu_angelegten_felder)
    Loest RecordFehler aus, wenn das Format danach nicht existiert.
    """
    if felder is None:
        felder = RECORD_FIELDS
    war_schon_da = vwutils.record_format_exists(record_name)

    vorhandene = set()
    if war_schon_da:
        vorhandene = set(existing_field_names(record_name))

    neu = []
    for feldname, typ, stil, standard in felder:
        if feldname in vorhandene:
            continue
        try:
            vs.NewField(record_name, feldname, standard, typ, stil)
            neu.append(feldname)
        except Exception as ex:
            raise RecordFehler(
                u"Das Datensatzfeld „%s“ konnte nicht angelegt werden.\n\n"
                u"Technische Meldung: %r" % (feldname, ex))

    if not vwutils.record_format_exists(record_name):
        raise RecordFehler(
            u"Das Datensatzformat „%s“ konnte nicht angelegt werden.\n\n"
            u"Moeglicherweise existiert bereits ein anderes Objekt mit "
            u"diesem Namen (Klasse, Ebene oder Symbol). Bitte pruefen Sie "
            u"den Ressourcenmanager." % (record_name,))

    return (war_schon_da, neu)


def existing_field_names(record_name=RECORD_NAME):
    """Namen der Felder eines vorhandenen Datensatzformats."""
    namen = []
    h = vwutils.get_resource(record_name, vwutils.TYP_RECORDDEFINITION)
    if h is None:
        return namen
    try:
        anzahl = int(vs.NumFields(h))
    except Exception:
        return namen
    for i in range(1, anzahl + 1):
        try:
            namen.append(vs.GetFldName(h, i))
        except Exception:
            pass
    return namen


# ---------------------------------------------------------------------------
# Rigolen-ID
# ---------------------------------------------------------------------------

_gesammelte_ids = []


def _sammle_id(h):
    wert = vs.GetRField(h, RECORD_NAME, FIELD_ID)
    if wert is None:
        raise RuntimeError("Vorhandene Rigolen-ID konnte nicht gelesen werden.")
    if wert:
        _gesammelte_ids.append(wert)


def collect_existing_ids():
    return _collect_ids(RECORD_NAME, FIELD_ID, KRITERIUM)


_gesammelte_rigole_daten = []


def _sammle_rigole_daten(h):
    eintrag = {}
    for schluessel, feld in (("symbol", FIELD_SYMBOL),
                             ("schacht_dn", FIELD_SCHACHT_DN),
                             ("schacht_anz", FIELD_SCHACHT_ANZ),
                             ("schacht_ok", FIELD_SCHACHT_OK),
                             ("ok_rigole", FIELD_OK)):
        try:
            eintrag[schluessel] = vs.GetRField(h, RECORD_NAME, feld)
        except Exception:
            eintrag[schluessel] = None
    _gesammelte_rigole_daten.append(eintrag)


def rigole_daten_zu_symbol(symbolname):
    """
    Datensaetze aller Rigolen, die auf der angegebenen Symboldefinition
    beruhen - Gegenstueck zu kies_daten_zu_symbol().
    """
    del _gesammelte_rigole_daten[:]
    if not symbolname or not vwutils.record_format_exists(RECORD_NAME):
        return []
    try:
        vs.ForEachObject(_sammle_rigole_daten, KRITERIUM)
    except Exception:
        return []
    name = str(symbolname)
    return [e for e in _gesammelte_rigole_daten
            if str(e.get("symbol") or "") == name]


def count_existing():
    """Anzahl der Rigolen im Dokument. vs.Count liefert einen Float."""
    if not vwutils.record_format_exists(RECORD_NAME):
        return 0
    try:
        return int(vs.Count(KRITERIUM))
    except Exception:
        return 0


def next_rigole_id():
    """Naechste freie ID, z. B. 'RIG-004'. Vorhandene werden nie ueberschrieben."""
    return generate_next_rigole_id(collect_existing_ids(),
                                   prefix=ID_PREFIX, digits=ID_DIGITS,
                                   start=ID_START)


# ---------------------------------------------------------------------------
# Werte schreiben
# ---------------------------------------------------------------------------

def _s(wert, nachkomma=None):
    """
    Wandelt einen Wert in den String, den vs.SetRField erwartet.
    Dezimaltrennzeichen ist der PUNKT - das Record-Feld rechnet den Text
    selbst in seinen Datentyp zurueck.
    """
    if wert is None:
        return ""
    if isinstance(wert, bool):
        return "TRUE" if wert else "FALSE"
    if isinstance(wert, float):
        if nachkomma is None:
            nachkomma = 6
        return ("%." + str(int(nachkomma)) + "f") % (wert,)
    return str(wert)


def write_record(h_objekt, werte, ergebnis, rigole_id, datum=""):
    """
    Haengt DB_Rigole an das Hauptobjekt und schreibt alle Felder.

    h_objekt   Handle der zentralen Rigolengruppe (NUR dieses eine Objekt!)
    werte      Wertedictionary aus dem Dialog
    ergebnis   RigoleResult aus calculations.compute_rigole
    rigole_id  z. B. 'RIG-004'
    datum      Erstellungsdatum als Text, z. B. '2026-08-21'

    Loest RecordFehler aus, wenn der Datensatz nicht angehaengt werden kann.
    """
    if not vwutils.handle_ok(h_objekt):
        raise RecordFehler(u"Kein gueltiges Objekt fuer den Datensatz.")

    try:
        vs.SetRecord(h_objekt, RECORD_NAME)
    except Exception as ex:
        raise RecordFehler(
            u"Der Datensatz „%s“ konnte nicht an die Rigole angehaengt "
            u"werden.\n\nTechnische Meldung: %r" % (RECORD_NAME, ex))

    felder = [
        (FIELD_ID, _s(rigole_id)),
        (FIELD_ART, _s(werte.get("rigole_type", ""))),
        (FIELD_SYSTEM, _s(werte.get("system_name", ""))),

        (FIELD_KORB_L, _s(ergebnis.basket_length, 4)),
        (FIELD_KORB_B, _s(ergebnis.basket_width, 4)),
        (FIELD_KORB_H, _s(ergebnis.basket_height, 4)),

        (FIELD_ANZ_L, _s(int(ergebnis.count_length))),
        (FIELD_ANZ_B, _s(int(ergebnis.count_width))),
        (FIELD_ANZ_H, _s(int(ergebnis.count_height))),

        (FIELD_GES_L, _s(ergebnis.total_length, 4)),
        (FIELD_GES_B, _s(ergebnis.total_width, 4)),
        (FIELD_GES_H, _s(ergebnis.total_height, 4)),

        (FIELD_VERSCHWEISST, _s(bool(werte.get("welded", False)))),

        (FIELD_KOEFF, _s(ergebnis.storage_coefficient, 4)),
        (FIELD_V_BRUTTO, _s(ergebnis.v_brutto, 4)),
        (FIELD_V_SPEICHER, _s(ergebnis.v_speicher, 4)),

        (FIELD_HOEHENBEZUG, _s(ergebnis.height_mode)),
        (FIELD_OK, _s(ergebnis.ok, 4)),
        (FIELD_UK, _s(ergebnis.uk, 4)),

        (FIELD_BELASTUNG, _s(werte.get("load_class", ""))),
        # Symbolname der GESAMTEN Rigole (= eingegebene Bezeichnung)
        (FIELD_SYMBOL, _s(werte.get("symbol_name", ""))),
        # Symbol eines einzelnen Rigolenkoerpers
        (FIELD_KORB_SYMBOL, _s(werte.get("basket_symbol_name", ""))),

        (FIELD_SCHACHT_DN, _s(ergebnis.schacht_dn)),
        (FIELD_SCHACHT_ANZ, _s(int(ergebnis.schacht_anzahl))),
        (FIELD_SCHACHT_OK, _s(ergebnis.schacht_ok, 4)),
        (FIELD_SCHACHT_UK, _s(ergebnis.schacht_uk, 4)),

        (FIELD_KOMMENTAR, _s(werte.get("comment", ""))),
        (FIELD_DATUM, _s(datum)),
        (FIELD_EINHEIT, "m"),
    ]

    fehlgeschlagen = []
    for feldname, text in felder:
        try:
            vs.SetRField(h_objekt, RECORD_NAME, feldname, text)
        except Exception:
            fehlgeschlagen.append(feldname)

    if fehlgeschlagen:
        raise RecordFehler(
            u"Folgende Datensatzfelder konnten nicht beschrieben werden:\n\n"
            + u", ".join(fehlgeschlagen))

    return True


def read_record(h_objekt):
    """Liest alle Felder zurueck - fuer Kontrolle und spaetere Auswertung."""
    ergebnis = {}
    if not vwutils.handle_ok(h_objekt):
        return ergebnis
    for feldname, typ, stil, standard in RECORD_FIELDS:
        try:
            ergebnis[feldname] = vs.GetRField(h_objekt, RECORD_NAME, feldname)
        except Exception:
            ergebnis[feldname] = None
    return ergebnis


# ---------------------------------------------------------------------------
# KIESRIGOLE - eigenes Datensatzformat DB_Kiesrigole
# ---------------------------------------------------------------------------
#
# Bewusst getrennt vom Format der Koerbe-Rigole: die beiden Bauarten haben
# unterschiedliche Felder (Korbanzahl gibt es hier nicht, Draenrohr dort
# nicht). Ein gemeinsames Format mit lauter leeren Feldern waere fuer die
# spaetere Auswertung in Tabellen unbrauchbar.

def ensure_kies_record_format():
    """Legt DB_Kiesrigole an bzw. ergaenzt fehlende Felder."""
    return ensure_record_format(RECORD_NAME_KIES, RECORD_FIELDS_KIES)


_gesammelte_kies_ids = []


def _sammle_kies_id(h):
    wert = vs.GetRField(h, RECORD_NAME_KIES, KFIELD_ID)
    if wert is None:
        raise RuntimeError("Vorhandene Kiesrigolen-ID konnte nicht gelesen werden.")
    if wert:
        _gesammelte_kies_ids.append(wert)


def collect_existing_kies_ids():
    return _collect_ids(RECORD_NAME_KIES, KFIELD_ID, KRITERIUM_KIES)


def count_existing_kies():
    """Anzahl der Kiesrigolen im Dokument."""
    if not vwutils.record_format_exists(RECORD_NAME_KIES):
        return 0
    try:
        return int(vs.Count(KRITERIUM_KIES))
    except Exception:
        return 0


_gesammelte_kies_daten = []


def _sammle_kies_daten(h):
    eintrag = {}
    for schluessel, feld in (("symbol", KFIELD_SYMBOL),
                             ("rohr_dn", KFIELD_ROHR_DN),
                             ("rohr_uk", KFIELD_ROHR_UK),
                             ("schacht_dn", KFIELD_SCHACHT_DN),
                             ("schacht_anz", KFIELD_SCHACHT_ANZ),
                             ("schacht_ok", KFIELD_SCHACHT_OK),
                             ("uk_rigole", KFIELD_UK),
                             ("laenge", KFIELD_LAENGE),
                             ("breite", KFIELD_BREITE),
                             ("hoehe", KFIELD_HOEHE)):
        try:
            eintrag[schluessel] = vs.GetRField(h, RECORD_NAME_KIES, feld)
        except Exception:
            eintrag[schluessel] = None
    _gesammelte_kies_daten.append(eintrag)


def kies_daten_zu_symbol(symbolname):
    """
    Liefert die Datensaetze aller Kiesrigolen im Dokument, die auf der
    angegebenen Symboldefinition beruhen.

    Warum: Eine Symboldefinition traegt ihre Bauteile in sich, aber keine
    auslesbare Merkliste, WELCHES Draenrohr darin steckt. Die Werte stehen
    jedoch im Datensatz jeder Instanz - im Feld "Symbolname" ist vermerkt,
    zu welcher Definition sie gehoert. Darueber laesst sich pruefen, ob eine
    vorhandene Definition zu den neuen Eingaben passt.
    """
    del _gesammelte_kies_daten[:]
    if not symbolname or not vwutils.record_format_exists(RECORD_NAME_KIES):
        return []
    try:
        vs.ForEachObject(_sammle_kies_daten, KRITERIUM_KIES)
    except Exception:
        return []
    name = str(symbolname)
    return [e for e in _gesammelte_kies_daten
            if str(e.get("symbol") or "") == name]


def next_kies_id():
    """Naechste freie ID, z. B. 'KIES-004'."""
    return generate_next_rigole_id(collect_existing_kies_ids(),
                                   prefix=ID_PREFIX_KIES,
                                   digits=ID_DIGITS_KIES,
                                   start=ID_START)


def write_kies_record(h_objekt, werte, ergebnis, kies_id, datum=""):
    """
    Haengt DB_Kiesrigole an die Symbolinstanz und schreibt alle Felder.

    h_objekt   Handle der Symbolinstanz (NUR dieses eine Objekt!)
    werte      Wertedictionary aus dem Dialog
    ergebnis   KiesResult aus calculations.compute_kiesrigole
    kies_id    z. B. 'KIES-004'
    """
    if not vwutils.handle_ok(h_objekt):
        raise RecordFehler(u"Kein gueltiges Objekt fuer den Datensatz.")

    try:
        vs.SetRecord(h_objekt, RECORD_NAME_KIES)
    except Exception as ex:
        raise RecordFehler(
            u"Der Datensatz „%s“ konnte nicht an die Kiesrigole angehaengt "
            u"werden.\n\nTechnische Meldung: %r" % (RECORD_NAME_KIES, ex))

    felder = [
        (KFIELD_ID, _s(kies_id)),
        (KFIELD_ART, _s(werte.get("rigole_type", ""))),
        (KFIELD_SYSTEM, _s(werte.get("system_name", ""))),

        (KFIELD_LAENGE, _s(ergebnis.total_length, 4)),
        (KFIELD_BREITE, _s(ergebnis.total_width, 4)),
        (KFIELD_HOEHE, _s(ergebnis.total_height, 4)),

        (KFIELD_MATERIAL, _s(ergebnis.material)),
        (KFIELD_KOEFF, _s(ergebnis.storage_coefficient, 4)),
        (KFIELD_V_BRUTTO, _s(ergebnis.v_brutto, 4)),
        (KFIELD_V_SPEICHER, _s(ergebnis.v_speicher, 4)),

        (KFIELD_ROHR_DN, _s(ergebnis.rohr_dn)),
        (KFIELD_ROHR_DA, _s(ergebnis.rohr_durchmesser, 4)),
        (KFIELD_ROHR_UK, _s(ergebnis.rohr_uk, 4)),
        (KFIELD_ROHR_ACHSE, _s(ergebnis.rohr_achse, 4)),
        (KFIELD_ROHR_LAENGE, _s(ergebnis.rohr_laenge, 4)),
        (KFIELD_ROHR_BRUTTO, _s(ergebnis.rohr_laenge_brutto, 4)),
        (KFIELD_ROHR_VOLUMEN, _s(ergebnis.rohr_volumen, 4)),

        (KFIELD_SCHACHT_DN, _s(ergebnis.schacht_dn)),
        (KFIELD_SCHACHT_ANZ, _s(int(ergebnis.schacht_anzahl))),
        (KFIELD_SCHACHT_OK, _s(ergebnis.schacht_ok, 4)),
        (KFIELD_SCHACHT_UK, _s(ergebnis.schacht_uk, 4)),

        (KFIELD_HOEHENBEZUG, _s(ergebnis.height_mode)),
        (KFIELD_OK, _s(ergebnis.ok, 4)),
        (KFIELD_UK, _s(ergebnis.uk, 4)),

        (KFIELD_BELASTUNG, _s(werte.get("load_class", ""))),
        (KFIELD_SYMBOL, _s(werte.get("symbol_name", ""))),

        (KFIELD_KOMMENTAR, _s(werte.get("comment", ""))),
        (KFIELD_DATUM, _s(datum)),
        (KFIELD_EINHEIT, "m"),
    ]

    fehlgeschlagen = []
    for feldname, text in felder:
        try:
            vs.SetRField(h_objekt, RECORD_NAME_KIES, feldname, text)
        except Exception:
            fehlgeschlagen.append(feldname)

    if fehlgeschlagen:
        raise RecordFehler(
            u"Folgende Datensatzfelder konnten nicht beschrieben werden:\n\n"
            + u", ".join(fehlgeschlagen))

    return True


def read_kies_record(h_objekt):
    """Liest alle Felder der Kiesrigole zurueck."""
    ergebnis = {}
    if not vwutils.handle_ok(h_objekt):
        return ergebnis
    for feldname, typ, stil, standard in RECORD_FIELDS_KIES:
        try:
            ergebnis[feldname] = vs.GetRField(h_objekt, RECORD_NAME_KIES,
                                              feldname)
        except Exception:
            ergebnis[feldname] = None
    return ergebnis


def heute():
    """Erstellungsdatum als 'JJJJ-MM-TT'."""
    try:
        import datetime
        return datetime.date.today().isoformat()
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# RIGOLE KOMPLEX - eigenes Datensatzformat DB_Rigole_komplex
# ---------------------------------------------------------------------------
#
# Wieder getrennt gefuehrt: Bei der Polygonrigole ist "Anzahl in
# Laengsrichtung x Anzahl in Querrichtung" keine sinnvolle Kennzahl mehr.
# Massgebend sind die belegten Korbplaetze, die Polygonflaeche und die
# Ausnutzung. In einer Tabelle stehen so nebeneinander nur Werte, die auch
# vergleichbar sind.

def ensure_poly_record_format():
    """Legt DB_Rigole_komplex an bzw. ergaenzt fehlende Felder."""
    return ensure_record_format(RECORD_NAME_POLY, RECORD_FIELDS_POLY)


_gesammelte_poly_ids = []


def _sammle_poly_id(h):
    wert = vs.GetRField(h, RECORD_NAME_POLY, PFIELD_ID)
    if wert is None:
        raise RuntimeError("Vorhandene komplexe Rigolen-ID konnte nicht gelesen werden.")
    if wert:
        _gesammelte_poly_ids.append(wert)


def collect_existing_poly_ids():
    return _collect_ids(RECORD_NAME_POLY, PFIELD_ID, KRITERIUM_POLY)


def count_existing_poly():
    if not vwutils.record_format_exists(RECORD_NAME_POLY):
        return 0
    try:
        return int(vs.Count(KRITERIUM_POLY))
    except Exception:
        return 0


_gesammelte_poly_daten = []


def _sammle_poly_daten(h):
    eintrag = {}
    for schluessel, feld in (("symbol", PFIELD_SYMBOL),
                             ("korb_symbol", PFIELD_KORB_SYMBOL),
                             ("koerbe", PFIELD_ANZ_KOERBE),
                             ("je_lage", PFIELD_ANZ_LAGE),
                             ("lagen", PFIELD_ANZ_HOEHE),
                             ("winkel", PFIELD_WINKEL),
                             ("ecken", PFIELD_ECKEN),
                             ("umgrenzung", PFIELD_UMGRENZUNG),
                             ("schacht_dn", PFIELD_SCHACHT_DN),
                             ("schacht_anz", PFIELD_SCHACHT_ANZ),
                             ("schacht_ok", PFIELD_SCHACHT_OK),
                             ("uk_rigole", PFIELD_UK),
                             ("korb_l", PFIELD_KORB_L),
                             ("korb_b", PFIELD_KORB_B),
                             ("korb_h", PFIELD_KORB_H)):
        try:
            eintrag[schluessel] = vs.GetRField(h, RECORD_NAME_POLY, feld)
        except Exception:
            eintrag[schluessel] = None
    _gesammelte_poly_daten.append(eintrag)


def poly_daten_zu_symbol(symbolname):
    """
    Datensaetze aller komplexen Rigolen, die auf dieser Symboldefinition
    beruhen. Gleiche Begruendung wie bei der Kiesrigole: An der Definition
    selbst laesst sich nicht ablesen, welche Korbverteilung darin steckt -
    im Datensatz der Instanz steht es.
    """
    del _gesammelte_poly_daten[:]
    if not symbolname or not vwutils.record_format_exists(RECORD_NAME_POLY):
        return []
    try:
        vs.ForEachObject(_sammle_poly_daten, KRITERIUM_POLY)
    except Exception:
        return []
    name = str(symbolname)
    return [e for e in _gesammelte_poly_daten
            if str(e.get("symbol") or "") == name]


def next_poly_id():
    """Naechste freie ID, z. B. 'RIGK-004'."""
    return generate_next_rigole_id(collect_existing_poly_ids(),
                                   prefix=ID_PREFIX_POLY,
                                   digits=ID_DIGITS_POLY,
                                   start=ID_START)


def write_poly_record(h_objekt, werte, ergebnis, rigole_id, datum="",
                      umgrenzung_name=""):
    """
    Haengt DB_Rigole_komplex an die Symbolinstanz und schreibt alle Felder.

    umgrenzung_name  Objektname des gezeichneten Umgrenzungspolygons. Ueber
                     ihn findet das Werkzeug das Polygon beim Bearbeiten
                     wieder - die Eckpunkte selbst stehen bewusst NICHT im
                     Datensatz, ein Textfeld mit unbekannter Laengengrenze
                     waere dafuer der falsche Ort.
    """
    if not vwutils.handle_ok(h_objekt):
        raise RecordFehler(u"Kein gueltiges Objekt fuer den Datensatz.")

    try:
        vs.SetRecord(h_objekt, RECORD_NAME_POLY)
    except Exception as ex:
        raise RecordFehler(
            u"Der Datensatz \u201e%s\u201c konnte nicht an die Rigole "
            u"angehaengt werden.\n\nTechnische Meldung: %r"
            % (RECORD_NAME_POLY, ex))

    felder = [
        (PFIELD_ID, _s(rigole_id)),
        (PFIELD_ART, _s(werte.get("rigole_type", ""))),
        (PFIELD_SYSTEM, _s(werte.get("system_name", ""))),

        (PFIELD_KORB_L, _s(ergebnis.basket_length, 4)),
        (PFIELD_KORB_B, _s(ergebnis.basket_width, 4)),
        (PFIELD_KORB_H, _s(ergebnis.basket_height, 4)),

        (PFIELD_ANZ_KOERBE, _s(int(ergebnis.basket_count))),
        (PFIELD_ANZ_LAGE, _s(int(ergebnis.koerbe_je_lage))),
        (PFIELD_ANZ_HOEHE, _s(int(ergebnis.count_height))),

        (PFIELD_POLY_FLAECHE, _s(ergebnis.polygon_flaeche, 4)),
        (PFIELD_BELEGT, _s(ergebnis.belegte_flaeche, 4)),
        (PFIELD_AUSNUTZUNG, _s(100.0 * float(ergebnis.ausnutzung or 0.0), 2)),
        (PFIELD_WINKEL, _s(ergebnis.raster_winkel, 4)),
        (PFIELD_ECKEN, _s(int(ergebnis.eckenzahl))),
        (PFIELD_UMGRENZUNG, _s(umgrenzung_name)),

        (PFIELD_GES_L, _s(ergebnis.total_length, 4)),
        (PFIELD_GES_B, _s(ergebnis.total_width, 4)),
        (PFIELD_GES_H, _s(ergebnis.total_height, 4)),

        (PFIELD_VERSCHWEISST, _s(bool(werte.get("welded", False)))),

        (PFIELD_KOEFF, _s(ergebnis.storage_coefficient, 4)),
        (PFIELD_V_BRUTTO, _s(ergebnis.v_brutto, 4)),
        (PFIELD_V_SPEICHER, _s(ergebnis.v_speicher, 4)),

        (PFIELD_HOEHENBEZUG, _s(ergebnis.height_mode)),
        (PFIELD_OK, _s(ergebnis.ok, 4)),
        (PFIELD_UK, _s(ergebnis.uk, 4)),

        (PFIELD_BELASTUNG, _s(werte.get("load_class", ""))),
        (PFIELD_SYMBOL, _s(werte.get("symbol_name", ""))),
        (PFIELD_KORB_SYMBOL, _s(werte.get("basket_symbol_name", ""))),

        (PFIELD_SCHACHT_DN, _s(ergebnis.schacht_dn)),
        (PFIELD_SCHACHT_ANZ, _s(int(ergebnis.schacht_anzahl))),
        (PFIELD_SCHACHT_OK, _s(ergebnis.schacht_ok, 4)),
        (PFIELD_SCHACHT_UK, _s(ergebnis.schacht_uk, 4)),

        (PFIELD_KOMMENTAR, _s(werte.get("comment", ""))),
        (PFIELD_DATUM, _s(datum)),
        (PFIELD_EINHEIT, "m"),
    ]

    fehlgeschlagen = []
    for feldname, text in felder:
        try:
            vs.SetRField(h_objekt, RECORD_NAME_POLY, feldname, text)
        except Exception:
            fehlgeschlagen.append(feldname)

    if fehlgeschlagen:
        raise RecordFehler(
            u"Folgende Datensatzfelder konnten nicht beschrieben werden:\n\n"
            + u", ".join(fehlgeschlagen))

    return True


def read_poly_record(h_objekt):
    """Liest alle Felder der komplexen Rigole zurueck."""
    ergebnis = {}
    if not vwutils.handle_ok(h_objekt):
        return ergebnis
    for feldname, typ, stil, standard in RECORD_FIELDS_POLY:
        try:
            ergebnis[feldname] = vs.GetRField(h_objekt, RECORD_NAME_POLY,
                                              feldname)
        except Exception:
            ergebnis[feldname] = None
    return ergebnis
