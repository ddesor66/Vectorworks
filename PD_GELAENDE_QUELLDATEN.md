# Gelände-Quelldaten aus einer Markierung erzeugen

`pd_gelaende_quelldaten.py` ist ein eigenständiges Python-Skript für Vectorworks 2026.
Es wandelt alle markierten Objekte, die Vectorworks im 3D-Raum lokalisieren kann, in
genau die beiden Objektarten um, die das Geländemodell als Ausgangsdaten akzeptiert:

- **3D-Punkte** (`Locus3D`) für punktförmige Quellen,
- **3D-Polygone** für Bruchkanten und geschlossene Höhenlinien.

Die Originalobjekte werden weder verändert noch gelöscht. Die Ausgabe entsteht auf einer
neuen Konstruktionsebene und ist nach dem Lauf markiert.

## Einbau und Aufruf

1. In Vectorworks `Werkzeuge > Skripte > Skripte verwalten` ein neues **Python-Skript**
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
