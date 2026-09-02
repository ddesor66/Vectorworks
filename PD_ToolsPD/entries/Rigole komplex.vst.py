# -*- coding: utf-8 -*-
"""
DAS IST DER INHALT DES WERKZEUGS "RIGOLE KOMPLEX".

Genau dieser Text kommt in den Skripteditor des DRITTEN Plug-ins
(Plug-in-Manager > Rigole komplex > Skript bearbeiten). Alle drei Werkzeuge
teilen sich den Modulordner 'Rigole'.

WAS DIESES WERKZEUG KANN
------------------------
Es fuellt ein GEZEICHNETES POLYGON mit Rigolenkoerben - fuer Rigolen, die
kein Rechteck sind.

    1. Ein geschlossenes Polygon (oder eine geschlossene Polylinie) zeichnen.
    2. Werkzeug "Rigole komplex" waehlen.
    3. Auf das Polygon klicken - am besten auf eine Kante, oder in die
       Flaeche, wenn es eine Fuellung hat.
    4. Im Dialog Korbtyp, Lagen, Hoehenlage und Schaechte einstellen. Die
       Ergebnisanzeige sagt sofort, wie viele Koerbe hineinpassen und wie
       gut die Flaeche ausgenutzt ist.
    5. OK - die Rigole entsteht.

Gesetzt werden nur Koerbe, die VOLLSTAENDIG innerhalb des Polygons liegen.
Angeschnittene Koerbe gibt es nicht; Rigolenkoerper lassen sich nicht
schneiden.

Das Raster richtet sich standardmaessig an der laengsten Polygonkante aus.
Bei schraeg liegenden Rigolen passen so deutlich mehr Koerbe hinein als bei
einem achsparallelen Raster. Im Dialog laesst sich das umstellen.

DAS UMGRENZUNGSPOLYGON BLEIBT LIEGEN
------------------------------------
Es wird nicht geloescht und nicht veraendert - es bekommt nur einen Namen
("Rigole komplex RIGK-001 Umgrenzung"), sofern es noch keinen hat. Ueber
diesen Namen findet das Werkzeug es beim Bearbeiten wieder. Hat das Polygon
schon einen eigenen Namen, bleibt dieser stehen.

Wer das Polygon spaeter loescht, kann die Rigole nicht mehr bearbeiten -
das Werkzeug sagt das dann auch. Die Rigole selbst bleibt natuerlich
bestehen.

VOR DEM ERSTEN START
--------------------
1. Unten bei RIGOLE_ORDNER den Pfad zum entpackten Ordner 'Rigole' eintragen.
2. Im Plug-in-Manager unter Einstellungen > Eigenschaften:
       Projektionsart   = Nur 2D
       Script ausfuehren = Nach Mausklick

   Mehr ist nicht einzustellen; eine Modusleiste gibt es im Plug-in-Manager
   nicht (siehe Werkzeugskript.py).

VORHANDENE RIGOLE BEARBEITEN
----------------------------
Mit dem Werkzeug auf eine vorhandene komplexe Rigole klicken. Es fragt nach,
oeffnet den Dialog mit den gespeicherten Werten und baut die Rigole nach OK
an derselben Stelle neu auf - Kennung und Umgrenzung bleiben erhalten. Ein
Rueckgaengig nimmt den ganzen Vorgang zurueck.

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
            # Beide Werkzeuge teilen sich den Modulordner - auch die
            # Einstiegsmodule muessen raus, sonst wirkt eine Aenderung dort
            # erst nach einem Neustart von Vectorworks.
            if name.startswith("rigole_") or name in (
                    "rigole_tool", "kies_tool", "polygon_tool"):
                try:
                    del sys.modules[name]
                except Exception:
                    pass

    try:
        import polygon_tool
    except Exception as ex:
        vs.AlrtDialog("Die Rigolen-Module konnten nicht geladen werden.\n\n"
                      "Ordner: %s\n\nTechnische Meldung: %r" % (ordner, ex))
        return

    polygon_tool.PROTOKOLL_AN = PROTOKOLL
    try:
        polygon_tool.run()
    except Exception as ex:
        import traceback
        spur = ""
        try:
            spur = traceback.format_exc()
        except Exception:
            pass
        vs.AlrtDialog("Beim Erzeugen der komplexen Rigole ist ein unerwarteter Fehler "
                      "aufgetreten.\n\n%r" % (ex,))
        _bericht_schreiben(spur)
    finally:
        _bericht_schreiben(polygon_tool.protokoll_text())


main()
