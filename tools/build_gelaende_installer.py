# -*- coding: utf-8 -*-
"""Baut die fertigen Installer für pd_gelaende_quelldaten.py.

Erzeugt werden zwei eigenständige Dateien, die den Skriptinhalt eingebettet
mitführen und beim Installieren gegen eine SHA-256-Prüfsumme halten:

* ``installer/PD_Gelaende_Quelldaten_Installer.py`` – wird einmal in die
  Vectorworks-Skript-Palette eingefügt und dort ausgeführt.
* ``installer/PD_Gelaende_Quelldaten_Setup.py`` – wird außerhalb von
  Vectorworks ausgeführt (Doppelklick oder ``python3 …_Setup.py``).

Aufruf:  python3 tools/build_gelaende_installer.py
"""
from __future__ import absolute_import

import base64
import hashlib
import os
import re
import textwrap

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUELLE = os.path.join(WURZEL, "pd_gelaende_quelldaten.py")
AUSGABE = os.path.join(WURZEL, "installer")
VORLAGE_VW = os.path.join(WURZEL, "tools", "vorlage_installer_vw.py")
VORLAGE_DESKTOP = os.path.join(WURZEL, "tools", "vorlage_installer_desktop.py")
ZIEL_VW = "PD_Gelaende_Quelldaten_Installer.py"
ZIEL_DESKTOP = "PD_Gelaende_Quelldaten_Setup.py"
LOADER_DATEI = "PD_Gelaende_Quelldaten_Menuebefehl.txt"

# Der Menübefehl bleibt über alle Updates gleich: Er lädt die installierte
# Skriptdatei aus dem Benutzer-Plug-ins-Ordner und ruft sie ausdrücklich auf.
LOADER = '''# Menübefehl "Gelände-Quelldaten" – dieser Text bleibt bei Updates unverändert.
# Plug-in-Manager > Neu > Menübefehl > Sprache Python, oder als Skript
# in einer Skript-Palette.
import os
import sys

import vs

_ordner = str(vs.GetFolderPath(-2) or "")
if _ordner and _ordner not in sys.path:
    sys.path.insert(0, _ordner)

os.environ["PD_GELAENDE_QUELLDATEN_KEIN_AUTOSTART"] = "1"
try:
    import importlib

    import pd_gelaende_quelldaten as werkzeug
    importlib.reload(werkzeug)          # immer die installierte Fassung verwenden
except ImportError:
    vs.AlrtDialog("Gelände-Quelldaten ist nicht installiert.\\n\\n"
                  "Bitte den Installer ausführen.")
else:
    werkzeug.quelldaten_erzeugen(vs)
'''

KOPF = '''# -*- coding: utf-8 -*-
"""{titel}

{beschreibung}

ERZEUGTE DATEI – NICHT VON HAND ÄNDERN.
Sie entsteht aus pd_gelaende_quelldaten.py über
``python3 tools/build_gelaende_installer.py``.
"""
from __future__ import absolute_import

VERSION = "{version}"
DATEINAME = "{dateiname}"
LOADER_DATEI = "{loaderdatei}"
PRUEFSUMME = "{pruefsumme}"

LOADER = {loader!r}

# Base64 des vollständigen Skripts pd_gelaende_quelldaten.py.
PAYLOAD = (
{payload}
)

'''

TITEL_VW = "Installer für das Vectorworks-Skript Gelände-Quelldaten."
BESCHREIBUNG_VW = textwrap.dedent("""\
    Diesen Text einmal in ein Python-Skript der Vectorworks-Skript-Palette
    einfügen und ausführen. Der Installer legt das eigentliche Werkzeug im
    Benutzer-Plug-ins-Ordner ab und schreibt den unveränderlichen Loader-Text
    für den Menübefehl daneben.""")
TITEL_DESKTOP = "Setup für das Vectorworks-Skript Gelände-Quelldaten."
BESCHREIBUNG_DESKTOP = textwrap.dedent("""\
    Außerhalb von Vectorworks ausführen: Doppelklick oder
    ``python3 PD_Gelaende_Quelldaten_Setup.py``. Das Setup sucht den
    Benutzer-Plug-ins-Ordner von Vectorworks, legt das Werkzeug dort ab und
    schreibt den Loader-Text für den Menübefehl daneben.""")


def version_lesen(quelltext):
    treffer = re.search(r'^VERSION\s*=\s*"([^"]+)"', quelltext, re.MULTILINE)
    if not treffer:
        raise SystemExit("In pd_gelaende_quelldaten.py fehlt die Konstante VERSION.")
    return treffer.group(1)


def payload_zeilen(daten, breite=76):
    text = base64.b64encode(daten).decode("ascii")
    zeilen = [text[start:start + breite] for start in range(0, len(text), breite)]
    return "\n".join('    "%s"' % zeile for zeile in zeilen)


def bauen(quelle=QUELLE, ausgabe=AUSGABE):
    """Beide Installer erzeugen und die geschriebenen Pfade zurückgeben."""
    with open(quelle, "rb") as datei:
        daten = datei.read()
    version = version_lesen(daten.decode("utf-8"))
    kopf_werte = dict(
        version=version,
        dateiname=os.path.basename(quelle),
        loaderdatei=LOADER_DATEI,
        pruefsumme=hashlib.sha256(daten).hexdigest(),
        loader=LOADER,
        payload=payload_zeilen(daten),
    )
    if not os.path.isdir(ausgabe):
        os.makedirs(ausgabe)
    ergebnis = []
    for vorlage, ziel, titel, beschreibung in (
            (VORLAGE_VW, ZIEL_VW, TITEL_VW, BESCHREIBUNG_VW),
            (VORLAGE_DESKTOP, ZIEL_DESKTOP, TITEL_DESKTOP, BESCHREIBUNG_DESKTOP)):
        with open(vorlage, "r", encoding="utf-8") as datei:
            rumpf = datei.read()
        inhalt = KOPF.format(titel=titel, beschreibung=beschreibung, **kopf_werte) + rumpf
        pfad = os.path.join(ausgabe, ziel)
        with open(pfad, "w", encoding="utf-8", newline="\n") as datei:
            datei.write(inhalt)
        ergebnis.append(pfad)
    return tuple(ergebnis)


if __name__ == "__main__":
    for pfad in bauen():
        print("erzeugt: " + os.path.relpath(pfad, WURZEL))
