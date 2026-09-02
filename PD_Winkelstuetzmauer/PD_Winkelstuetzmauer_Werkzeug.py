# -*- coding: utf-8 -*-
"""
==============================================================================
 PD Winkelstuetzmauer - WERKZEUG-Variante (Plug-in vom Typ "Werkzeug")
==============================================================================

 Dieses Skript gehoert in ein Plug-in vom Typ *Werkzeug* und macht daraus
 ein "Aktionswerkzeug": ein Klick auf das Symbol in der Werkzeugpalette
 startet denselben Ablauf wie der Menuebefehl. Anschliessend schaltet
 Vectorworks zurueck auf das Auswahlwerkzeug.

 WICHTIG - bitte vorher lesen:
 - Werkzeuge werden ueber Ereignisse gesteuert. Die Nummern der Ereignisse
   koennen sich zwischen Versionen unterscheiden; sie stehen in der
   Vectorworks-Skriptreferenz unter "Tool Events". Das Skript wertet sie
   defensiv aus und faellt notfalls auf "sofort ausfuehren" zurueck.
 - Das eigentliche Zeichnen liegt unveraendert in PD_Winkelstuetzmauer.py.
   Diese Datei laedt sie nur - es gibt also keine zweite Fassung zu pflegen.
==============================================================================
"""

import vs
import os

NAME = 'PD_Winkelstuetzmauer.py'
ORDNER = 'PD_Winkelstuetzmauer'

# Ereignisnummern laut Skriptreferenz (bei Bedarf anpassen)
EV_SETUP = 3          # Werkzeug wird aktiviert
EV_MOUSEDOWN = 100    # Mausklick in der Zeichnung
EV_MOUSEUP = 103


def _basis():
    for fid in (-2, 1, 12, 0):
        try:
            r = vs.GetFolderPath(fid)
            if isinstance(r, (list, tuple)):
                r = r[0]
            if r:
                yield str(r)
        except Exception:
            pass


def starte_mauerbefehl():
    """Laedt PD_Winkelstuetzmauer.py und fuehrt sie aus."""
    kandidaten = []
    for b in _basis():
        kandidaten.append(os.path.join(b, ORDNER, NAME))
        kandidaten.append(os.path.join(b, 'Plug-Ins', ORDNER, NAME))
    pfad = next((p for p in kandidaten if os.path.isfile(p)), None)
    if not pfad:
        vs.AlrtDialog('PD Winkelstuetzmauer: Skriptdatei nicht gefunden.\n\n'
                      'Gesucht wurde in:\n' + '\n'.join(kandidaten))
        return
    with open(pfad, encoding='utf-8-sig') as f:
        exec(compile(f.read(), pfad, 'exec'),
             {'__name__': '__main__', '__file__': os.path.abspath(pfad)})


def zurueck_zum_auswahlwerkzeug():
    """Nach der Aktion wieder auf das 2D-Auswahlwerkzeug schalten."""
    for wert in (-240, -200):        # Werte je nach Version
        try:
            vs.SetTool(wert)
            return
        except Exception:
            continue


def ereignis():
    """Liefert die Ereignisnummer oder None, wenn sie nicht lesbar ist."""
    try:
        res = vs.vstGetEventInfo()
    except Exception:
        return None
    if isinstance(res, (list, tuple)):
        for v in res:
            if isinstance(v, int) and not isinstance(v, bool):
                return v
    if isinstance(res, int):
        return res
    return None


def main():
    ev = ereignis()

    # Ereignisse nicht lesbar -> Werkzeug verhaelt sich wie ein Menuebefehl
    if ev is None:
        starte_mauerbefehl()
        return

    if ev == EV_SETUP:
        for fn, arg in (('vstSetHelpString',
                         'Winkelstuetzmauer: Bezugslinien auswaehlen, '
                         'dann in die Zeichnung klicken'),
                        ('SetCursor', 1)):
            try:
                getattr(vs, fn)(arg)
            except Exception:
                pass
        return

    if ev in (EV_MOUSEDOWN, EV_MOUSEUP):
        starte_mauerbefehl()
        zurueck_zum_auswahlwerkzeug()
        return


try:
    main()
except Exception:
    import traceback
    try:
        vs.AlrtDialog('Fehler im Werkzeug:\n\n' + traceback.format_exc())
    except Exception:
        pass
