# -*- coding: utf-8 -*-
"""
Gemeinsame Bausteine der Einstellungsdialoge.

Seit dem 24.08.2026 gibt es ZWEI Werkzeuge - „Rigole" (Rigolenkoerper) und
„Kiesrigole". Beide brauchen dieselben kleinen Lese- und Schreibhilfen fuer
den Layout-Manager. Die stehen deshalb hier, statt in beiden Dialogdateien
doppelt zu leben.

ZWEI REGELN, die Pruefbericht C2 erzwungen hat
----------------------------------------------
1. AddChoice MUSS im Dialog-Handler beim Ereignis SetupDialogC (12255)
   aufgerufen werden, nicht beim Aufbau des Dialogs. Sonst bleiben alle
   Aufklappmenues leer.
2. Alle Werte MUESSEN INNERHALB des Handlers gelesen werden, solange der
   Dialog noch existiert. Nach dem Ende von RunLayoutDialog liefert
   GetEditReal nur noch (False, 0.0).

Ereignisnummern (gemessen, nicht geraten):
    12255  Dialog wird aufgebaut   (SetupDialogC)
    12256  Dialog wird geschlossen
        1  OK
        2  Abbrechen
   sonst  ID des ausgeloesten Steuerelements

Es ist immer nur EIN Dialog gleichzeitig offen, deshalb genuegt ein einziger
Zustand auf Modulebene.

Kompatibilitaet: Python 3.9.2 (Vectorworks 2026)
"""

import vs


EV_SETUP = 12255
EV_CLOSE = 12256
EV_OK = 1
EV_CANCEL = 2

BREITE_LABEL = 26          # Zeichen fuer die Beschriftungstexte
BREITE_FELD = 12


class Zustand(object):
    def __init__(self):
        self.dlg = 0
        self.defaults = {}
        self.symbolnamen = []
        self.werte = None          # gelesene Werte bei OK
        self.abgebrochen = True
        # Nur "Rigole komplex": die Eckpunkte des angeklickten Polygons in
        # Metern. Der Dialog rechnet damit seine Vorschau.
        self.polygon = []


Z = Zustand()


# ---------------------------------------------------------------------------
# Lesen  (immer INNERHALB des Handlers benutzen!)
# ---------------------------------------------------------------------------

def real(item, standard=0.0):
    try:
        ok, wert = vs.GetEditReal(Z.dlg, item, 1)
        return float(wert) if ok else standard
    except Exception:
        return standard


def ganzzahl(item, standard=0):
    try:
        ok, wert = vs.GetEditInteger(Z.dlg, item)
        return int(wert) if ok else standard
    except Exception:
        return standard


def text(item, standard=""):
    try:
        wert = vs.GetItemText(Z.dlg, item)
        return wert if wert is not None else standard
    except Exception:
        return standard


def ja_nein(item, standard=False):
    try:
        ergebnis = vs.GetBooleanItem(Z.dlg, item)
        # Die Referenz nennt eine BOOLEAN-Rueckgabe; in Python kam im Test
        # ein einfacher Wahrheitswert zurueck. Beides abfangen.
        if isinstance(ergebnis, (tuple, list)):
            return bool(ergebnis[-1])
        return bool(ergebnis)
    except Exception:
        return standard


def auswahl(item, werte, standard):
    """Liefert den logischen Wert eines Aufklappmenues (0-basierter Index)."""
    try:
        idx = int(vs.GetSelectedChoiceIndex(Z.dlg, item, 0))
        if 0 <= idx < len(werte):
            return werte[idx]
    except Exception:
        pass
    return standard


# ---------------------------------------------------------------------------
# Schreiben
# ---------------------------------------------------------------------------

def setze_auswahl(item, werte, wert):
    """Waehlt den Eintrag aus, der 'wert' entspricht."""
    try:
        idx = werte.index(wert)
    except ValueError:
        idx = 0
    try:
        vs.SelectChoice(Z.dlg, item, idx, True)
    except Exception:
        pass


def fuelle(item, texte):
    """
    Fuellt ein Aufklappmenue. itemIndex ist laut Referenz 'der Index, NACH
    dem eingefuegt wird' - deshalb fortlaufend 0, 1, 2, ...
    DARF NUR im Ereignis 12255 aufgerufen werden.
    """
    for i, eintrag in enumerate(texte):
        try:
            vs.AddChoice(Z.dlg, item, eintrag, i)
        except Exception:
            pass


def aktiv(item, zustand):
    try:
        vs.EnableItem(Z.dlg, item, bool(zustand))
    except Exception:
        pass


def setze_text(item, inhalt):
    try:
        vs.SetItemText(Z.dlg, item, inhalt)
    except Exception:
        pass


def setze_real(item, wert):
    try:
        vs.SetEditReal(Z.dlg, item, 1, float(wert))
    except Exception:
        pass


def setze_ganzzahl(item, wert):
    try:
        vs.SetEditInteger(Z.dlg, item, int(wert))
    except Exception:
        pass


def setze_ja_nein(item, wert):
    try:
        vs.SetBooleanItem(Z.dlg, item, bool(wert))
    except Exception:
        pass


def hilfetext(item, inhalt):
    try:
        vs.SetHelpText(Z.dlg, item, inhalt)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Dialoglauf
# ---------------------------------------------------------------------------

def starte(baue_dialog, handler, defaults, symbolnamen=None,
           polygon=None):
    """
    Baut den Dialog, laesst ihn laufen und liefert die Eingaben zurueck.

    baue_dialog   Funktion ohne Argumente, die vs.CreateLayout aufruft und
                  Z.dlg setzt
    handler       Ereignisbehandlung

    Rueckgabe: dict mit den Eingaben, oder None bei Abbruch.
    """
    Z.defaults = dict(defaults or {})
    Z.symbolnamen = list(symbolnamen or [])
    Z.werte = None
    Z.abgebrochen = True
    Z.polygon = list(polygon or [])

    try:
        dlg = baue_dialog()
    except Exception as ex:
        try:
            vs.AlrtDialog("Der Einstellungsdialog konnte nicht aufgebaut "
                          "werden:\n\n%r" % (ex,))
        except Exception:
            pass
        return None

    try:
        ergebnis = vs.RunLayoutDialog(dlg, handler)
    except Exception as ex:
        try:
            vs.AlrtDialog("Der Einstellungsdialog konnte nicht geoeffnet "
                          "werden:\n\n%r" % (ex,))
        except Exception:
            pass
        return None

    if ergebnis != EV_OK or Z.abgebrochen or Z.werte is None:
        return None
    return Z.werte
