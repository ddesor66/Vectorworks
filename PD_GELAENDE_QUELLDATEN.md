# Gelände-Quelldaten aus einer Markierung erzeugen

`pd_gelaende_quelldaten.py` ist ein eigenständiges Python-Skript für Vectorworks 2026.
Es wandelt alle markierten Objekte, die Vectorworks im 3D-Raum lokalisieren kann, in
genau die beiden Objektarten um, die das Geländemodell als Ausgangsdaten akzeptiert:

- **3D-Punkte** (`Locus3D`) für punktförmige Quellen,
- **3D-Polygone** für Bruchkanten und geschlossene Höhenlinien.

Die Originalobjekte werden weder verändert noch gelöscht. Die Ausgabe entsteht auf einer
neuen Konstruktionsebene und ist nach dem Lauf markiert.

## Installation mit dem fertigen Installer (empfohlen)

Beide Installer tragen das Werkzeug eingebettet mit, prüfen es beim Schreiben gegen
eine SHA-256-Prüfsumme und legen es im Benutzer-Plug-ins-Ordner von Vectorworks ab.
Ein erneuter Lauf aktualisiert eine vorhandene Fassung und meldet die Versionen.

**Variante A – in Vectorworks** (`installer/PD_Gelaende_Quelldaten_Installer.py`)

1. Inhalt der Datei in ein neues Python-Skript der Skript-Palette einfügen und ausführen.
2. Der Dialog nennt den Zielpfad und die verbleibenden Schritte.

**Variante B – ohne Vectorworks** (`installer/PD_Gelaende_Quelldaten_Setup.py`)

    python3 installer/PD_Gelaende_Quelldaten_Setup.py            # Ordner automatisch suchen
    python3 installer/PD_Gelaende_Quelldaten_Setup.py --zeigen   # nur anzeigen, nichts schreiben
    python3 installer/PD_Gelaende_Quelldaten_Setup.py --ziel "<Plug-ins-Ordner>"

Gesucht wird unter Windows in `%APPDATA%\Nemetschek\Vectorworks\<Jahr>\Plug-ins`,
unter macOS in `~/Library/Application Support/Vectorworks/<Jahr>/Plug-ins`, jeweils
für 2026 bis 2023 mit Vorrang für den neuesten Jahrgang.

**Variante C – Windows-Programm** (`PD_Gelaende_Quelldaten_Setup.exe`)

Für Kolleginnen und Kollegen ohne Python: Das Setup wird als eigenständiges
Windows-Programm gebaut. Der Bau läuft in GitHub Actions auf einem Windows-Runner
(`.github/workflows/gelaende-installer-exe.yml`) und startet bei jeder Änderung an
Skript, Vorlagen oder Installern; er lässt sich unter `Actions` auch von Hand auslösen.

1. Im Repository auf `Actions > Gelände-Quelldaten Setup.exe bauen` den letzten Lauf öffnen.
2. Unter `Artifacts` das Paket `PD_Gelaende_Quelldaten_Setup-exe` herunterladen und entpacken.
3. `PD_Gelaende_Quelldaten_Setup.exe` doppelklicken. Das Fenster bleibt bis zur
   Bestätigung offen und nennt Zielpfad und nächste Schritte.

Der Lauf prüft das gebaute Programm selbst: `--zeigen`, eine vollständige
Testinstallation in einen leeren Ordner und die SHA-256-Summe der EXE liegen dem
Artefakt bei.

Auf einem Windows-Rechner geht derselbe Bau auch von Hand:

    pip install "pyinstaller>=6,<7"
    python tools/build_gelaende_installer.py
    pyinstaller --onefile --console --name PD_Gelaende_Quelldaten_Setup installer/PD_Gelaende_Quelldaten_Setup.py

Die EXE ist **nicht signiert**. Windows SmartScreen meldet deshalb beim ersten Start
einen unbekannten Herausgeber (`Weitere Informationen > Trotzdem ausführen`), und
manche Virenscanner schlagen bei frisch gebauten PyInstaller-Programmen an. Für eine
breite Verteilung im Büro ist ein Code-Signing-Zertifikat der saubere Weg – ohne
Signatur bleibt der Warnhinweis bestehen.

**Einmalig danach – der Menübefehl.** Vectorworks-Plug-ins (`.vsm`) sind Binärdateien,
die nur der Plug-in-Manager erzeugen kann; dieser Schritt lässt sich nicht skripten:

1. `Extras > Plug-ins > Plug-in-Manager > Neu > Menübefehl`, Name `Gelände-Quelldaten`,
   Sprache **Python**.
2. Den Inhalt der mitinstallierten Datei `PD_Gelaende_Quelldaten_Menuebefehl.txt`
   in den Skripteditor einfügen.
3. Im Arbeitsbereich-Editor den Befehl in ein Menü ziehen, anschließend Vectorworks neu starten.

Dieser Loader-Text bleibt über alle Updates unverändert – er lädt bei jedem Aufruf die
installierte Skriptdatei neu. Künftige Updates sind daher nur noch ein Installerlauf.
Wer keinen Menübefehl möchte, legt stattdessen ein Skript in der Skript-Palette mit
demselben Loader-Text an.

Die Installer werden aus dem Skript erzeugt:

    python3 tools/build_gelaende_installer.py

## Einbau ohne Installer

Für einen einmaligen Einsatz genügt das Skript selbst:

1. Im Ressourcen-Manager eine Skript-Palette und darin ein neues **Python-Skript**
   anlegen und den Inhalt von `pd_gelaende_quelldaten.py` einfügen.
2. Die umzuwandelnden Objekte markieren – gern die komplette Importebene.
3. Das Skript ausführen. Der Abschlussdialog nennt Anzahl, Ebenennamen und die Gründe
   für nicht übernommene Objekte.
4. Mit der bestehenden Markierung
   `Landschaft > Geländemodell > Geländemodell aus Ausgangsdaten` aufrufen.

Alternativ kann die Datei als Menübefehl-Plug-in eingebunden werden; der Ablauf ist gleich.

## Behandelte Objekttypen

| Quelle | Ergebnis |
| --- | --- |
| 3D-Punkt | 3D-Punkt mit Ebenenbasishöhe |
| 2D-Punkt, Text, sonstige Punktobjekte | 3D-Punkt am Einfüge-/Textursprung |
| Text ohne echte 3D-Höhe mit genau einer Zahl (`102.65`, `H=102,65`) | 3D-Punkt mit dieser Höhe |
| Symbol/Block | 3D-Punkt am Einfügepunkt (umschaltbar auf volle 3D-Geometrie) |
| Vermessungspunkt-/Höhenmarken-Plug-in | 3D-Punkt am 3D-Einfügepunkt |
| Linie, Polygon, Polylinie | 3D-Bruchkante bzw. geschlossene Kontur |
| Bogen, Kreis, Rechteck, Freihandlinie | abgetastete bzw. umgewandelte 3D-Polygone |
| 3D-Polygon, NURBS-Kurve | 3D-Bruchkante mit allen Scheitelhöhen |
| Mesh | jeder Eckpunkt als eigener 3D-Punkt |
| Gruppe | rekursiv gelesen, das Original bleibt erhalten |
| Volumenkörper und andere räumliche Fremdtypen | über eine temporäre Kopie in 3D-Polygone aufgelöst |

Objekte ohne eigenen Leseweg liefern mindestens einen Stützpunkt an ihrem
Vectorworks-3D-Mittelpunkt. Punktwolken werden nicht übernommen.

## Einstellungen im Skriptkopf

| Konstante | Bedeutung |
| --- | --- |
| `ZIEL_EBENE`, `KLASSE_PUNKT`, `KLASSE_KANTE` | Namen der erzeugten Ebene und Klassen |
| `SEHNENTOLERANZ_M` | Abtastgenauigkeit für Bögen und Freihandkurven |
| `TEXTHOEHE_AUS_INHALT`, `TEXTHOEHE_IN_METERN` | Höhe aus dem Textinhalt lesen und deren Einheit |
| `SYMBOL_ALS_EINFUEGEPUNKT` | Symbole als Punkt oder als volle 3D-Geometrie |
| `OHNE_HOEHE_UEBERNEHMEN` | reine 2D-Objekte auf Ebenenbasishöhe mitnehmen |
| `DUBLETTEN_ENTFERNEN`, `DUBLETTEN_TOLERANZ_M` | deckungsgleiche Punkte zusammenfassen |
| `HOEHE_MIN_M`, `HOEHE_MAX_M` | Plausibilitätsfenster gegen Ausreißer aus Importen |

Voreingestellt werden Objekte **ohne echte Höhe** übersprungen und im Bericht gezählt.
Das verhindert, dass ein Geländemodell durch flächig auf Höhe null liegende
Importgeometrie verzogen wird. Für Zeichnungen mit tatsächlich sinnvoller
Ebenenbasishöhe `OHNE_HOEHE_UEBERNEHMEN = True` setzen.

## Sicherheit und Prüfung

- Die Ausgabe wird von Vectorworks selbst nachgezählt (`Count` je Ebene und Objekttyp).
  Bei einer Abweichung werden alle erzeugten Objekte und die neue Ebene gelöscht und der
  Lauf als Fehler gemeldet, statt Vollständigkeit zu behaupten.
- Die Markierung erfolgt nativ über ein Ebenenkriterium.
- Der Vorgang erhält das Rückgängig-Ereignis `Gelände-Quelldaten erzeugen`.
- Es werden keine sprachabhängigen Menüaufrufe (`DoMenuTextByName`) verwendet.

## Grenzen

- Höhen aus Parametern von Plug-in-Objekten werden nicht ausgelesen; maßgeblich ist der
  3D-Einfügepunkt. Native Höhenmarken kann das Geländemodell ohnehin direkt verwenden.
- Höhentexte innerhalb von Symboldefinitionen werden nicht gelesen. Solche Blöcke vorher
  auflösen oder die Höhentexte als eigene Textobjekte markieren.
- Das Skript erzeugt kein Geländemodell; dieser Schritt bleibt der native Befehl.
- Für den vollständigen Arbeitsablauf mit Vorschau, Bestands-/Sollmodellen, Baugruben und
  Massenvergleich steht das Modul `PD_GelaendeBaugruben` zur Verfügung. Das Skript deckt
  bewusst nur die Umwandlung ab und läuft ohne Installation.

## Tests

    python3 -m unittest tests.test_gelaende_quelldaten
    python3 -m unittest tests.test_gelaende_installer

Die Installerprüfungen stellen unter anderem sicher, dass die eingecheckten Installer
zum aktuellen Skriptstand passen, dass ein beschädigter Inhalt nichts schreibt und dass
der Loader-Text tatsächlich die installierte Fassung startet.
