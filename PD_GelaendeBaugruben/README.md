# PD Gelände und Baugruben

Produktionsmodul für Vectorworks 2026 zum Prüfen von Geländedaten, Verwalten von Bestands-/Sollzuständen, Konstruieren von Baugrubenböschungen sowie numerischen Ermitteln von Abtrag und Auftrag.

## Voraussetzungen und Aufruf

- Vectorworks 2026; zum Erzeugen und Bearbeiten nativer Geländemodelle ist eine Produktvariante mit Geländemodell-Funktionen erforderlich (insbesondere Architektur/Landschaft).
- Die Installation erfolgt über den vollständigen PD-Tools-Einklickinstaller.
- Aufruf: über das eigenständige Hauptmenü `Gelände und Baugruben` oder das
  gleichnamige grafische Werkzeug in der Werkzeuggruppe `Favoriten`.
- Die Funktion ist bewusst nicht mehr Teil des Kanal-/Leitungs-Auswahldialogs.
- Alle Modulberechnungen verwenden Meter, Quadratmeter und Kubikmeter. Dokumentkoordinaten werden über `GetUnits` verlustarm in Meter umgerechnet.

## Assistent

### 1. Quelldaten wählen und prüfen

1. Geeignete Objekte markieren. Unterstützt sind 3D-Punkte, erkannte Vermessungspunkt-Plug-in-Objekte, 3D-Polygone/Bruchkanten, Linien, Polygone, Polylinien und abgetastete Bögen mit gültiger Höhe.
2. Optional ein geschlossenes 2D-Polygon als Modellbegrenzung mit markieren.
3. Sehnentoleranz, Dublettentoleranz, Höhentoleranz, Ausschlussmuster, Ziel-Ebene, gewünschten DGM-Namen, DGM-Klasse und Höhenlinien-Äquidistanz einstellen.
4. `Vorschau` zeigt verwendbare, ausgeschlossene, problematische und nicht unterstützte Objekte. Gleiche XY-Lage mit widersprüchlicher Höhe und Begrenzungskreuzungen blockieren die Ausgabe.
5. Nach Bestätigung werden geprüfte Kopien auf einer neuen Ebene angelegt und markiert. Originale werden weder geändert noch gelöscht.
6. Danach den von Vectorworks bereitgestellten Befehl `Landschaft > Geländemodell > Geländemodell aus Ausgangsdaten` ausführen und die im Abschlussdialog genannten Vorgaben verwenden.

3D-Polygone und Bruchkanten bleiben als 3D-Polygone erhalten. Kurven werden nur mit der gewählten Sehnentoleranz abgetastet. Punktwolken und Meshes werden nicht pauschal konvertiert, sondern als nicht unterstützt ausgewiesen.

### 2. Bestands- und Sollmodelle

- Ein benanntes natives DGM kann als `Bestand` oder `Soll` registriert werden.
- Sollvarianten können als unabhängige DGM-Kopie angelegt werden. Jede Kopie erhält Variantenname, Referenzmodell und Priorität als nachvollziehbare Metadaten.
- Löschen ist ausschließlich für eine vom Modul erzeugte und als Soll gekennzeichnete Kopie möglich.
- Änderungen am Bestandsmodell oder an anderen, nicht verwalteten DGM werden dadurch nicht ausgeführt.

Bei mehreren Sollflächen wird der Benutzer nicht durch eine erfundene automatische Überlagerung getäuscht: Für die Berechnung werden genau ein Referenz- und ein Vergleichsmodell gewählt. Nicht eindeutig zusammengeführte Überlappungen müssen zuvor als eigene native Sollvariante aufgelöst werden.

### 3. Baugrube und Böschung

1. Zuerst die geschlossene Baugrubensohle markieren; weitere markierte geschlossene Polygone gelten als benannte Hindernisse.
2. Höhe am ersten Begrenzungspunkt, optionales Sohlengefälle in Prozent und Gefällerichtung in Grad eingeben.
3. Böschungsneigung als `1:n`, Prozent oder Grad sowie maximale Ausdehnung festlegen.
4. Schraffurabstand und Verhältnis der kurzen Linien einstellen. Voreinstellung: jede zweite Linie 50 Prozent.
5. Die Vorschau meldet nicht herstellbare Abschnitte, das verursachende Hindernis und – soweit bestimmbar – die erforderliche steilste Neigung. Die gewünschte Neigung wird nie still geändert.

Die Ausgabe verwendet getrennte, eindeutig benannte 2D- und 3D-Objekte für Unter- und Oberkante sowie eigene Klassen für Sohle, Böschung, Schraffur und Konflikte. Die Sohlenfläche kann über die verifizierte `SetPadAttrs`-Schnittstelle als einfacher nativer Pad-Modifikator gekennzeichnet werden. Ob die Modifikatorebene im konkreten DGM zugelassen ist und die Aktualisierung erfolgreich ist, muss in Vectorworks geprüft werden.

### 4. Geländemodelle vergleichen

1. Eine geschlossene Auswertungsbegrenzung markieren.
2. Referenz und Vergleich wählen; beide müssen verschieden sein.
3. Rasterweite, Rasterwinkel, Höhentoleranz, Konvergenztoleranz, Rasterursprung und Textgröße einstellen.
4. Bei automatischem Ursprung wird der erste Punkt der Begrenzung verwendet; andernfalls gelten die eingegebenen X-/Y-Koordinaten.
5. Die Berechnung kann über den Vectorworks-Fortschrittsdialog abgebrochen werden. Vor der Bestätigung werden keine Ergebnisobjekte erzeugt.

Vorzeichen: `Differenzhöhe = Vergleich − Referenz`; positive Werte sind Auftrag, negative Werte Abtrag.

Die sichtbare Rasterweite wird für den Plan verwendet. Für die Mengen wird zusätzlich mit halber Rasterweite gerechnet. Die Abweichung beider Integrationen wird als Konvergenz angegeben:

- `Konvergiert`: gewählte Toleranz erreicht.
- `Vorläufig`: Raster verfeinern.
- `Teilüberdeckung`: mindestens ein Mittelpunkt liegt nicht auf beiden Modellen; diese Felder werden als `keine Daten` ausgewiesen und nicht als Nullhöhe gerechnet.

Ermittelt werden Abtrags-/Auftragsvolumen, Differenz, Abtrags-/Auftragsfläche, maximale sowie flächengewichtete mittlere Höhen. Randzellen werden nach der Mittelpunktregel einbezogen; deshalb ist die dokumentierte Raster- und Konvergenzprüfung Bestandteil des Ergebnisses.

### 5. Ausgabe

- Vectorworks-Tabelle `PD Gelände – Massenvergleich` mit Modellen, Datum, Methode, Status, Einheiten, Begrenzung, Rasterparametern, Mengen und Konvergenz.
- Rasterbeschriftung auf getrennten Klassen für Auftrag, Abtrag, Null und keine Daten.
- Näherungsweise Null-/Verschneidungslinien aus dem sichtbaren Differenzraster.
- Böschungsschraffur mit abwechselnd langen und kurzen Linien.

Eine vorhandene Ergebnistabelle wird erst überschrieben, nachdem eine neue temporäre Tabelle erfolgreich aufgebaut wurde. Bei einem Fehler bleibt die geprüfte Tabelle als `Wiederherstellung` erhalten.

## Rückgängig und Datensicherheit

- Original-Quelldaten werden nicht verändert.
- Erzeugte Ausgaben werden bei einem Fehler vollständig zurückgerollt.
- Die Ausgabeschritte erhalten benannte Vectorworks-Rückgängig-Ereignisse.
- `Abbrechen` erzeugt keine Berechnungsausgabe. `Zurück` führt zur Assistentenübersicht.
- Es werden keine sprachabhängigen Menüaufrufe (`DoMenuTextByName`) verwendet.

## Technische API-Grenze

Die offizielle Vectorworks-2026-Python-Referenz stellt geprüfte Funktionen zum Finden und Abfragen bestehender nativer DGM bereit (`DTM6_GetDTMObject`, `DTM6_IsDTM6Object`, `DTM6_IsObjectReady`, `DTM6_GetZatXY`). In der vorhandenen offiziellen `vs.py` ist dagegen keine belastbare Python-Funktion dokumentiert, die aus beliebigen Quellen ein neues natives DGM erzeugt, einen Modifikator sicher einem bestimmten DGM zuordnet, die Modifikatorebene einschaltet, das DGM garantiert aktualisiert oder native Abtrag-/Auftragswerte ausliest.

Darum trennt das Modul strikt:

- automatisierbar: Quellprüfung/-kopie, DGM-Erkennung/-Abfrage, Sollkopien, numerischer Vergleich, Planausgabe, Tabelle und einfacher Pad-Attributversuch;
- nativer Benutzerschritt: DGM aus markierten Ausgangsdaten erzeugen, DGM-Einstellungen/Modifikatorebene prüfen und DGM aktualisieren;
- nicht als native Vectorworks-Menge behauptet: Die Modulmengen sind reproduzierbare, konvergenzgeprüfte Rasterintegration.

## Bekannte Einschränkungen

- Punktwolken und Mesh-Geometrien werden mangels verifizierter, verlustfreier Python-Konvertierung nicht übernommen.
- Modellbegrenzungen und Hindernisse sind einfache geschlossene 2D-Polygone/Polylinien ohne Löcher.
- Böschungsverschneidungen werden an den Eckstrahlen der Sohle gelöst; hochkomplexe freie Böschungsflächen benötigen eine zusätzliche visuelle Fachprüfung.
- Null-/Verschneidungslinien werden aus dem Differenzraster angenähert, nicht aus einer nicht verfügbaren nativen DGM-Verschneidungsfunktion.
- Eine erfolgreiche Ausführung der automatischen Tests ersetzt nicht die in `MANUAL_TESTS.md` dokumentierten Prüfungen im realen Vectorworks 2026.
