# -*- coding: utf-8 -*-
"""
DAS IST DER INHALT DES WERKZEUGS.

Genau dieser Text kommt in den Skripteditor des Plug-ins (Plug-in-Manager >
Rigole > Skript bearbeiten). Er ist absichtlich kurz - die eigentliche Arbeit
steckt in den Modulen im Ordner 'Rigole'.

VOR DEM ERSTEN START
--------------------
1. Unten bei RIGOLE_ORDNER den Pfad zum entpackten Ordner 'Rigole' eintragen.
2. Im Plug-in-Manager unter Einstellungen > Eigenschaften:
       Projektionsart   = Nur 2D
       Script ausfuehren = Nach Mausklick

WAEHREND DER ENTWICKLUNG
------------------------
DEV_MODE = True laedt die Module bei jedem Klick neu. Damit wirkt eine
geaenderte .py sofort, ohne Vectorworks neu zu starten. Fuer den
produktiven Einsatz spaeter auf False setzen - das ist etwas schneller.

PROTOKOLL = True schreibt bei jedem Lauf einen Bericht in den
Benutzer-Plug-ins-Ordner. Fuer die Testphase hilfreich, danach auf False.
"""

# ---------------------------------------------------------------------------
RIGOLE_ORDNER = r"H:\PROJEKTE\0 Vorlagen Vectorwork 2026\Plug-Ins\Rigole"

DEV_MODE = True
PROTOKOLL = True
# ---------------------------------------------------------------------------

import os
import sys

import vs


def _ordner_finden():
    if RIGOLE_ORDNER and os.path.isdir(os.path.join(RIGOLE_ORDNER, "rigole_core")):
        return RIGOLE_ORDNER
    # Rueckfall: Ordner 'Rigole' im Benutzer-Plug-ins-Ordner
    try:
        kandidat = os.path.join(vs.GetFolderPath(-2), "Rigole")
        if os.path.isdir(os.path.join(kandidat, "rigole_core")):
            return kandidat
    except Exception:
        pass
    return None


def _bericht_schreiben(text):
    if not PROTOKOLL or not text:
        return
    try:
        pfad = os.path.join(vs.GetFolderPath(-2), "Rigole_Protokoll.txt")
        f = open(pfad, "a", encoding="utf-8")
        f.write(text + "\n")
        f.close()
    except Exception:
        pass


def main():
    ordner = _ordner_finden()
    if ordner is None:
        vs.AlrtDialog(
            "Der Ordner 'Rigole' wurde nicht gefunden.\n\n"
            "Bitte tragen Sie oben im Werkzeugskript bei RIGOLE_ORDNER "
            "den richtigen Pfad ein.\n\nGesucht wurde in:\n"
            + str(RIGOLE_ORDNER))
        return

    if ordner not in sys.path:
        sys.path.insert(0, ordner)

    if DEV_MODE:
        for name in list(sys.modules.keys()):
            if name.startswith("rigole_"):
                try:
                    del sys.modules[name]
                except Exception:
                    pass

    try:
        import rigole_tool
    except Exception as ex:
        vs.AlrtDialog("Die Rigolen-Module konnten nicht geladen werden.\n\n"
                      "Ordner: %s\n\nTechnische Meldung: %r" % (ordner, ex))
        return

    rigole_tool.PROTOKOLL_AN = PROTOKOLL
    try:
        rigole_tool.run()
    except Exception as ex:
        import traceback
        spur = ""
        try:
            spur = traceback.format_exc()
        except Exception:
            pass
        vs.AlrtDialog("Beim Erzeugen der Rigole ist ein unerwarteter Fehler "
                      "aufgetreten.\n\n%r" % (ex,))
        _bericht_schreiben(spur)
    finally:
        _bericht_schreiben(rigole_tool.protokoll_text())


main()