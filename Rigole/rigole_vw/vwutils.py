# -*- coding: utf-8 -*-
"""
Kleine Helfer rund um die Vectorworks-API.

Hier sind die Erkenntnisse aus den Pruefberichten A, A2, C und C2 als Code
festgehalten - alles, was man in Vectorworks 2026 anders machen muss, als
man es zunaechst erwarten wuerde.

Kompatibilitaet: Python 3.9.2 (Vectorworks 2026)
"""

import vs
import os
import sys

_pd_plugin_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _pd_plugin_root not in sys.path:
    sys.path.insert(0, _pd_plugin_root)
from pd_plan_frame import PlanFrame, rigole_angle

from rigole_core.units import UnitContext


# ---------------------------------------------------------------------------
# Objekttypen (Anhang D der Skriptreferenz)
# ---------------------------------------------------------------------------
TYP_LINIE = 2
TYP_RECHTECK = 3
TYP_TEXT = 10
TYP_GRUPPE = 11
TYP_SYMBOLINSTANZ = 15
TYP_SYMBOLDEFINITION = 16
TYP_RECORDDEFINITION = 47

# Vectorworks-Platzhalter fuer "kein Wert".
# Gemessen in Pruefbericht C: vstGetPt2D liefert 1e+97, wenn kein Punkt
# vorliegt. Get3DCntr liefert denselben Wert auf ungueltigen Handles.
UNGUELTIG = 1.0e90

# Obergrenze fuer Handle-Schleifen.
# Pruefbericht A2 hat gezeigt, dass NextSymDef im leeren Dokument endlos
# dasselbe Handle zurueckgibt. Ohne Obergrenze friert Vectorworks ein.
SCHLEIFEN_LIMIT = 20000


# ---------------------------------------------------------------------------
# Handles
# ---------------------------------------------------------------------------

def handle_ok(h):
    """
    Prueft ein Handle.

    ACHTUNG: 'h is None' funktioniert in Vectorworks 2026 NICHT.
    vs.GetObject() liefert fuer einen nicht vorhandenen Namen ein Objekt
    mit repr() == '0', das nicht None ist - dessen Wahrheitswert aber
    False ist (gemessen in Pruefbericht A2, Abschnitt N1).
    """
    try:
        return bool(h)
    except Exception:
        return False


def resource_exists(name, expected_type):
    """
    Existiert eine Ressource mit diesem Namen UND dem erwarteten Typ?

    Die Typpruefung ist wichtig, weil vs.GetObject laut Referenz zuerst die
    Namensliste und dann die Ebenenliste durchsucht - eine Klasse oder Ebene
    mit demselben Namen wuerde sonst faelschlich als Treffer gelten.
    """
    if not name:
        return False
    try:
        h = vs.GetObject(name)
    except Exception:
        return False
    if not handle_ok(h):
        return False
    try:
        return vs.GetTypeN(h) == expected_type
    except Exception:
        return False


def get_resource(name, expected_type):
    """Liefert das Handle oder None."""
    if not resource_exists(name, expected_type):
        return None
    return vs.GetObject(name)


def symbol_exists(name):
    return resource_exists(name, TYP_SYMBOLDEFINITION)


def record_format_exists(name):
    return resource_exists(name, TYP_RECORDDEFINITION)


def iter_handles(first_func, next_func, limit=SCHLEIFEN_LIMIT):
    """
    Sichere Handle-Schleife mit Abbruchzaehler.

        for h in iter_handles(vs.FSymDef, vs.NextSymDef):
            ...
    """
    try:
        h = first_func()
    except Exception:
        return
    zaehler = 0
    gesehen = set()
    while handle_ok(h) and zaehler < limit:
        zaehler += 1
        # Endlosschleife auf demselben Handle abfangen
        try:
            schluessel = repr(h)
        except Exception:
            schluessel = None
        if schluessel is not None:
            if schluessel in gesehen:
                return
            gesehen.add(schluessel)
        yield h
        try:
            h = next_func(h)
        except Exception:
            return


# ---------------------------------------------------------------------------
# Punkte
# ---------------------------------------------------------------------------

def point_ok(p):
    """Faengt den Platzhalter 1e+97 ab."""
    try:
        if p is None or len(p) < 2:
            return False
        return abs(float(p[0])) < UNGUELTIG and abs(float(p[1])) < UNGUELTIG
    except Exception:
        return False


def mode_value(gruppe, standard=1):
    """
    Wert einer Modusgruppe der Werkzeug-Modusleiste.

    Bei einer Radiogruppe ist das die Nummer des gewaehlten Knopfes, von
    links beginnend bei 1.

    WICHTIG: Unsere beiden Werkzeuge HABEN keine Modusleiste. Sie liesse
    sich nur im Init-Ereignis eines ereignisgesteuerten Werkzeugs anlegen
    (vs.AddRadioMode), und ereignisgesteuert bekommt man ein Skriptwerkzeug
    ueber den Plug-in-Manager nicht - so steht es in der Anmerkung zu
    vstGetEventInfo in der Vectorworks-Entwicklerreferenz.

    Diese Funktion bleibt trotzdem stehen: sie liefert dann 'standard'
    (= neu anlegen), und das Werkzeug entscheidet selbst am Klickpunkt,
    siehe rigole_vw/bearbeiten.py. Kommt spaeter doch eine Modusleiste
    dazu, wird sie ohne weitere Aenderung gelesen.
    """
    try:
        wert = vs.vstGetModeValue(int(gruppe))
    except Exception:
        return standard
    try:
        wert = int(wert)
    except (TypeError, ValueError):
        return standard
    return wert if wert >= 1 else standard


def get_tool_point():
    """
    Liefert den vom Anwender geklickten Punkt in DOKUMENTEINHEITEN
    oder None.

    Grundlage Pruefbericht C/C2: In einem Werkzeug mit der Einstellung
    'Script ausfuehren = Nach Mausklick' liefert vstGetCurrPt2D() den
    Klickpunkt zuverlaessig. vstGetPt2D() liefert dagegen 1e+97, weil das
    Werkzeug nicht ereignisgesteuert ist - es dient hier nur als Rueckfall.
    """
    try:
        p = vs.vstGetCurrPt2D()
        if point_ok(p):
            return (float(p[0]), float(p[1]))
    except Exception:
        pass
    try:
        p = vs.vstGetPt2D(0, True)
        if point_ok(p):
            return (float(p[0]), float(p[1]))
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Einheiten
# ---------------------------------------------------------------------------

def get_unit_context():
    """
    Liest die Dokumenteinheiten EINMAL und verpackt sie.
    Wird danach an alle Geometriefunktionen weitergereicht (Performance).
    """
    try:
        fraction, display, format_, upi, name, square_name = vs.GetUnits()
        return UnitContext(upi, name, square_name)
    except Exception as error:
        raise RuntimeError(
            "Dokumenteinheiten konnten nicht sicher gelesen werden. "
            "Die Rigole wurde nicht erstellt. Bitte die Dokumenteinheiten "
            "prüfen und den Befehl erneut starten.") from error


# ---------------------------------------------------------------------------
# Meldungen
# ---------------------------------------------------------------------------

def alert(text):
    try:
        vs.AlrtDialog(text)
    except Exception:
        pass


def status(text):
    try:
        vs.Message(text)
    except Exception:
        pass


def frage(text):
    try:
        return bool(vs.YNDialog(text))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Klassen
# ---------------------------------------------------------------------------

def ensure_class(name):
    """
    Legt die Klasse an, falls sie fehlt, und macht sie aktiv.
    vs.NameClass erledigt beides in einem Schritt.
    """
    try:
        vs.NameClass(name)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------

class Rollback(object):
    """
    Sammelt erzeugte Objekte, damit bei einem Fehler nichts Halbfertiges
    in der Zeichnung zurueckbleibt (Anforderung Punkt 23).

    Verwendung:

        rb = Rollback()
        try:
            vs.Rect(...)
            rb.merke_letztes()
            ...
            rb.ersetze_durch_gruppe(h_gruppe)   # nach dem Gruppieren
        except Exception:
            rb.zuruecknehmen()
            raise
    """

    def __init__(self):
        self.handles = []

    def merke(self, h):
        if handle_ok(h):
            self.handles.append(h)
        return h

    def merke_letztes(self):
        """
        vs.LNewObj() MUSS unmittelbar nach der erzeugenden Funktion
        aufgerufen werden - so steht es in der Referenz.
        """
        try:
            return self.merke(vs.LNewObj())
        except Exception:
            return None

    def ersetze_durch_gruppe(self, h_gruppe, anzahl_ersetzte=None):
        """
        Nach dem Gruppieren duerfen die Einzelobjekte nicht mehr einzeln
        geloescht werden - stattdessen traegt die Gruppe die Verantwortung.
        """
        if anzahl_ersetzte is None:
            self.handles = []
        else:
            self.handles = self.handles[:-int(anzahl_ersetzte)]
        self.merke(h_gruppe)

    def zuruecknehmen(self):
        """Loescht in umgekehrter Erzeugungsreihenfolge."""
        geloescht = 0
        for h in reversed(self.handles):
            try:
                vs.DelObject(h)
                geloescht += 1
            except Exception:
                pass
        self.handles = []
        return geloescht

    def __len__(self):
        return len(self.handles)
