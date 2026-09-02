# -*- coding: utf-8 -*-
"""
Modus "Vorhandenes bearbeiten" (Stand 25.08.2026).

WARUM KEINE MODUSLEISTE
-----------------------
Geplant war eine Radiogruppe in der Modusleiste ("Neu erstellen" /
"Vorhandenes bearbeiten"). Der Plug-in-Manager hat dafuer aber keinen
Bereich: eine Modusleiste kann ein Skriptwerkzeug nur selbst anlegen
(vs.AddRadioMode bzw. vs.vstAddRadioMode), und zwar im Init-Ereignis eines
EREIGNISGESTEUERTEN Werkzeugs. Die Entwicklerreferenz sagt bei
vstGetEventInfo ausdruecklich, dass es keinen Weg ueber die Oberflaeche
gibt, ein Skriptwerkzeug ereignisgesteuert zu machen.

Deshalb entscheidet das Werkzeug selbst, und zwar am Klickpunkt:

    Klick auf eine vorhandene Rigole  ->  Rueckfrage, dann bearbeiten
    Klick ins Leere                   ->  neu anlegen

Die Rueckfrage ist wichtig: sie haelt den Fall offen, dass jemand eine neue
Rigole genau ueber einer vorhandenen anlegen will, und sie verhindert, dass
ein danebengegangener Klick unbemerkt eine fertige Rigole umbaut.

Sollte das Werkzeug spaeter doch ereignisgesteuert laufen, ist die
Radiogruppe weiterhin vorgesehen: liefert vstGetModeValue eine 2, wird ohne
Rueckfrage bearbeitet (siehe vorbereiten()).

WAS "BEARBEITEN" HIER HEISST
----------------------------
Technisch ein NEUBAU an derselben Stelle, kein Aendern im Bestand: die alte
Symbolinstanz und ihre Beschriftung werden entfernt und mit den neuen Werten
neu aufgebaut. Rigolen-ID und Einfuegepunkt bleiben erhalten.

Der Grund liegt in der Bauform: Die Rigole ist eine Symbolinstanz, kein
parametrisches Objekt. Ihre Geometrie steckt in der Symboldefinition und
laesst sich nicht nachtraeglich umrechnen.

Folge, die der Anwender kennen muss: von Hand geaenderte Attribute am Objekt
(Farbe, Fuellung, Ebenenwechsel) sind danach weg. Der ganze Werkzeuglauf ist
EIN Undo-Schritt, ein versehentliches Bearbeiten laesst sich also mit einem
Rueckgaengig vollstaendig zuruecknehmen.

REIHENFOLGE
-----------
Erst Dialog, Pruefung und Berechnung - dabei wird nichts angetastet. Nur wenn
alles stimmt, wird geloescht und neu gebaut. Scheitert der Neubau, nimmt der
Builder seine eigenen Objekte zurueck; die alte Rigole holt der Anwender mit
Rueckgaengig zurueck.

Kompatibilitaet: Python 3.9.2 (Vectorworks 2026)
"""

import vs
import uuid

from rigole_config.constants import (
    RECORD_NAME, RECORD_NAME_KIES, RECORD_NAME_POLY,
    LABEL_NAME_TEMPLATE, LABEL_NAME_TEMPLATE_KIES, LABEL_NAME_TEMPLATE_POLY,
    FIELD_ID, KFIELD_ID, PFIELD_ID,
    MODE_BEARBEITEN,
)
from rigole_core import aus_datensatz
from rigole_vw import vwutils, records, builder

ART_RIGOLE = "rigole"
ART_KIES = "kies"
ART_POLYGON = "polygon"


class BearbeitenFehler(Exception):
    pass


BEZEICHNUNGEN = {
    ART_RIGOLE: u"Rigole",
    ART_KIES: u"Kiesrigole",
    ART_POLYGON: u"komplexe Rigole",
}

WERKZEUGNAMEN = {
    ART_RIGOLE: u"Rigole",
    ART_KIES: u"Kiesrigole",
    ART_POLYGON: u"Rigole komplex",
}


def _bezeichnung(art):
    return BEZEICHNUNGEN.get(art, u"Rigole")


# ---------------------------------------------------------------------------
# Objekt finden
# ---------------------------------------------------------------------------

def finde_am_punkt(punkt_doc):
    """
    Was liegt unter dem Klickpunkt? Handle oder None.

    NUR der Klickpunkt zaehlt - ausdruecklich ohne Rueckfall auf die
    Auswahl. Der Builder markiert die frisch gebaute Rigole; wuerde die
    Auswahl mitzaehlen, fragte das Werkzeug beim naechsten Klick jedes Mal
    nach dem Bearbeiten der zuletzt gebauten Rigole.

    Laut Referenz findet vs.PickObject nur, was auch mit dem Auswahlwerkzeug
    anklickbar waere - nichts auf ausgeblendeten Klassen oder Ebenen. Das ist
    hier genau richtig: was der Anwender nicht sieht, soll er auch nicht
    versehentlich umbauen.
    """
    if punkt_doc is None:
        return None
    try:
        h = vs.PickObject((float(punkt_doc[0]), float(punkt_doc[1])))
    except Exception:
        return None
    return h if vwutils.handle_ok(h) else None


def finde_objekt(punkt_doc=None):
    """
    Das zu bearbeitende Objekt im ausdruecklichen Bearbeiten-Modus
    (Modusleiste, falls je vorhanden).

    Erst der Klickpunkt, danach die Auswahl (vs.FSActLayer). Der zweite Weg
    ist der Rueckfall fuer Rigolen auf ausgeblendeten Klassen oder Ebenen:
    markieren, dann klicken.

    Rueckgabe: Handle oder None.
    """
    h = finde_am_punkt(punkt_doc)
    if h is not None:
        return h

    try:
        h = vs.FSActLayer()
    except Exception:
        h = None
    return h if vwutils.handle_ok(h) else None


def art_des_objekts(h):
    """
    Welche Bauart traegt das Objekt?
    Rueckgabe: ART_RIGOLE, ART_KIES oder None.

    Erkannt wird am angehaengten Datensatz - nicht an Klasse oder Name, die
    kann jeder von Hand aendern.

    Zuerst werden die angehaengten Datensaetze durchgezaehlt (NumRecords /
    GetRecord liefern Handles, deren Name das Datensatzformat ist). Klappt
    das nicht, wird ersatzweise ein Pflichtfeld gelesen: GetRField liefert
    fuer einen nicht angehaengten Datensatz einen leeren Text.
    """
    if not vwutils.handle_ok(h):
        return None

    zuordnung = {RECORD_NAME_KIES: ART_KIES, RECORD_NAME: ART_RIGOLE,
                 RECORD_NAME_POLY: ART_POLYGON}
    try:
        anzahl = int(vs.NumRecords(h))
    except Exception:
        anzahl = 0
    for i in range(1, anzahl + 1):
        try:
            h_rec = vs.GetRecord(h, i)
            if not vwutils.handle_ok(h_rec):
                continue
            name = str(vs.GetName(h_rec) or "")
        except Exception:
            continue
        if name in zuordnung:
            return zuordnung[name]

    for record, feld, art in ((RECORD_NAME_KIES, KFIELD_ID, ART_KIES),
                              (RECORD_NAME_POLY, PFIELD_ID, ART_POLYGON),
                              (RECORD_NAME, FIELD_ID, ART_RIGOLE)):
        try:
            if str(vs.GetRField(h, record, feld) or "").strip():
                return art
        except Exception:
            pass
    return None


def kennung_des_objekts(h, art):
    """Die gespeicherte ID (z. B. 'RIG-004') oder ''."""
    if art == ART_KIES:
        record, feld = RECORD_NAME_KIES, KFIELD_ID
    elif art == ART_POLYGON:
        record, feld = RECORD_NAME_POLY, PFIELD_ID
    else:
        record, feld = RECORD_NAME, FIELD_ID
    try:
        return str(vs.GetRField(h, record, feld) or "").strip()
    except Exception:
        return ""


def einfuegepunkt(h):
    """
    Einfuegepunkt der Symbolinstanz in Dokumenteinheiten.
    Rueckgabe: (x, y) oder None.
    """
    try:
        p = vs.GetSymLoc(h)
        x, y = float(p[0]), float(p[1])
    except Exception:
        return None
    if abs(x) >= vwutils.UNGUELTIG or abs(y) >= vwutils.UNGUELTIG:
        return None
    return (x, y)


# ---------------------------------------------------------------------------
# Werte zurueckholen
# ---------------------------------------------------------------------------

def lies_werte(h, art, vorgaben=None):
    """
    Datensatz -> Wertedictionary des Dialogs.
    Rueckgabe: (werte, id, fehlende_felder)

    'fehlende_felder' nennt die Felder, die dem Datensatz fehlen - bei
    Rigolen aus aelteren Programmstaenden zum Beispiel die Schachtangaben.
    Fuer sie gelten dann die zuletzt gespeicherten Einstellungen; das
    Werkzeug sagt das auch.
    """
    if art == ART_KIES:
        felder = records.read_kies_record(h)
        werte, kennung = aus_datensatz.werte_aus_kies_record(felder, vorgaben)
    elif art == ART_POLYGON:
        felder = records.read_poly_record(h)
        werte, kennung = aus_datensatz.werte_aus_polygon_record(felder,
                                                                vorgaben)
    else:
        felder = records.read_record(h)
        werte, kennung = aus_datensatz.werte_aus_rigole_record(felder,
                                                               vorgaben)

    fehlend = [name for name, wert in felder.items() if wert is None]
    return werte, kennung, fehlend


# ---------------------------------------------------------------------------
# Vor dem Dialog: neu oder bearbeiten?
# ---------------------------------------------------------------------------

class Vorbereitung(object):
    """
    Ergebnis der Modusklaerung.

    weiter    False = Werkzeuglauf beenden, die Meldung ist bereits gezeigt
    alt       Handle der zu ersetzenden Rigole oder None (= Neubau)
    kennung   erhaltene ID beim Bearbeiten, sonst None
    punkt     Einfuegepunkt (beim Bearbeiten der des Altobjekts)
    vorgaben  Vorbelegung des Dialogs
    text      eine Zeile fuers Protokoll
    """

    __slots__ = ("weiter", "alt", "kennung", "punkt", "vorgaben", "text")

    def __init__(self, weiter, alt=None, kennung=None, punkt=None,
                 vorgaben=None, text=u""):
        self.weiter = bool(weiter)
        self.alt = alt
        self.kennung = kennung
        self.punkt = punkt
        self.vorgaben = vorgaben
        self.text = text


def _uebernehmen(h, art, vorgaben, quelle):
    """Werte des vorhandenen Objekts in den Dialog holen."""
    stelle = einfuegepunkt(h)
    if stelle is None:
        vwutils.alert(
            u"Der Einfuegepunkt der vorhandenen %s liess sich nicht "
            u"bestimmen. Es wurde nichts veraendert." % (_bezeichnung(art),))
        return Vorbereitung(False)

    werte, kennung, fehlend = lies_werte(h, art, vorgaben)
    if fehlend:
        vwutils.alert(meldung_fehlende_felder(fehlend))

    return Vorbereitung(True, alt=h, kennung=kennung, punkt=stelle,
                        vorgaben=werte,
                        text=u"bearbeiten (%s) - %s am Punkt %s"
                             % (quelle, kennung, stelle))


def vorbereiten(punkt, art_erwartet, vorgaben, modus=1):
    """
    Klaert vor dem Dialog, ob neu gebaut oder bearbeitet wird.

    modus == MODE_BEARBEITEN  (nur mit Modusleiste erreichbar):
        Es MUSS eine passende Rigole gefunden werden, sonst Meldung und Ende.

    sonst - automatische Erkennung am Klickpunkt:
        passende Rigole getroffen  -> Rueckfrage; Nein = neu anlegen
        andere Bauart getroffen    -> Hinweis; Nein = abbrechen
        nichts getroffen           -> neu anlegen

    Rueckgabe: Vorbereitung
    """
    if modus == MODE_BEARBEITEN:
        h = finde_objekt(punkt)
        art = art_des_objekts(h)
        if art is None:
            vwutils.alert(meldung_nichts_gefunden(art_erwartet))
            return Vorbereitung(False)
        if art != art_erwartet:
            vwutils.alert(meldung_falsche_bauart(art))
            return Vorbereitung(False)
        return _uebernehmen(h, art, vorgaben, u"Modusleiste")

    neu = Vorbereitung(True, punkt=punkt, vorgaben=vorgaben,
                       text=u"neu anlegen")

    h = finde_am_punkt(punkt)
    art = art_des_objekts(h)
    if art is None:
        return neu

    if art != art_erwartet:
        if vwutils.frage(meldung_fremde_bauart(art, art_erwartet)):
            return neu
        return Vorbereitung(False)

    kennung = kennung_des_objekts(h, art)
    if not vwutils.frage(frage_bearbeiten(art, kennung)):
        return neu

    return _uebernehmen(h, art, vorgaben, u"Klickpunkt")


# ---------------------------------------------------------------------------
# Altbestand entfernen
# ---------------------------------------------------------------------------

def _symbolname_der_instanz(h):
    try:
        name = vs.GetSymName(h)
    except Exception:
        return ""
    return str(name or "")


def _symbol_noch_benutzt(symbolname, art):
    """
    Gibt es nach dem Loeschen noch eine Rigole, die auf dieser
    Symboldefinition beruht?
    """
    if not symbolname:
        return True
    if art == ART_KIES:
        return bool(records.kies_daten_zu_symbol(symbolname))
    if art == ART_POLYGON:
        return bool(records.poly_daten_zu_symbol(symbolname))
    return bool(records.rigole_daten_zu_symbol(symbolname))


def neu_aufbauen(h, art, kennung, build):
    """Build and verify first; failed construction never deletes the original."""
    if h is None:
        return build()
    template = {ART_KIES: LABEL_NAME_TEMPLATE_KIES,
                ART_POLYGON: LABEL_NAME_TEMPLATE_POLY}.get(art, LABEL_NAME_TEMPLATE)
    old_label = vs.GetObject(template.format(rigole_id=kennung)) if kennung else None
    originals = [item for item in (h, old_label) if vwutils.handle_ok(item)]
    names = [(item, str(vs.GetName(item) or "")) for item in originals]
    info = None
    try:
        for item, name in names:
            if name:
                temporary = "PD_Rigole_Alt_" + uuid.uuid4().hex
                vs.SetName(item, temporary)
                if str(vs.GetName(item)) != temporary:
                    raise builder.BauFehler("Der Altbestand konnte nicht sicher reserviert werden.")
        info = build()
        if not info or not vwutils.handle_ok(info.get("instance")):
            raise builder.BauFehler("Der Neubau lieferte keine gültige Rigole.")
    except Exception as error:
        for item, name in names:
            if name:
                vs.SetName(item, name)
        raise builder.BauFehler(
            "Neubau abgebrochen; die bisherige Rigole bleibt erhalten.\n" + str(error)) from error
    # Do not remove shared symbol definitions. Existing instances can still
    # reference them, and the resource is useful for a document Undo.
    for item in originals:
        vs.DelObject(item)
    return info


def entferne_alt(h, art, kennung):
    """
    Entfernt Symbolinstanz und Beschriftung des bearbeiteten Objekts - und
    die Symboldefinition, wenn danach niemand mehr auf ihr sitzt. Nur so
    bleibt beim Neubau der urspruengliche Symbolname frei; sonst bekaeme die
    bearbeitete Rigole einen Namen mit angehaengter ID.

    Rueckgabe: dict mit
        beschriftung_geloescht  bool
        symbol_geloescht        bool
        symbolname              str
    """
    ergebnis = {"beschriftung_geloescht": False, "symbol_geloescht": False,
                "symbolname": ""}

    symbolname = _symbolname_der_instanz(h)
    ergebnis["symbolname"] = symbolname

    # --- Beschriftung ------------------------------------------------------
    vorlage = {ART_KIES: LABEL_NAME_TEMPLATE_KIES,
               ART_POLYGON: LABEL_NAME_TEMPLATE_POLY}.get(
                   art, LABEL_NAME_TEMPLATE)
    if kennung:
        try:
            h_text = vs.GetObject(vorlage.format(rigole_id=kennung))
        except Exception:
            h_text = None
        if vwutils.handle_ok(h_text):
            try:
                vs.DelObject(h_text)
                ergebnis["beschriftung_geloescht"] = True
            except Exception:
                pass

    # --- Instanz -----------------------------------------------------------
    try:
        vs.DelObject(h)
    except Exception as ex:
        raise BearbeitenFehler(
            u"Die vorhandene Rigole konnte nicht entfernt werden.\n\n"
            u"Technische Meldung: %r" % (ex,))

    # --- Symboldefinition, falls verwaist ---------------------------------
    if symbolname and not _symbol_noch_benutzt(symbolname, art):
        if builder.loesche_symboldefinition(symbolname):
            ergebnis["symbol_geloescht"] = True

    return ergebnis


# ---------------------------------------------------------------------------
# Meldungstexte
# ---------------------------------------------------------------------------

def frage_bearbeiten(art, kennung):
    was = _bezeichnung(art)
    name = (u"%s „%s“" % (was, kennung)) if kennung else (u"eine %s" % (was,))
    return (u"An dieser Stelle liegt bereits %s.\n\n"
            u"JA  = diese %s bearbeiten. Der Dialog oeffnet sich mit ihren "
            u"Werten; nach OK wird sie an derselben Stelle neu aufgebaut, "
            u"Kennung und Einfuegepunkt bleiben erhalten.\n\n"
            u"NEIN = hier eine ZUSAETZLICHE %s anlegen.\n\n"
            u"Vorhandene %s bearbeiten?" % (name, was, was, was))


def meldung_fremde_bauart(gefunden, erwartet):
    return (u"An dieser Stelle liegt eine %s.\n\n"
            u"Bearbeiten laesst sie sich nur mit dem Werkzeug „%s“.\n\n"
            u"Soll hier stattdessen eine neue %s angelegt werden?"
            % (_bezeichnung(gefunden), _bezeichnung(gefunden),
               _bezeichnung(erwartet)))


def meldung_nichts_gefunden(art_erwartet):
    was = _bezeichnung(art_erwartet)
    return (u"An dieser Stelle liegt keine %s dieses Werkzeugs.\n\n"
            u"Bitte klicken Sie im Modus „Vorhandenes bearbeiten“ auf eine "
            u"vorhandene %s - oder markieren Sie sie vorher.\n\n"
            u"Hinweis: Angeklickt werden kann nur, was auch mit dem "
            u"Auswahlwerkzeug erreichbar ist. Liegt die %s auf einer "
            u"ausgeblendeten Klasse oder Ebene, markieren Sie sie bitte "
            u"zuerst." % (was, was, was))


def meldung_falsche_bauart(gefunden):
    if gefunden == ART_KIES:
        return (u"Das angeklickte Objekt ist eine KIESRIGOLE.\n\n"
                u"Bitte bearbeiten Sie sie mit dem Werkzeug „Kiesrigole“.")
    return (u"Das angeklickte Objekt ist eine Rigole aus RIGOLENKOERPERN.\n\n"
            u"Bitte bearbeiten Sie sie mit dem Werkzeug „Rigole“.")


def meldung_fehlende_felder(fehlend):
    return (u"Diese Rigole stammt aus einem aelteren Programmstand - "
            u"folgende Angaben fehlen im Datensatz und wurden mit den "
            u"zuletzt verwendeten Einstellungen vorbelegt:\n\n%s\n\n"
            u"Bitte im Dialog pruefen." % (u", ".join(sorted(fehlend)),))
