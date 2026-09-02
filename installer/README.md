# Installer – Gelände-Quelldaten

Beide Dateien sind **erzeugte** Installer für das Vectorworks-2026-Skript
`pd_gelaende_quelldaten.py`. Sie tragen das Werkzeug eingebettet mit und prüfen es beim
Schreiben gegen eine SHA-256-Prüfsumme.

| Datei | Ausführung |
| --- | --- |
| `PD_Gelaende_Quelldaten_Installer.py` | Inhalt in ein Python-Skript der Vectorworks-Skript-Palette einfügen und ausführen |
| `PD_Gelaende_Quelldaten_Setup.py` | außerhalb von Vectorworks: `python3 PD_Gelaende_Quelldaten_Setup.py` |

Installiert werden in den Benutzer-Plug-ins-Ordner:

- `pd_gelaende_quelldaten.py` – das Werkzeug,
- `PD_Gelaende_Quelldaten_Menuebefehl.txt` – der unveränderliche Loader-Text für den
  Menübefehl bzw. für ein Skript in der Skript-Palette.

Der einmalige Menübefehl wird im Plug-in-Manager angelegt; Vectorworks-Plug-ins (`.vsm`)
sind Binärdateien und lassen sich nicht skripten. Alle weiteren Updates erledigt allein
ein erneuter Installerlauf.

Nicht von Hand ändern – neu bauen mit:

    python3 tools/build_gelaende_installer.py

Vollständige Beschreibung: [../PD_GELAENDE_QUELLDATEN.md](../PD_GELAENDE_QUELLDATEN.md)
